"""Cola larga del catálogo: cubre lo que los scrapers por término (--all,
557 de db/seed_medicamentos.csv) nunca buscan porque no está en esa lista
-- shampoos medicados, cosmética, suplementos de marca, etc.

En vez de adivinar nombres, lee el sitemap.xml que cada sitio ya publica
para ser rastreado (no es evadir nada, es la lista de URLs reales que el
propio sitio invita a leer) y visita productos puntuales de a tandas cada
noche, rotando por los que hace más tiempo no se revisan (ver
db/migracion_catalog_urls.sql y Boveda Farmacia/Conceptos/Cola larga del
catálogo.md).

Medido el 2026-09-04: entre Fybeca, Pharmacys, Medicity y Cruz Azul hay
~40,600 productos reales y la base solo tenía ~5,840 (~14%). A 1 petición
cada 5-10s una vuelta completa tarda semanas, no una noche -- por eso la
rotación por `--budget-minutos` en vez de intentar todo de una vez.

Uso:
    python scrapers/cola_larga.py --pharmacy pharmacys --budget-minutos 50
    python scrapers/cola_larga.py --pharmacy fybeca --budget-minutos 35 --dry-run
    python scrapers/cola_larga.py --pharmacy medicity --solo-descubrir
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

from base import BlockedError, rate_limit_sleep, record_scrape_run, supabase_upsert
from sitemap_common import discover_product_urls, mark_scraped, pick_next_batch, sync_catalog_urls

import fybeca
import vtex_common

# Tiempo promedio real por petición (rate limit 5-10s + latencia): usado
# solo para dimensionar cuántas URLs pedir de la rotación, nunca para
# cortar peticiones a la mitad -- el corte real es por reloj (`budget_seg`).
SEG_POR_PETICION_ESTIMADO = 5

CONFIG = {
    "pharmacys": {
        "platform": "vtex",
        "base_url": "https://www.pharmacys.com.ec",
        "sitemap_index": "https://www.pharmacys.com.ec/sitemap.xml",
        "sitemap_filter": "product-",
    },
    "medicity": {
        "platform": "vtex",
        "base_url": "https://www.farmaciasmedicity.com",
        "sitemap_index": "https://www.farmaciasmedicity.com/sitemap.xml",
        "sitemap_filter": "product-",
    },
    "cruzazul": {
        "platform": "vtex",
        "base_url": "https://www.farmaciascruzazul.ec",
        "sitemap_index": "https://www.farmaciascruzazul.ec/sitemap.xml",
        "sitemap_filter": "product-",
    },
    "fybeca": {
        "platform": "fybeca",
        "base_url": "https://www.fybeca.com",
        "sitemap_index": "https://www.fybeca.com/sitemap_index.xml",
        "sitemap_filter": "-product",
    },
}


def ecuador_today():
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date().isoformat()


def fetch_and_normalize(platform, pharmacy, base_url, url):
    """Devuelve una lista de filas (puede ser vacía si la pagina no trajo
    nada que extraer -- nunca inventa datos)."""
    if platform == "vtex":
        raw = vtex_common.fetch_by_product_url(pharmacy, base_url, url)
        return vtex_common.normalize(raw)
    # fybeca
    page_html = fybeca.fetch_product_page(url)
    row = fybeca.normalize_product_page(page_html, url)
    return [row] if row else []


def load_to_supabase(pharmacy, products):
    """Generico para ambas plataformas: `precio_por_unidad` es propio de
    VTEX (Fybeca no lo distingue), asi que se completa con None si falta,
    en vez de duplicar load_to_supabase por plataforma."""
    pharmacy_products_rows = [
        {
            "pharmacy": pharmacy,
            "external_id": p["external_id"],
            "url": p["url"],
            "nombre_en_tienda": p["nombre_en_tienda"],
            "precio_por_unidad": p.get("precio_por_unidad"),
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
    parser.add_argument("--pharmacy", required=True, choices=sorted(CONFIG.keys()))
    parser.add_argument("--budget-minutos", type=float, default=45, help="Minutos maximos visitando productos (no cuenta el descubrimiento)")
    parser.add_argument("--solo-descubrir", action="store_true", help="Solo sincronizar el sitemap, no visitar productos")
    parser.add_argument("--dry-run", action="store_true", help="No escribir a Supabase")
    args = parser.parse_args()

    cfg = CONFIG[args.pharmacy]
    fuente = f"{args.pharmacy}_cola_larga"
    start = time.monotonic()

    print(f"Descubriendo catalogo real de {args.pharmacy} via sitemap...")
    try:
        urls = discover_product_urls(cfg["sitemap_index"], cfg["sitemap_filter"])
    except BlockedError as e:
        print(f"BLOQUEADO leyendo el sitemap: {e}. No se evade, se detiene.")
        if not args.dry_run:
            record_scrape_run(fuente, 0, 1, time.monotonic() - start)
        sys.exit(2)
    except Exception as e:
        print(f"FALLO el descubrimiento por sitemap de {args.pharmacy}: {e}")
        if not args.dry_run:
            record_scrape_run(fuente, 0, 1, time.monotonic() - start)
        sys.exit(1)

    print(f"Sitemap: {len(urls)} URLs de producto encontradas.")
    if not args.dry_run:
        sync_catalog_urls(args.pharmacy, urls)
    else:
        print("--dry-run: no se sincroniza catalog_urls.")

    if args.solo_descubrir:
        print("--solo-descubrir: no se visita ningun producto.")
        return

    budget_seg = args.budget_minutos * 60
    batch_size = max(1, int(budget_seg // SEG_POR_PETICION_ESTIMADO))
    batch = pick_next_batch(args.pharmacy, batch_size) if not args.dry_run else []
    if args.dry_run:
        # En dry-run catalog_urls no tiene datos propios (no se sincronizo
        # arriba); se toman URLs directo del sitemap recien leido para
        # poder probar el fetch+normalize sin tocar Supabase.
        batch = [{"id": None, "url": u} for u in urls[: min(3, len(urls))]]

    print(f"Visitando hasta {len(batch)} productos (presupuesto {args.budget_minutos} min)...")
    products = []
    scraped_ids = []
    errores = 0
    visit_start = time.monotonic()
    for i, row in enumerate(batch, start=1):
        if time.monotonic() - visit_start >= budget_seg:
            print(f"Presupuesto de {args.budget_minutos} min agotado, se corta aca ({i - 1}/{len(batch)} intentados).")
            break
        try:
            rows = fetch_and_normalize(cfg["platform"], args.pharmacy, cfg["base_url"], row["url"])
        except BlockedError as e:
            print(f"BLOQUEADO: {e}. No se evade, se detiene la tanda de hoy.")
            if row["id"] is not None:
                mark_scraped(scraped_ids)
            if not args.dry_run:
                n_products, n_snapshots = load_to_supabase(args.pharmacy, products) if products else (0, 0)
                print(f"Supabase (parcial): {n_products} productos, {n_snapshots} snapshots")
                record_scrape_run(fuente, len(products), errores + 1, time.monotonic() - start)
            sys.exit(2)
        except Exception as e:
            errores += 1
            print(f"[{i}/{len(batch)}] {row['url']} -> ERROR, se omite: {e}")
            if row["id"] is not None:
                scraped_ids.append(row["id"])  # se marca igual: reintentar un 404 para siempre no ayuda
            if i < len(batch):
                rate_limit_sleep()
            continue

        products.extend(rows)
        if row["id"] is not None:
            scraped_ids.append(row["id"])
        print(f"[{i}/{len(batch)}] {row['url']} -> {len(rows)} fila(s)")
        if i < len(batch):
            rate_limit_sleep()

    duracion = time.monotonic() - start
    print(f"\n{len(products)} productos extraidos, {len(scraped_ids)} URLs visitadas, {errores} errores, {duracion:.1f}s")

    if args.dry_run:
        print("--dry-run: no se escribe a Supabase ni se marca catalog_urls. Muestra de hasta 3 productos:")
        for p in products[:3]:
            print(" ", p)
        return

    if scraped_ids:
        mark_scraped(scraped_ids)
    n_products, n_snapshots = load_to_supabase(args.pharmacy, products) if products else (0, 0)
    print(f"Supabase: {n_products} pharmacy_products upsertados, {n_snapshots} price_snapshots guardados")

    record_scrape_run(fuente, len(products), errores, duracion)


if __name__ == "__main__":
    main()
