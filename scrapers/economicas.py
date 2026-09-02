"""Scraper de Farmacias Económicas, vía Rappi (ver decisión en
Boveda Farmacia/Entidades/Farmacias Económicas.md — el sitio propio de la
cadena no tiene catálogo funcional).

Limitación importante, a diferencia de las otras 4 cadenas: el `robots.txt`
de Rappi bloquea `/api*`, así que este scraper NO llama ningún endpoint de
API directamente (no se evade el bloqueo). Solo lee el HTML público de
`/tiendas/{slug}`, permitido por robots.txt, y extrae el bloque
`__NEXT_DATA__` (estado inicial de Next.js ya renderizado en esa misma
página). La búsqueda por término (`?query=`) es client-side pura — no
cambia el HTML servido — así que no hay forma respetuosa de buscar por
principio activo; solo se puede leer lo que Rappi decide mostrar en la
portada de cada tienda (unos pocos "pasillos"/aisles con ~15 productos
cada uno). Cobertura parcial por diseño, no un límite de este scraper.

No hay URL de producto individual disponible en HTML público (solo
deeplinks `rappi://`), así que `url` queda como la página de la tienda, no
del producto puntual — no se inventa una URL de producto que no existe.

Uso:
    python scrapers/economicas.py
    python scrapers/economicas.py --dry-run
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from base import (
    BlockedError,
    get_html,
    rate_limit_sleep,
    record_scrape_run,
    save_raw,
    supabase_upsert,
)

PHARMACY = "economicas"
BASE_URL = "https://www.rappi.com.ec"

# Sucursales representativas de Farmacias Económicas en Rappi (distintas
# ciudades). Encontradas por investigación previa (ver bitácora); no hay
# forma respetuosa de listarlas todas dinámicamente sin tocar /api*.
STORE_SLUGS = [
    "8007-farmacias-economicas",  # Tumbaco
    "8013-farmacias-economicas",  # Quito
    "19446-farmacias-economicas",  # Guayaquil
    "10794-farmacias-economicas",  # Cuenca
]

NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def fetch(slug):
    url = f"{BASE_URL}/tiendas/{slug}"
    page_html = get_html(url)
    save_raw(PHARMACY, slug, {"html_len": len(page_html), "slug": slug})
    return page_html


def normalize(page_html, slug):
    """Extrae productos del __NEXT_DATA__ ya renderizado en la página de la
    tienda. Campo no extraído = None, nunca inventado."""
    m = NEXT_DATA_RE.search(page_html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        fallback = data["props"]["pageProps"]["fallback"]
        components = fallback[f"storefront/{slug}"]["store_home_response"]["data"]["components"]
    except (KeyError, ValueError, TypeError):
        return []

    store_url = f"{BASE_URL}/tiendas/{slug}"
    rows = []
    for comp in components:
        resource = comp.get("resource") or {}
        for p in resource.get("products", []) or []:
            external_id = p.get("id")  # ej. "8007_17453", ya único por tienda+producto
            if not external_id:
                continue
            real_price = p.get("real_price")
            price = p.get("price")
            if real_price is not None and price is not None and price < real_price:
                precio_usd = real_price
                precio_promocional = price
            else:
                precio_usd = price if price is not None else real_price
                precio_promocional = None
            is_available = p.get("is_available")
            en_stock = is_available if is_available is not None else p.get("in_stock")
            rows.append(
                {
                    "external_id": str(external_id),
                    "nombre_en_tienda": p.get("name"),
                    "url": store_url,  # no hay URL de producto individual en HTML público
                    "precio_usd": precio_usd,
                    "precio_promocional": precio_promocional,
                    "en_stock": en_stock,
                }
            )
    return rows


def scrape(store_slugs):
    by_external_id = {}
    for i, slug in enumerate(store_slugs, start=1):
        page_html = fetch(slug)
        rows = normalize(page_html, slug)
        for row in rows:
            by_external_id[row["external_id"]] = row
        print(f"[{i}/{len(store_slugs)}] {slug} -> {len(rows)} productos en esta tienda, {len(by_external_id)} acumulados")
        if i < len(store_slugs):
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
    parser.add_argument("--dry-run", action="store_true", help="No escribir a Supabase")
    args = parser.parse_args()

    start = time.monotonic()
    try:
        products = scrape(STORE_SLUGS)
    except BlockedError as e:
        # 403/429: no se evade nunca. Se registra la corrida caida (productos_ok
        # = 0) y se sale con codigo != 0 para que el nocturno la marque fallida.
        print(f"BLOQUEADO: {e}. Marcar economicas como blocked_from_ci y detener. No se evade.")
        if not args.dry_run:
            record_scrape_run(PHARMACY, 0, 1, time.monotonic() - start)
        sys.exit(2)
    except Exception as e:
        print(f"FALLO la corrida de economicas: {e}")
        if not args.dry_run:
            record_scrape_run(PHARMACY, 0, 1, time.monotonic() - start)
        sys.exit(1)

    duracion = time.monotonic() - start
    print(f"\n{len(products)} productos únicos extraídos de {len(STORE_SLUGS)} tiendas en {duracion:.1f}s")

    if args.dry_run:
        print("--dry-run: no se escribe a Supabase. Muestra de 3 productos:")
        for p in products[:3]:
            print(" ", p)
        return

    n_products, n_snapshots = load_to_supabase(products)
    print(f"Supabase: {n_products} pharmacy_products upsertados, {n_snapshots} price_snapshots guardados")

    record_scrape_run(PHARMACY, len(products), 0, duracion)

    # Sin productos = la fuente cambio de forma. Se sale con error para que el
    # nocturno lo reporte en vez de dejar pasar una corrida vacia.
    if not products:
        print(f"ERROR: {PHARMACY} no devolvio ningun producto; probablemente cambio el sitio.")
        sys.exit(1)


if __name__ == "__main__":
    main()
