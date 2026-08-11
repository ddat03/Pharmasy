"""Scraper de Fybeca. Plataforma: Salesforce Commerce Cloud (SFCC).

A diferencia de las cadenas VTEX, Fybeca no expone una API JSON de
catálogo pública (ver Boveda Farmacia/Entidades/Fybeca.md). Se usa la
página de búsqueda HTML `/busqueda?q=<término>`, de donde se extraen dos
bloques:
  - Un `<script type="application/ld+json">` con `@type: ItemList` que trae
    la URL real de cada producto (incluye su id `ECFY_<n>` en el path).
  - Atributos `data-gtm` (HTML-escapados) con evento `ImpressionsUpdate`
    que traen id, nombre y precio de cada producto en la misma página.
Se cruzan ambos por el id `ECFY_<n>` para armar cada fila.

Limitación conocida: a diferencia de VTEX (que expone IsAvailable), esta
página no trae una señal explícita y confiable de stock para todos los
casos observados. `en_stock` queda `None` (desconocido) salvo cuando el
precio no está presente, señal de que el producto no está disponible para
compra — en ese caso se marca `en_stock=False` y `precio_usd=None`. No se
inventa disponibilidad que no se pueda confirmar.

Uso:
    python scrapers/fybeca.py --limit 10
    python scrapers/fybeca.py --terms Losartan,Metformina
    python scrapers/fybeca.py --all
    python scrapers/fybeca.py --limit 10 --dry-run
"""

import argparse
import csv
import html
import json
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from base import BlockedError, get_html, rate_limit_sleep, save_raw, supabase_insert, supabase_upsert

PHARMACY = "fybeca"
BASE_URL = "https://www.fybeca.com"
SEARCH_URL = BASE_URL + "/busqueda?q={term}"

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_CSV = BASE_DIR / "db" / "seed_medicamentos.csv"

GTM_RE = re.compile(r'data-gtm="(.*?)"')
JSONLD_RE = re.compile(r'<script type="application/ld\+json">\s*(\{.*?"ItemList".*?\})\s*</script>', re.S)
ECFY_ID_RE = re.compile(r"(ECFY_[0-9]+)\.html")


def load_terms():
    terms = []
    seen = set()
    with open(SEED_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row["principio_activo"].strip()
            if "(" in raw:
                continue
            term = raw.replace("/", " ")
            if term not in seen:
                seen.add(term)
                terms.append(term)
    return terms


def fetch(term):
    url = SEARCH_URL.format(term=urllib.parse.quote(term))
    page_html = get_html(url)
    save_raw(PHARMACY, term, {"html_len": len(page_html), "term": term})
    return page_html


def normalize(page_html):
    """Cruza el JSON-LD (URLs) con los data-gtm (nombre/precio) por id
    ECFY_<n>. Campo no extraído = None, nunca inventado."""
    url_by_id = {}
    m = JSONLD_RE.search(page_html)
    if m:
        try:
            data = json.loads(m.group(1))
            for item in data.get("itemListElement", []):
                u = item.get("url", "")
                id_match = ECFY_ID_RE.search(u)
                if id_match:
                    url_by_id[id_match.group(1)] = u
        except (ValueError, KeyError):
            pass

    rows = []
    seen_ids = set()
    for raw_attr in GTM_RE.findall(page_html):
        decoded = html.unescape(raw_attr)
        try:
            data = json.loads(decoded)
        except ValueError:
            continue
        if data.get("event") != "ImpressionsUpdate":
            continue
        impressions = data.get("ecommerce", {}).get("impressions")
        if not impressions:
            continue
        external_id = impressions.get("id")
        if not external_id or external_id in seen_ids:
            continue
        seen_ids.add(external_id)
        price = impressions.get("price")
        precio_usd = price if isinstance(price, (int, float)) else None
        en_stock = False if precio_usd is None else None  # None = desconocido, ver docstring
        rows.append(
            {
                "external_id": external_id,
                "nombre_en_tienda": impressions.get("name"),
                "url": url_by_id.get(external_id),
                "precio_usd": precio_usd,
                "precio_promocional": None,  # no distinguible del precio regular en esta página
                "en_stock": en_stock,
            }
        )
    return rows


def scrape(terms):
    by_external_id = {}
    errores = []
    for i, term in enumerate(terms, start=1):
        try:
            page_html = fetch(term)
        except BlockedError:
            raise  # 403/429: nunca se evade, se detiene todo el run
        except Exception as e:
            errores.append((term, str(e)))
            print(f"[{i}/{len(terms)}] {term} -> ERROR, se omite: {e}")
            if i < len(terms):
                rate_limit_sleep()
            continue
        for row in normalize(page_html):
            by_external_id[row["external_id"]] = row
        print(f"[{i}/{len(terms)}] {term} -> {len(by_external_id)} productos únicos acumulados")
        if i < len(terms):
            rate_limit_sleep()
    if errores:
        print(f"\n{len(errores)} términos con error (omitidos, no bloquean la corrida): {[t for t, _ in errores]}")
    return list(by_external_id.values())


def ecuador_today():
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date().isoformat()


def load_to_supabase(products):
    pharmacy_products_rows = [
        {
            "pharmacy": PHARMACY,
            "external_id": p["external_id"],
            "url": p["url"],
            "nombre_en_tienda": p["nombre_en_tienda"],
        }
        for p in products
    ]
    upserted = supabase_upsert("pharmacy_products", pharmacy_products_rows, on_conflict="pharmacy,external_id")
    id_by_external_id = {row["external_id"]: row["id"] for row in upserted}

    fecha = ecuador_today()
    snapshot_rows = []
    for p in products:
        pid = id_by_external_id.get(p["external_id"])
        if not pid:
            continue
        snapshot_rows.append(
            {
                "pharmacy_product_id": pid,
                "fecha": fecha,
                "precio_usd": p["precio_usd"],
                "en_stock": p["en_stock"],
                "precio_promocional": p["precio_promocional"],
            }
        )
    supabase_upsert("price_snapshots", snapshot_rows, on_conflict="pharmacy_product_id,fecha")
    return len(upserted), len(snapshot_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--terms", help="Términos separados por coma (override)")
    parser.add_argument("--limit", type=int, help="Limitar a los primeros N términos")
    parser.add_argument("--all", action="store_true", help="Correr los 194 términos de la semilla")
    parser.add_argument("--dry-run", action="store_true", help="No escribir a Supabase")
    args = parser.parse_args()

    if args.terms:
        terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    else:
        terms = load_terms()
        if not args.all:
            terms = terms[: args.limit or 10]

    start = time.monotonic()
    errores = 0
    try:
        products = scrape(terms)
    except BlockedError as e:
        print(f"BLOQUEADO: {e}. Marcar fybeca como blocked_from_ci y detener. No se evade.")
        return

    duracion = time.monotonic() - start
    print(f"\n{len(products)} productos únicos extraídos de {len(terms)} términos en {duracion:.1f}s")

    if args.dry_run:
        print("--dry-run: no se escribe a Supabase. Muestra de 3 productos:")
        for p in products[:3]:
            print(" ", p)
        return

    n_products, n_snapshots = load_to_supabase(products)
    print(f"Supabase: {n_products} pharmacy_products upsertados, {n_snapshots} price_snapshots guardados")

    supabase_insert(
        "scrape_runs",
        [
            {
                "fuente": PHARMACY,
                "productos_ok": len(products),
                "errores": errores,
                "duracion_segundos": round(duracion, 2),
            }
        ],
    )


if __name__ == "__main__":
    main()
