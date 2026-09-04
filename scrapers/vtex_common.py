"""Lógica compartida por las cadenas que corren sobre VTEX
([[Pharmacys]], [[Medicity]], [[Cruz Azul]] en la bóveda — mismo patrón de
API pública `/api/catalog_system/pub/products/search`, distinto dominio por
cadena). Fybeca (Salesforce Commerce Cloud) y Económicas (vía Rappi) no
comparten esta base porque corren sobre plataformas distintas.
"""

import argparse
import csv
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from base import (
    BlockedError,
    get_json,
    rate_limit_sleep,
    record_scrape_run,
    save_raw,
    supabase_upsert,
)

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


def fetch(pharmacy, base_url, search_path, term):
    url = base_url + search_path.format(term=urllib.parse.quote(term))
    data = get_json(url)
    save_raw(pharmacy, term, data)
    return data


def fetch_by_product_url(pharmacy, base_url, product_url):
    """Para `cola_larga.py`: pide el mismo JSON de catálogo que una búsqueda
    por término, pero para una URL de producto puntual (sacada del sitemap
    del sitio, no adivinada). Confirmado a mano: pedir la misma ruta bajo
    `/api/catalog_system/pub/products/search{ruta}` devuelve el mismo shape
    que `?ft=término`, así que `normalize()` no cambia."""
    path = product_url[len(base_url) :] if product_url.startswith(base_url) else product_url
    url = f"{base_url}/api/catalog_system/pub/products/search{path}"
    data = get_json(url)
    save_raw(pharmacy, path.strip("/").replace("/", "_")[:60], data)
    return data


def normalize(raw_products):
    """Convierte productos crudos de VTEX en filas para pharmacy_products +
    price_snapshots. Campo no extraído = None, nunca inventado."""
    rows = []
    for prod in raw_products or []:
        url = prod.get("link")
        nombre = prod.get("productName")
        # Algunas cadenas (confirmado en Medicity/Farmaenlace) marcan
        # "esFraccionado": ["si"] en productos que se venden también por
        # unidad suelta — para esos, el campo Price/ListPrice de la API es
        # el precio por unidad, no el de la caja completa que describe
        # "productName" (ej. "Con 100 Unidades" a $0.05 = precio por
        # tableta, la caja se vende a $5 en la página real). Nunca se
        # deduce el precio de caja multiplicando: se etiqueta el dato tal
        # como lo entrega la API, para que la web lo muestre como "por
        # unidad" en vez de hacerlo pasar por el precio de la presentación.
        es_fraccionado = (prod.get("esFraccionado") or [None])[0] == "si"
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
                    "precio_por_unidad": es_fraccionado,
                }
            )
    return rows


def scrape(pharmacy, base_url, search_path, terms):
    by_external_id = {}
    errores = []
    for i, term in enumerate(terms, start=1):
        try:
            raw = fetch(pharmacy, base_url, search_path, term)
        except BlockedError:
            raise  # 403/429: nunca se evade, se detiene todo el run
        except Exception as e:
            # Error transitorio (ej. 500 puntual del sitio): se registra y
            # se sigue con el siguiente término en vez de perder toda la
            # corrida por una falla de un solo término.
            errores.append((term, str(e)))
            print(f"[{i}/{len(terms)}] {term} -> ERROR, se omite: {e}")
            if i < len(terms):
                rate_limit_sleep()
            continue
        for row in normalize(raw):
            by_external_id[row["external_id"]] = row
        print(f"[{i}/{len(terms)}] {term} -> {len(by_external_id)} productos únicos acumulados")
        if i < len(terms):
            rate_limit_sleep()
    if errores:
        print(f"\n{len(errores)} términos con error (omitidos, no bloquean la corrida): {[t for t, _ in errores]}")
    return list(by_external_id.values()), len(errores)


def ecuador_today():
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date().isoformat()


def load_to_supabase(pharmacy, products):
    pharmacy_products_rows = [
        {
            "pharmacy": pharmacy,
            "external_id": p["external_id"],
            "url": p["url"],
            "nombre_en_tienda": p["nombre_en_tienda"],
            "precio_por_unidad": p["precio_por_unidad"],
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


def run_cli(pharmacy, base_url, search_path):
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
        products, errores = scrape(pharmacy, base_url, search_path, terms)
    except BlockedError as e:
        # 403/429: no se evade nunca. Se deja constancia en la bitacora (una
        # corrida con productos_ok = 0) y se sale con codigo != 0 para que el
        # workflow nocturno la marque como fallida en vez de pasar en silencio.
        print(f"BLOQUEADO: {e}. Marcar {pharmacy} como blocked_from_ci y detener. No se evade.")
        if not args.dry_run:
            record_scrape_run(pharmacy, 0, 1, time.monotonic() - start)
        sys.exit(2)
    except Exception as e:
        print(f"FALLO la corrida de {pharmacy}: {e}")
        if not args.dry_run:
            record_scrape_run(pharmacy, 0, 1, time.monotonic() - start)
        sys.exit(1)

    duracion = time.monotonic() - start
    print(f"\n{len(products)} productos únicos extraídos de {len(terms)} términos en {duracion:.1f}s")

    if args.dry_run:
        print("--dry-run: no se escribe a Supabase. Muestra de 3 productos:")
        for p in products[:3]:
            print(" ", p)
        return

    n_products, n_snapshots = load_to_supabase(pharmacy, products)
    print(f"Supabase: {n_products} pharmacy_products upsertados, {n_snapshots} price_snapshots guardados")

    record_scrape_run(pharmacy, len(products), errores, duracion)

    # Una corrida que termina sin ningun producto es tecnicamente "exitosa",
    # pero en la practica significa que la fuente cambio de forma. Se sale con
    # error para que el nocturno lo reporte en vez de dejar la tabla vacia.
    if not products:
        print(f"ERROR: {pharmacy} no devolvio ningun producto; probablemente cambio el sitio.")
        sys.exit(1)
