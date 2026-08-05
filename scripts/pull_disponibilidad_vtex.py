"""Consulta respetuosa de disponibilidad real contra las 3 cadenas VTEX
(Pharmacys, Medicity, Cruz Azul) para reconstruir la semilla de medicamentos
a partir de lo que realmente se vende, en vez de solo conocimiento
farmacológico genérico.

Reglas de scraping respetuoso aplicadas (ver
Boveda Farmacia/Conceptos/Scraping respetuoso.md):
- 1 petición por fuente cada 5-10s con jitter (se logra consultando las 3
  cadenas casi en simultáneo por término, y esperando entre términos).
- User-agent identificable con contacto.
- Nunca evadir bloqueos: si una cadena responde 403/429, se detiene esa
  cadena para el resto de la corrida y se reporta al final.
- Campo no extraído = None -> se guarda vacío, nunca inventado.

Uso: python scripts/pull_disponibilidad_vtex.py
Salida: db/disponibilidad_real_vtex.csv + raw/*.json (crudos, no versionados)
"""

import csv
import json
import random
import time
import urllib.parse
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_CSV = BASE_DIR / "db" / "seed_medicamentos.csv"
OUT_CSV = BASE_DIR / "db" / "disponibilidad_real_vtex.csv"
RAW_DIR = BASE_DIR / "raw" / "disponibilidad_vtex"

HEADERS = {
    "User-Agent": (
        "FarmaPreciosEcuadorBot/0.1 "
        "(+https://github.com/ddat03/Pharmasy; investigacion de precios "
        "de medicamentos, sin fines comerciales; contacto: "
        "diegodavidaleman@gmail.com)"
    )
}

PHARMACIES = {
    "pharmacys": "https://www.pharmacys.com.ec/api/catalog_system/pub/products/search?ft={term}&_from=0&_to=9",
    "medicity": "https://www.farmaciasmedicity.com/api/catalog_system/pub/products/search/?ft={term}",
    "cruzazul": "https://www.farmaciascruzazul.ec/api/catalog_system/pub/products/search/?ft={term}",
}


def load_unique_terms():
    terms = []
    seen = set()
    with open(SEED_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row["principio_activo"].strip()
            if "(" in raw:  # entradas no-farmacológicas como el kit H. pylori
                continue
            term = raw.replace("/", " ")
            if term not in seen:
                seen.add(term)
                terms.append((raw, term))
    return terms


def query(pharmacy, url_template, term):
    url = url_template.format(term=urllib.parse.quote(term))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        return None, f"error de red: {e}"
    if resp.status_code in (403, 429):
        return None, f"bloqueado ({resp.status_code})"
    if resp.status_code not in (200, 206):  # VTEX responde 206 (Partial Content) en búsquedas paginadas
        return None, f"status {resp.status_code}"
    try:
        return resp.json(), None
    except ValueError:
        return None, "respuesta no-JSON"


def extract_rows(pharmacy, original_term, data):
    rows = []
    if not isinstance(data, list):
        return rows
    for prod in data:
        try:
            items = prod.get("items", [])
            price = None
            list_price = None
            if items:
                sellers = items[0].get("sellers", [])
                if sellers:
                    offer = sellers[0].get("commertialOffer", {})
                    price = offer.get("Price")
                    list_price = offer.get("ListPrice")
            link_text = prod.get("linkText", "")
            rows.append(
                {
                    "principio_activo_buscado": original_term,
                    "farmacia": pharmacy,
                    "producto_nombre": prod.get("productName", ""),
                    "marca": prod.get("brand", ""),
                    "precio": price if price is not None else "",
                    "precio_lista": list_price if list_price is not None else "",
                    "categorias": "|".join(prod.get("categories", []) or []),
                    "linkText": link_text,
                }
            )
        except Exception:
            continue
    return rows


DOMAIN_FOR_URL = {
    "pharmacys": "www.pharmacys.com.ec",
    "medicity": "www.farmaciasmedicity.com",
    "cruzazul": "www.farmaciascruzazul.ec",
}


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    terms = load_unique_terms()
    print(f"Total de términos únicos a consultar: {len(terms)}")

    blocked = set()
    all_rows = []
    errors = []

    for i, (original_term, search_term) in enumerate(terms, start=1):
        for pharmacy, url_template in PHARMACIES.items():
            if pharmacy in blocked:
                continue
            data, err = query(pharmacy, url_template, search_term)
            if err:
                errors.append((original_term, pharmacy, err))
                if "bloqueado" in err:
                    blocked.add(pharmacy)
                    print(f"[{i}/{len(terms)}] {pharmacy}: BLOQUEADO, se excluye del resto de la corrida")
                continue
            rows = extract_rows(pharmacy, original_term, data)
            for r in rows:
                r["url"] = f"https://{DOMAIN_FOR_URL[pharmacy]}/{r['linkText']}/p" if r["linkText"] else ""
            all_rows.extend(rows)
            raw_path = RAW_DIR / f"{i:03d}_{pharmacy}_{search_term[:40].replace(' ', '_')}.json"
            raw_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            time.sleep(0.8 + random.random() * 0.7)  # pequeño respiro entre las 3 cadenas del mismo término

        print(f"[{i}/{len(terms)}] {original_term} -> {sum(1 for r in all_rows if r['principio_activo_buscado'] == original_term)} productos encontrados hasta ahora")

        if i < len(terms):
            time.sleep(5 + random.random() * 4)  # 5-9s de jitter entre términos, por fuente

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "principio_activo_buscado",
            "farmacia",
            "producto_nombre",
            "marca",
            "precio",
            "precio_lista",
            "categorias",
            "url",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    print(f"\nListo. {len(all_rows)} filas de disponibilidad real guardadas en {OUT_CSV}")
    print(f"Cadenas bloqueadas durante la corrida: {blocked or 'ninguna'}")
    print(f"Errores no bloqueantes: {len(errors)}")
    if errors:
        for term, pharmacy, err in errors[:20]:
            print(f"  - {term} / {pharmacy}: {err}")


if __name__ == "__main__":
    main()
