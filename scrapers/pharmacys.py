"""Scraper de Pharmacys (Grupo Difare). Plataforma: VTEX.

Endpoint de catálogo público, sin auth, no bloqueado por robots.txt (ver
Boveda Farmacia/Entidades/Pharmacys.md). Lógica compartida en
vtex_common.py — este archivo solo fija la configuración de la cadena.

Uso:
    python scrapers/pharmacys.py --limit 10
    python scrapers/pharmacys.py --terms Losartan,Metformina
    python scrapers/pharmacys.py --all
    python scrapers/pharmacys.py --limit 10 --dry-run
"""

from vtex_common import run_cli

PHARMACY = "pharmacys"
BASE_URL = "https://www.pharmacys.com.ec"
SEARCH_PATH = "/api/catalog_system/pub/products/search?ft={term}&_from=0&_to=9"

if __name__ == "__main__":
    run_cli(PHARMACY, BASE_URL, SEARCH_PATH)
