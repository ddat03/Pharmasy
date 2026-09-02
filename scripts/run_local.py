"""Plan B: correr la corrida nocturna desde la PC, no desde GitHub Actions.

Para qué sirve (fase 8 del Orden de construcción): si una cadena empieza a
devolver 403/429 desde los runners de GitHub (IPs de datacenter, fáciles de
bloquear en masa) queda marcada `blocked_from_ci` y sale del workflow. Desde
una conexión doméstica normal suele seguir respondiendo, así que esa cadena
se corre a mano desde acá y sube los datos por la misma pipeline y a la misma
base: no hay un camino de datos paralelo que pueda divergir.

Esto NO evade ningún bloqueo: se respetan el mismo rate limit, el mismo
user-agent identificable y el mismo robots.txt. Es correr el mismo scraper
desde otra red, no disfrazarse para entrar donde dijeron que no.

Uso:
    python scripts/run_local.py --fuente cruzazul
    python scripts/run_local.py --fuente cruzazul --sin-normalizar
    python scripts/run_local.py --todas
    python scripts/run_local.py --fuente fybeca --dry-run
"""

import argparse
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Económicas no acepta --all: lee un set fijo de tiendas de Rappi.
FUENTES = {
    "fybeca": ["--all"],
    "pharmacys": ["--all"],
    "medicity": ["--all"],
    "cruzazul": ["--all"],
    "economicas": [],
}


def correr(descripcion, cmd):
    print(f"\n{'=' * 70}\n{descripcion}\n{'=' * 70}")
    resultado = subprocess.run([sys.executable, *cmd], cwd=BASE_DIR)
    if resultado.returncode != 0:
        print(f"-> terminó con código {resultado.returncode}")
    return resultado.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fuente", choices=sorted(FUENTES), help="Cadena a correr")
    parser.add_argument("--todas", action="store_true", help="Correr las 5 cadenas, una tras otra")
    parser.add_argument("--sin-normalizar", action="store_true", help="No correr el normalizador (no gasta OpenAI)")
    parser.add_argument("--sin-alertas", action="store_true", help="No correr el diff de precios ni el reporte de salud")
    parser.add_argument("--dry-run", action="store_true", help="No escribir nada a Supabase")
    args = parser.parse_args()

    if not args.fuente and not args.todas:
        parser.error("indicá --fuente <cadena> o --todas")

    fuentes = sorted(FUENTES) if args.todas else [args.fuente]
    fallidas = []

    for fuente in fuentes:
        cmd = [f"scrapers/{fuente}.py", *FUENTES[fuente]]
        if args.dry_run:
            cmd.append("--dry-run")
        if correr(f"Scrapeando {fuente}", cmd) != 0:
            fallidas.append(fuente)

    if args.dry_run:
        print("\n--dry-run: no se normaliza ni se alerta (no se escribió nada).")
        return

    if not args.sin_normalizar:
        for fuente in fuentes:
            if fuente in fallidas:
                print(f"\nSe omite la normalización de {fuente}: su scrapeo falló.")
                continue
            correr(f"Normalizando {fuente}", ["pipeline/normalizer.py", "--pharmacy", fuente, "--all"])

    if not args.sin_alertas:
        correr("Alertas y salud", ["pipeline/alerts.py"])

    if fallidas:
        print(f"\nCadenas que fallaron: {', '.join(fallidas)}")
        sys.exit(1)

    print(
        "\nListo. Los datos ya están en Supabase. La web se republica sola en la próxima "
        "corrida nocturna; para publicarla ahora: gh workflow run deploy-web.yml"
    )


if __name__ == "__main__":
    main()
