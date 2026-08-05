"""Scraper de Farmacias Cruz Azul (Grupo Difare). Plataforma: VTEX.

Endpoint de catálogo público, sin auth, no bloqueado por robots.txt (ver
Boveda Farmacia/Entidades/Cruz Azul.md). Lógica compartida en
vtex_common.py — este archivo solo fija la configuración de la cadena.

Uso:
    python scrapers/cruzazul.py --limit 10
    python scrapers/cruzazul.py --terms Losartan,Metformina
    python scrapers/cruzazul.py --all
    python scrapers/cruzazul.py --limit 10 --dry-run
"""

from vtex_common import run_cli

PHARMACY = "cruzazul"
BASE_URL = "https://www.farmaciascruzazul.ec"
SEARCH_PATH = "/api/catalog_system/pub/products/search/?ft={term}"

if __name__ == "__main__":
    run_cli(PHARMACY, BASE_URL, SEARCH_PATH)
