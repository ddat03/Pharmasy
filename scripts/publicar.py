"""Dispara la reconstrucción y publicación del sitio.

Por qué existe: el sitio es estático y se genera leyendo Supabase en el
momento del build. Scrapear actualiza la base, pero NO el sitio — hasta que
no se reconstruye, la web sigue mostrando la foto del build anterior.

El nocturno ya encadena su propio deploy, así que ahí no hace falta. El
agujero son las corridas a mano: el 2026-09-03 un scrapeo manual dejó la
base con 6078 productos mientras el sitio publicado seguía mostrando el
estado de una hora antes, y nadie lo hubiera notado hasta la noche.

Uso:
    python scripts/publicar.py
    python scripts/publicar.py --esperar    # bloquea hasta que termine
"""

import argparse
import shutil
import subprocess
import sys

WORKFLOW = "deploy-web.yml"


def publicar(esperar: bool = False) -> bool:
    """Devuelve True si se disparó el deploy. No lanza excepción: no poder
    publicar no debe tumbar una corrida de datos que sí funcionó."""
    if not shutil.which("gh"):
        print("\nNo se encontró la CLI `gh`, así que no se pudo publicar solo.")
        print("Los datos YA están en Supabase. Para publicarlos:")
        print(f"    gh workflow run {WORKFLOW}")
        return False

    print(f"\nPublicando el sitio (gh workflow run {WORKFLOW})...")
    resultado = subprocess.run(["gh", "workflow", "run", WORKFLOW], capture_output=True, text=True)
    if resultado.returncode != 0:
        print(f"No se pudo disparar el deploy: {(resultado.stderr or '').strip()}")
        print(f"Reintentá a mano con: gh workflow run {WORKFLOW}")
        return False

    print("Deploy disparado. Tarda ~1 minuto en estar en vivo.")

    if esperar:
        # `gh run watch` necesita el id, y el run recién creado tarda unos
        # segundos en aparecer en la lista.
        import time

        time.sleep(10)
        ver = subprocess.run(
            ["gh", "run", "list", "--workflow", WORKFLOW, "--limit", "1", "--json", "databaseId", "--jq", ".[0].databaseId"],
            capture_output=True,
            text=True,
        )
        run_id = (ver.stdout or "").strip()
        if run_id:
            subprocess.run(["gh", "run", "watch", run_id, "--exit-status", "--interval", "10"])
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--esperar", action="store_true", help="Bloquea hasta que el deploy termine")
    args = parser.parse_args()
    sys.exit(0 if publicar(esperar=args.esperar) else 1)


if __name__ == "__main__":
    main()
