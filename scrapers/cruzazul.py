"""Scraper de Farmacias Cruz Azul (Grupo Difare).

Plataforma: VTEX. Endpoint de catálogo público, sin auth, no bloqueado por
robots.txt (ver Boveda Farmacia/Entidades/Cruz Azul.md):

    GET https://www.farmaciascruzazul.ec/api/catalog_system/pub/products/search/?ft={término}

Uso:
    python scrapers/cruzazul.py --limit 10            # prueba rápida
    python scrapers/cruzazul.py --terms Losartan,Metformina
    python scrapers/cruzazul.py --all                 # los 194 términos de la semilla
    python scrapers/cruzazul.py --limit 10 --dry-run   # sin escribir a Supabase
"""

import argparse
import csv
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from base import BlockedError, get_json, rate_limit_sleep, save_raw, supabase_insert, supabase_upsert

PHARMACY = "cruzazul"
BASE_URL = "https://www.farmaciascruzazul.ec"
SEARCH_URL = BASE_URL + "/api/catalog_system/pub/products/search/?ft={term}"

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_CSV = BASE_DIR / "db" / "seed_medicamentos.csv"


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
    data = get_json(url)
    save_raw(PHARMACY, term, data)
    return data


def normalize(raw_products):
    """Convierte productos crudos de VTEX en filas para pharmacy_products +
    price_snapshots. Campo no extraído = None, nunca inventado."""
    rows = []
    for prod in raw_products or []:
        url = prod.get("link")
        nombre = prod.get("productName")
        for item in prod.get("items", []) or []:
            external_id = item.get("itemId")
            if not external_id:
                continue
            sellers = item.get("sellers", []) or []
            seller = next((s for s in sellers if s.get("sellerDefault")), sellers[0] if sellers else None)
            if not seller:
                continue
            offer = seller.get("commertialOffer", {}) or {}
            price = offer.get("Price")
            list_price = offer.get("ListPrice")
            if list_price is not None and price is not None and price < list_price:
                precio_usd = list_price
                precio_promocional = price
            else:
                precio_usd = price if price is not None else list_price
                precio_promocional = None
            rows.append(
                {
                    "external_id": str(external_id),
                    "nombre_en_tienda": nombre,
                    "url": url,
                    "precio_usd": precio_usd,
                    "precio_promocional": precio_promocional,
                    "en_stock": offer.get("IsAvailable"),
                }
            )
    return rows


def scrape(terms):
    """Consulta cada término con rate limit, dedupe por external_id."""
    by_external_id = {}
    for i, term in enumerate(terms, start=1):
        raw = fetch(term)
        for row in normalize(raw):
            by_external_id[row["external_id"]] = row
        print(f"[{i}/{len(terms)}] {term} -> {len(by_external_id)} productos únicos acumulados")
        if i < len(terms):
            rate_limit_sleep()
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
        print(f"BLOQUEADO: {e}. Marcar cruzazul como blocked_from_ci y detener. No se evade.")
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
