"""Chequea si la última corrida de una fuente en `scrape_runs` quedó
bloqueada (productos_ok = 0), para que el workflow nocturno decida si vale
la pena reintentarla en un runner nuevo (IP nueva de Azure). No reintenta
nada por sí mismo, solo informa: escribe `needs_retry=true|false` en
$GITHUB_OUTPUT si esa variable de entorno existe (paso de GitHub Actions).

Si la fuente ya trajo productos (productos_ok > 0) no hace falta reintentar
-- reintentar igual violaría "scraping respetuoso" (no pegarle a la fuente
sin necesidad).

Uso:
    python pipeline/check_scrape_status.py --fuente economicas
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
from base import supabase_select  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fuente", required=True)
    args = parser.parse_args()

    rows = supabase_select(
        "scrape_runs",
        {
            "fuente": f"eq.{args.fuente}",
            "select": "productos_ok,fecha",
            "order": "fecha.desc",
            "limit": "1",
        },
    )

    if not rows:
        print(f"{args.fuente}: sin corridas registradas todavía, nada que reintentar")
        needs_retry = False
    else:
        productos_ok = rows[0]["productos_ok"]
        needs_retry = productos_ok == 0
        print(f"{args.fuente}: última corrida ({rows[0]['fecha']}) trajo {productos_ok} productos")

    print(f"needs_retry={str(needs_retry).lower()}")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"needs_retry={str(needs_retry).lower()}\n")


if __name__ == "__main__":
    main()
