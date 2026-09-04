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
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from base import (
    BlockedError,
    get_html,
    rate_limit_sleep,
    record_scrape_run,
    save_raw,
    supabase_upsert,
)

PHARMACY = "fybeca"
BASE_URL = "https://www.fybeca.com"
SEARCH_URL = BASE_URL + "/busqueda?q={term}"

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_CSV = BASE_DIR / "db" / "seed_medicamentos.csv"

GTM_RE = re.compile(r'data-gtm="(.*?)"')
JSONLD_RE = re.compile(r'<script type="application/ld\+json">\s*(\{.*?"ItemList".*?\})\s*</script>', re.S)
ECFY_ID_RE = re.compile(r"(ECFY_[0-9]+)\.html")

# Para cola_larga.py: la página de un producto puntual (a diferencia de la
# de búsqueda) trae un bloque schema.org/Product con precio y sku -- no hace
# falta cruzar JSON-LD con data-gtm como en la búsqueda.
PRODUCT_JSONLD_RE = re.compile(r'<script type="application/ld\+json">\s*(\{.*?"@type":"Product".*?\})\s*</script>', re.S)


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


def fetch_product_page(url):
    page_html = get_html(url)
    save_raw(PHARMACY, url.rstrip("/").rsplit("/", 1)[-1][:60], {"html_len": len(page_html)})
    return page_html


def normalize_product_page(page_html, url):
    """Para cola_larga.py: una página de producto puntual (sacada del
    sitemap del sitio, no adivinada por término). Devuelve None si no se
    pudo extraer el bloque Product -- nunca inventa datos."""
    m = PRODUCT_JSONLD_RE.search(page_html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None

    external_id = data.get("sku")
    if not external_id:
        return None

    offers = data.get("offers") or {}
    price = offers.get("price")
    try:
        precio_usd = float(price) if price is not None else None
    except (TypeError, ValueError):
        precio_usd = None

    availability = offers.get("availability") or ""
    en_stock = True if "InStock" in availability else (False if availability else None)

    return {
        "external_id": external_id,
        "nombre_en_tienda": data.get("name"),
        "url": url,
        "precio_usd": precio_usd,
        "precio_promocional": None,  # no distinguible del precio regular en esta pagina
        "en_stock": en_stock,
    }


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
    return list(by_external_id.values()), len(errores)


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
    try:
        products, errores = scrape(terms)
    except BlockedError as e:
        # 403/429: no se evade nunca. Se registra la corrida caida (productos_ok
        # = 0) y se sale con codigo != 0 para que el nocturno la marque fallida.
        print(f"BLOQUEADO: {e}. Marcar fybeca como blocked_from_ci y detener. No se evade.")
        if not args.dry_run:
            record_scrape_run(PHARMACY, 0, 1, time.monotonic() - start)
        sys.exit(2)
    except Exception as e:
        print(f"FALLO la corrida de fybeca: {e}")
        if not args.dry_run:
            record_scrape_run(PHARMACY, 0, 1, time.monotonic() - start)
        sys.exit(1)

    duracion = time.monotonic() - start
    print(f"\n{len(products)} productos únicos extraídos de {len(terms)} términos en {duracion:.1f}s")

    if args.dry_run:
        print("--dry-run: no se escribe a Supabase. Muestra de 3 productos:")
        for p in products[:3]:
            print(" ", p)
        return

    n_products, n_snapshots = load_to_supabase(products)
    print(f"Supabase: {n_products} pharmacy_products upsertados, {n_snapshots} price_snapshots guardados")

    record_scrape_run(PHARMACY, len(products), errores, duracion)

    # Sin productos = la fuente cambio de forma. Se sale con error para que el
    # nocturno lo reporte en vez de dejar pasar una corrida vacia.
    if not products:
        print(f"ERROR: {PHARMACY} no devolvio ningun producto; probablemente cambio el sitio.")
        sys.exit(1)


if __name__ == "__main__":
    main()
