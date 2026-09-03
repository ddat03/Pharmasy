"""Borra snapshots de precio más viejos que la ventana de historial.

Por qué: cada corrida nocturna agrega ~2.900 filas a `price_snapshots`, una
por producto vivo. Eso son ~1.060.000 filas al año, creciendo para siempre
sobre un plan gratuito de Supabase de 500 MB. Sin límite, el proyecto se
rompe solo en año y medio o dos — y lo haría en silencio, escribiendo cada
vez más lento hasta que un INSERT falle.

Cuánto se conserva: 90 días, que es exactamente lo que el documento maestro
dice que muestra la web ("gráfico de historial, últimos 90 días"). O sea que
esto no recorta ninguna funcionalidad existente; solo tira lo que ya nadie
mira. Con esta ventana la tabla se estabiliza en ~260.000 filas y deja de
crecer.

Deliberadamente NO borra nada más: `pharmacy_products`, `drugs` y `ai_cache`
son catálogo y caché, no series de tiempo, y perderlos sí costaría dinero o
cobertura.

Uso:
    python pipeline/limpiar_snapshots.py --dry-run
    python pipeline/limpiar_snapshots.py
    python pipeline/limpiar_snapshots.py --dias 180
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
from base import supabase_delete, supabase_select  # noqa: E402

DIAS_POR_DEFECTO = 90


def ecuador_hoy():
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def contar_anteriores(corte):
    """Cuenta aproximada de filas a borrar. PostgREST limita la respuesta, así
    que se pide solo el id y se cuenta lo devuelto: alcanza para decidir si
    hay algo que hacer y para el mensaje del log."""
    filas = supabase_select(
        "price_snapshots",
        {"select": "id", "fecha": f"lt.{corte.isoformat()}", "limit": "1000"},
    )
    return len(filas)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=DIAS_POR_DEFECTO, help="Días de historial a conservar")
    parser.add_argument("--dry-run", action="store_true", help="No borra, solo informa")
    args = parser.parse_args()

    if args.dias < 30:
        sys.exit("Negado: menos de 30 días de historial rompería el gráfico de la web.")

    corte = ecuador_hoy() - timedelta(days=args.dias)
    print(f"Conservando los últimos {args.dias} días. Se borra todo lo anterior a {corte.isoformat()}.")

    pendientes = contar_anteriores(corte)
    if pendientes == 0:
        print("No hay snapshots más viejos que la ventana. Nada que borrar.")
        return

    if args.dry_run:
        print(f"--dry-run: se borrarían al menos {pendientes} filas (el conteo se corta en 1000).")
        return

    # Se repite hasta que no quede nada: un DELETE filtrado puede topar con
    # límites del servidor en tablas grandes, así que se vacía por tandas en
    # vez de asumir que una sola llamada alcanza.
    vueltas = 0
    while True:
        supabase_delete("price_snapshots", {"fecha": f"lt.{corte.isoformat()}"})
        vueltas += 1
        restantes = contar_anteriores(corte)
        if restantes == 0:
            break
        if vueltas >= 20:
            print(f"Aviso: quedan {restantes}+ filas viejas tras {vueltas} tandas. Se reintenta mañana.")
            break

    print(f"Listo en {vueltas} tanda(s). Historial recortado a {args.dias} días.")


if __name__ == "__main__":
    main()
