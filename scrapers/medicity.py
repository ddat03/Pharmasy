"""Scraper de Medicity (Farmaenlace). Plataforma: VTEX.

Endpoint de catálogo público, sin auth, no bloqueado por robots.txt (ver
Boveda Farmacia/Entidades/Medicity.md). Lógica compartida en
vtex_common.py — este archivo solo fija la configuración de la cadena.

Uso:
    python scrapers/medicity.py --limit 10
    python scrapers/medicity.py --terms Losartan,Metformina
    python scrapers/medicity.py --all
    python scrapers/medicity.py --limit 10 --dry-run
"""

from vtex_common import run_cli

PHARMACY = "medicity"
BASE_URL = "https://www.farmaciasmedicity.com"
SEARCH_PATH = "/api/catalog_system/pub/products/search/?ft={term}"

if __name__ == "__main__":
    run_cli(PHARMACY, BASE_URL, SEARCH_PATH)
