"""Diff de precios/stock vs. el día anterior -> mensajes de Telegram.

Dos cosas distintas, en la misma corrida (fase 7 del Orden de construcción):

1. **Alertas de usuario.** Para cada fila de `subscriptions`, compara el
   snapshot de hoy contra el anterior de ese mismo producto y avisa si el
   precio bajó, si repuso stock, o si cruzó el umbral pedido. Máximo un
   mensaje por persona por día: todas sus alertas se agrupan en uno solo
   (sección 7.5 del documento maestro).

2. **Salud del scraping.** Revisa `scrape_runs` y avisa al admin si una
   fuente lleva 3 corridas seguidas sin traer productos. Esto funciona
   aunque no haya ni un suscriptor, y es lo que evita que el sitio se
   quede sirviendo precios viejos en silencio — que es exactamente lo que
   pasó entre el 2026-08-11 y el 2026-09-02.

Nunca inventa datos: si falta el precio de ayer o el de hoy, no se emite
alerta para ese producto (no se asume que "sin dato" significa "sin stock").

Uso:
    python pipeline/alerts.py
    python pipeline/alerts.py --dry-run     # imprime, no envía nada
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
from base import supabase_select  # noqa: E402

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Una fuente con esta cantidad de corridas consecutivas sin productos se
# considera caída (sección 6 del documento maestro).
CORRIDAS_FALLIDAS_PARA_ALERTAR = 3

FUENTES = [
    "fybeca",
    "pharmacys",
    "medicity",
    "cruzazul",
    "economicas",
    # Cola larga por sitemap (ver scrapers/cola_larga.py): un fuente propio
    # para no mezclar su salud con la búsqueda por término -- si una fuente
    # de cola larga trae 0 productos 3 noches seguidas, es señal real de que
    # el sitemap cambió de formato o el sitio empezó a bloquearla, no ruido.
    "fybeca_cola_larga",
    "pharmacys_cola_larga",
    "medicity_cola_larga",
    "cruzazul_cola_larga",
]


def ecuador_today():
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


# --- Telegram -------------------------------------------------------------


def enviar(chat_id, texto, dry_run=False):
    """Envía un mensaje. Si no hay bot configurado, lo imprime y sigue: la
    corrida nocturna no debe caerse por no poder avisar."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if dry_run or not token:
        motivo = "--dry-run" if dry_run else "sin TELEGRAM_BOT_TOKEN"
        print(f"[{motivo}] mensaje para {chat_id}:\n{texto}\n")
        return False
    try:
        resp = requests.post(
            TELEGRAM_API.format(token=token),
            json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=20,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"aviso: no se pudo enviar el mensaje a {chat_id}: {e}")
        return False


# --- 1. Alertas de usuario ------------------------------------------------


def snapshots_de(fecha):
    """Snapshots de una fecha, indexados por pharmacy_product_id."""
    rows = supabase_select(
        "price_snapshots",
        {
            "select": "pharmacy_product_id,precio_usd,en_stock,precio_promocional",
            "fecha": f"eq.{fecha.isoformat()}",
        },
    )
    return {r["pharmacy_product_id"]: r for r in rows}


def precio_efectivo(snap):
    """El precio que realmente paga la persona: el promocional si existe."""
    if snap is None:
        return None
    promo = snap.get("precio_promocional")
    return promo if promo is not None else snap.get("precio_usd")


def alertas_de_usuario(hoy, dry_run=False):
    subs = supabase_select("subscriptions", {"select": "telegram_chat_id,drug_id,tipo,umbral"})
    if not subs:
        print("No hay suscripciones registradas: nada que avisar a usuarios.")
        return 0

    hoy_snaps = snapshots_de(hoy)
    ayer_snaps = snapshots_de(hoy - timedelta(days=1))
    if not hoy_snaps:
        print("No hay snapshots de hoy: no se emiten alertas de usuario.")
        return 0

    drug_ids = sorted({s["drug_id"] for s in subs})
    productos = supabase_select(
        "pharmacy_products",
        {
            "select": "id,drug_id,pharmacy,nombre_en_tienda,url,precio_por_unidad",
            "drug_id": f"in.({','.join(drug_ids)})",
        },
    )
    drugs = supabase_select(
        "drugs",
        {"select": "id,slug,principio_activo,concentracion", "id": f"in.({','.join(drug_ids)})"},
    )
    drug_por_id = {d["id"]: d for d in drugs}

    productos_por_drug = defaultdict(list)
    for p in productos:
        # Los productos con precio por unidad suelta no son comparables con el
        # precio de la caja (ver comentario en db/schema.sql): se excluyen de
        # las alertas igual que la web los excluye del "precio más bajo".
        if p.get("precio_por_unidad"):
            continue
        productos_por_drug[p["drug_id"]].append(p)

    lineas_por_chat = defaultdict(list)
    for sub in subs:
        drug = drug_por_id.get(sub["drug_id"])
        if not drug:
            continue
        nombre_drug = " ".join(filter(None, [drug["principio_activo"], drug.get("concentracion")]))
        for prod in productos_por_drug.get(sub["drug_id"], []):
            hoy_s = hoy_snaps.get(prod["id"])
            ayer_s = ayer_snaps.get(prod["id"])
            if hoy_s is None:
                continue  # sin dato de hoy no se compara nada

            p_hoy = precio_efectivo(hoy_s)
            p_ayer = precio_efectivo(ayer_s)

            if sub["tipo"] == "precio_baja":
                umbral = sub.get("umbral")
                if umbral is not None:
                    # Con umbral, alcanza con que el precio de hoy lo cruce.
                    if p_hoy is not None and float(p_hoy) <= float(umbral):
                        lineas_por_chat[sub["telegram_chat_id"]].append(
                            f"💊 <b>{nombre_drug}</b> en {prod['pharmacy']}: "
                            f"${p_hoy} (bajo tu umbral de ${umbral})"
                            + (f"\n{prod['url']}" if prod.get("url") else "")
                        )
                elif p_hoy is not None and p_ayer is not None and float(p_hoy) < float(p_ayer):
                    lineas_por_chat[sub["telegram_chat_id"]].append(
                        f"💊 <b>{nombre_drug}</b> en {prod['pharmacy']}: "
                        f"${p_ayer} → ${p_hoy}"
                        + (f"\n{prod['url']}" if prod.get("url") else "")
                    )

            elif sub["tipo"] == "repone_stock":
                # Solo el cruce false -> true cuenta como reposición. Si ayer
                # no hay dato, no se asume que estaba agotado.
                if ayer_s is not None and ayer_s.get("en_stock") is False and hoy_s.get("en_stock") is True:
                    lineas_por_chat[sub["telegram_chat_id"]].append(
                        f"📦 <b>{nombre_drug}</b> volvió a haber en {prod['pharmacy']}"
                        + (f" (${p_hoy})" if p_hoy is not None else "")
                        + (f"\n{prod['url']}" if prod.get("url") else "")
                    )

    for chat_id, lineas in lineas_por_chat.items():
        cabecera = f"Novedades de hoy ({hoy.isoformat()}):\n\n"
        enviar(chat_id, cabecera + "\n\n".join(lineas[:20]), dry_run=dry_run)

    print(f"{len(lineas_por_chat)} personas con novedades hoy.")
    return len(lineas_por_chat)


# --- 2. Salud del scraping ------------------------------------------------


def revisar_salud(hoy, dry_run=False):
    """Resumen de la corrida de hoy + aviso si una fuente lleva N corridas
    seguidas sin traer nada. Devuelve la lista de fuentes caídas."""
    resumen = []
    caidas = []
    sin_correr = []

    for fuente in FUENTES:
        runs = supabase_select(
            "scrape_runs",
            {
                "select": "fecha,productos_ok,errores,duracion_segundos",
                "fuente": f"eq.{fuente}",
                "order": "fecha.desc",
                "limit": str(CORRIDAS_FALLIDAS_PARA_ALERTAR),
            },
        )
        if not runs:
            resumen.append(f"• {fuente}: sin corridas registradas")
            sin_correr.append(fuente)
            continue

        ultima = runs[0]
        fecha_ultima = (ultima["fecha"] or "")[:10]
        corrio_hoy = fecha_ultima == hoy.isoformat()
        if not corrio_hoy:
            sin_correr.append(fuente)
        marca = "✅" if (corrio_hoy and ultima["productos_ok"] > 0) else "⚠️"
        resumen.append(
            f"{marca} {fuente}: {ultima['productos_ok']} productos"
            f", {ultima['errores']} errores ({fecha_ultima})"
        )

        fallidas = [r for r in runs if r["productos_ok"] == 0]
        if len(runs) >= CORRIDAS_FALLIDAS_PARA_ALERTAR and len(fallidas) == len(runs):
            caidas.append(fuente)

    admin = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    cuerpo = f"<b>farma-precios · {hoy.isoformat()}</b>\n\n" + "\n".join(resumen)
    if sin_correr:
        cuerpo += f"\n\n🟠 <b>Sin datos de hoy</b>: {', '.join(sin_correr)}"
    if caidas:
        cuerpo += (
            f"\n\n🔴 <b>Fuentes caídas</b> ({CORRIDAS_FALLIDAS_PARA_ALERTAR}"
            f" corridas seguidas sin productos): {', '.join(caidas)}"
        )
    if admin:
        enviar(admin, cuerpo, dry_run=dry_run)
    else:
        print("(sin TELEGRAM_ADMIN_CHAT_ID; resumen solo por consola)")
        print(cuerpo)

    return caidas, sin_correr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No envía nada por Telegram, solo imprime")
    parser.add_argument("--solo-salud", action="store_true", help="Omite las alertas de usuario")
    args = parser.parse_args()

    hoy = ecuador_today()
    if not args.solo_salud:
        alertas_de_usuario(hoy, dry_run=args.dry_run)
    caidas, sin_correr = revisar_salud(hoy, dry_run=args.dry_run)

    # Salir con error si alguna fuente esta caida o no dejo datos de hoy: asi
    # el workflow queda en rojo y llega el aviso de GitHub, aunque el bot de
    # Telegram todavia no este configurado.
    if caidas or sin_correr:
        print(f"\nEstado no saludable. Caidas: {caidas or chr(45)}. Sin datos de hoy: {sin_correr or chr(45)}.")
        sys.exit(1)


if __name__ == "__main__":
    main()
