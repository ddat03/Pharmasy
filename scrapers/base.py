"""Base compartida para todos los scrapers: rate limit, reintentos,
user-agent, guardado de crudos, y carga a Supabase vía PostgREST.

Reglas de scraping respetuoso (ver
Boveda Farmacia/Conceptos/Scraping respetuoso.md):
  - 1 petición cada 5-10s con jitter (rate_limit_sleep).
  - user-agent identificable con contacto.
  - nunca evadir bloqueos activos: 403/429 -> BlockedError, el caller debe
    marcar la fuente blocked_from_ci y detenerse, no reintentar evadiendo.
  - preferir siempre endpoints JSON internos sobre parseo de HTML.
  - campo no extraído = None, nunca inventado.
"""

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

USER_AGENT = (
    "FarmaPreciosEcuadorBot/0.1 "
    "(+https://github.com/ddat03/Pharmasy; comparador de precios de "
    "medicamentos sin fines comerciales; contacto: diegodavidaleman@gmail.com)"
)

RATE_LIMIT_MIN = 5.0
RATE_LIMIT_MAX = 10.0

RAW_DIR = Path(__file__).resolve().parent.parent / "raw"


class BlockedError(Exception):
    """La fuente respondió 403/429. No reintentar ni evadir."""


def rate_limit_sleep():
    time.sleep(RATE_LIMIT_MIN + random.random() * (RATE_LIMIT_MAX - RATE_LIMIT_MIN))


def _get(url, max_retries=3, timeout=15):
    """GET con reintentos. Lanza BlockedError en 403/429 (nunca se evade)."""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        except requests.RequestException as e:
            last_exc = e
            time.sleep(2 * attempt)
            continue
        if resp.status_code in (403, 429):
            raise BlockedError(f"{url} -> {resp.status_code}")
        if resp.status_code in (200, 206):  # VTEX responde 206 en búsquedas paginadas
            return resp
        last_exc = RuntimeError(f"status {resp.status_code}")
        time.sleep(2 * attempt)
    raise RuntimeError(f"fallo tras {max_retries} intentos: {last_exc}")


def get_json(url, max_retries=3, timeout=15):
    resp = _get(url, max_retries=max_retries, timeout=timeout)
    return resp.json()


def get_html(url, max_retries=3, timeout=15):
    resp = _get(url, max_retries=max_retries, timeout=timeout)
    return resp.text


def save_raw(source, name, data):
    out_dir = RAW_DIR / source
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:60]
    path = out_dir / f"{ts}_{safe_name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# --- Supabase (REST/PostgREST), usa SUPABASE_URL + SUPABASE_SERVICE_KEY ---


def _supabase_headers(extra=None):
    key = os.environ["SUPABASE_SERVICE_KEY"]
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def supabase_upsert(table, rows, on_conflict, timeout=30):
    """Upsert (insert o update por conflicto de índice único) vía PostgREST.
    Devuelve las filas resultantes (con sus id)."""
    if not rows:
        return []
    base_url = os.environ["SUPABASE_URL"]
    url = f"{base_url}/rest/v1/{table}?on_conflict={on_conflict}"
    headers = _supabase_headers({"Prefer": "resolution=merge-duplicates,return=representation"})
    resp = requests.post(url, headers=headers, json=rows, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def supabase_select(table, params, timeout=30):
    """GET vía PostgREST. `params` son query params estilo PostgREST, ej.
    {"select": "id,nombre", "drug_id": "is.null", "limit": "50"}."""
    base_url = os.environ["SUPABASE_URL"]
    url = f"{base_url}/rest/v1/{table}"
    resp = requests.get(url, headers=_supabase_headers(), params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def supabase_patch(table, params, patch, timeout=30):
    """UPDATE parcial vía PostgREST, filtrado por `params` (ej.
    {"slug": "eq.<slug>"}). A diferencia de supabase_upsert, no requiere
    incluir columnas NOT NULL que no cambian (Postgres sí las exige en un
    INSERT ... ON CONFLICT DO UPDATE aunque termine resolviendo por UPDATE)."""
    base_url = os.environ["SUPABASE_URL"]
    url = f"{base_url}/rest/v1/{table}"
    resp = requests.patch(url, headers=_supabase_headers(), params=params, json=patch, timeout=timeout)
    resp.raise_for_status()
    return resp.json() if resp.text else []


def supabase_delete(table, params, timeout=30):
    """DELETE vía PostgREST filtrado por `params`, ej. {"id": "eq.<uuid>"}."""
    base_url = os.environ["SUPABASE_URL"]
    url = f"{base_url}/rest/v1/{table}"
    resp = requests.delete(url, headers=_supabase_headers(), params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json() if resp.text else []


def supabase_insert(table, rows, timeout=30):
    if not rows:
        return []
    base_url = os.environ["SUPABASE_URL"]
    url = f"{base_url}/rest/v1/{table}"
    headers = _supabase_headers({"Prefer": "return=representation"})
    resp = requests.post(url, headers=headers, json=rows, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
