"""Descubrimiento de catálogo por sitemap.xml, compartido por
`scrapers/cola_larga.py` para las 4 cadenas con sitio propio (Fybeca,
Pharmacys, Medicity, Cruz Azul -- Económicas no tiene sitio propio, corre
vía Rappi, no aplica).

Un sitemap es una lista de URLs que el propio sitio publica para que los
bots la lean -- lo opuesto a evadir un bloqueo. Leerlo es barato (unos
pocos archivos XML, no miles de peticiones de producto), así que se puede
hacer todas las noches sin afectar el presupuesto de tiempo real, que es
visitar cada producto para sacar su precio (eso sí respeta el rate limit
de 1 petición cada 5-10s, igual que el resto del proyecto).

`catalog_urls` guarda qué URLs existen y cuándo se visitó cada una por
última vez, para que cada noche se tome la tanda más vieja (o nunca vista)
en vez de recorrer el catálogo completo de una sola vez.
"""

import re
import xml.etree.ElementTree as ET

from base import get_html, rate_limit_sleep, supabase_patch, supabase_select, supabase_upsert

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _parse_locs(xml_text):
    root = ET.fromstring(xml_text)
    return [loc.text.strip() for loc in root.iter(f"{SITEMAP_NS}loc") if loc.text]


def discover_product_urls(sitemap_index_url, sub_sitemap_filter):
    """Lee el índice de sitemaps, se queda con los sub-sitemaps de producto
    (identificados por `sub_sitemap_filter`, ej. "product-" o "-product"),
    y devuelve la lista completa de URLs de producto reales del sitio."""
    index_xml = get_html(sitemap_index_url)
    sub_sitemaps = [loc for loc in _parse_locs(index_xml) if sub_sitemap_filter in loc]

    urls = []
    for i, sub_url in enumerate(sub_sitemaps, start=1):
        sub_xml = get_html(sub_url)
        urls.extend(_parse_locs(sub_xml))
        print(f"  sitemap [{i}/{len(sub_sitemaps)}] {sub_url} -> {len(urls)} URLs acumuladas")
        if i < len(sub_sitemaps):
            rate_limit_sleep()
    return urls


def sync_catalog_urls(pharmacy, urls):
    """Upsert de las URLs descubiertas hoy. No toca `last_scraped` de las
    que ya existían -- solo actualiza `last_seen_in_sitemap`. Las nuevas
    entran con `last_scraped` nulo (máxima prioridad para la próxima
    tanda)."""
    if not urls:
        return 0
    rows = [{"pharmacy": pharmacy, "url": u} for u in urls]
    upserted = supabase_upsert("catalog_urls", rows, on_conflict="pharmacy,url")
    return len(upserted)


def pick_next_batch(pharmacy, batch_size):
    """Las `batch_size` URLs que hace más tiempo no se visitan -- nunca
    visitadas (`last_scraped` nulo) primero."""
    rows = supabase_select(
        "catalog_urls",
        {
            "pharmacy": f"eq.{pharmacy}",
            "select": "id,url",
            "order": "last_scraped.asc.nullsfirst",
            "limit": str(batch_size),
        },
    )
    return rows


def mark_scraped(ids):
    """Marca estas filas como visitadas ahora, para que no les toque de
    nuevo hasta que se agote el resto de la rotación. PATCH, no upsert:
    upsert exigiría reenviar pharmacy/url (NOT NULL) aunque no cambien."""
    if not ids:
        return
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    ids_filter = "(" + ",".join(ids) + ")"
    supabase_patch("catalog_urls", {"id": f"in.{ids_filter}"}, {"last_scraped": now})
