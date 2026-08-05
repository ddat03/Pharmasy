"""Catálogo maestro: empareja pharmacy_products sin drug_id con `drugs`.

Flujo (ver Boveda Farmacia/Conceptos/Normalización con IA.md):
  1. Match exacto: si el (principio_activo, concentracion, forma) extraído
     ya existe en `drugs`, se reutiliza ese drug_id.
  2. Si no existe: se extrae la estructura con la API de OpenAI (salida
     estructurada, json_schema), cacheada por hash del texto en `ai_cache`
     para nunca pagar dos veces por el mismo nombre de producto, y se crea
     una fila nueva en `drugs`.
  3. Si `confidence < 0.85`, el producto queda igual enlazado pero marcado
     con esa confianza baja — sirve como cola de revisión manual vía
     `select * from pharmacy_products where match_confidence < 0.85`
     (la página admin dedicada es trabajo futuro, no de esta fase).

Nunca inventa datos: campo no extraído por el modelo = null.

Uso:
    python pipeline/normalizer.py --pharmacy cruzazul --limit 10
    python pipeline/normalizer.py --pharmacy cruzazul --all
"""

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
from base import supabase_insert, supabase_select, supabase_upsert  # noqa: E402

from openai import OpenAI  # noqa: E402

MODEL = "gpt-5-mini"

JSON_SCHEMA = {
    "name": "extraccion_medicamento",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "principio_activo": {
                "type": "string",
                "description": "Principio activo en forma genérica estándar (ej. 'Losartan', no 'Losartán Potásico 50mg Caja x30')",
            },
            "concentracion": {"type": ["string", "null"], "description": "ej. '50mg', null si no aparece"},
            "forma_farmaceutica": {
                "type": ["string", "null"],
                "description": "tableta, capsula, jarabe, suspension, inyectable, crema, ovulo, etc. null si no se puede inferir",
            },
            "presentacion": {"type": ["string", "null"], "description": "ej. 'caja x30', null si no aparece"},
            "es_generico": {
                "type": "boolean",
                "description": "true si la marca es el nombre del principio activo o un laboratorio genérico, false si tiene nombre comercial distintivo",
            },
            "laboratorio": {"type": ["string", "null"], "description": "marca/laboratorio si es identificable"},
            "confidence": {"type": "number", "description": "0-1, tu confianza en esta extracción"},
        },
        "required": [
            "principio_activo",
            "concentracion",
            "forma_farmaceutica",
            "presentacion",
            "es_generico",
            "laboratorio",
            "confidence",
        ],
        "additionalProperties": False,
    },
}

SYSTEM_PROMPT = (
    "Extraes información estructurada de nombres de productos de farmacias "
    "ecuatorianas. Normaliza el principio activo a su forma genérica "
    "estándar en español. Nunca inventes un valor: si no puedes determinar "
    "un campo, usa null. Reporta tu confianza real en la extracción."
)


def normalize_key(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def slugify(*parts):
    text = " ".join(p for p in parts if p)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "medicamento"


def load_existing_drugs():
    rows = supabase_select("drugs", {"select": "id,slug,principio_activo,concentracion,forma_farmaceutica"})
    by_key = {}
    for r in rows:
        key = (normalize_key(r["principio_activo"]), normalize_key(r["concentracion"]), normalize_key(r["forma_farmaceutica"]))
        by_key[key] = r["id"]
    return by_key


def get_cached_extraction(client, text):
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cached = supabase_select("ai_cache", {"select": "response_json", "input_hash": f"eq.{h}"})
    if cached:
        return cached[0]["response_json"]

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Nombre del producto: {text}"},
        ],
        response_format={"type": "json_schema", "json_schema": JSON_SCHEMA},
    )
    parsed = json.loads(resp.choices[0].message.content)
    supabase_upsert("ai_cache", [{"input_hash": h, "response_json": parsed}], on_conflict="input_hash")
    return parsed


def normalize_batch(pharmacy, limit=None, run_all=False):
    client = OpenAI()

    existing_drugs = load_existing_drugs()
    print(f"Catálogo maestro actual: {len(existing_drugs)} medicamentos")

    params = {
        "select": "id,pharmacy,external_id,nombre_en_tienda",
        "drug_id": "is.null",
        "pharmacy": f"eq.{pharmacy}",
    }
    if not run_all:
        params["limit"] = str(limit or 10)
    products = supabase_select("pharmacy_products", params)
    print(f"{len(products)} productos de {pharmacy} sin drug_id por normalizar")

    exact = 0
    nuevos = 0
    baja_confianza = 0

    for i, prod in enumerate(products, start=1):
        text = prod["nombre_en_tienda"]
        parsed = get_cached_extraction(client, text)

        key = (
            normalize_key(parsed["principio_activo"]),
            normalize_key(parsed["concentracion"]),
            normalize_key(parsed["forma_farmaceutica"]),
        )

        if key in existing_drugs:
            drug_id = existing_drugs[key]
            match_method = "exact"
            exact += 1
        else:
            slug = slugify(parsed["principio_activo"], parsed["concentracion"], parsed["forma_farmaceutica"])
            drug_row = {
                "slug": slug,
                "principio_activo": parsed["principio_activo"],
                "concentracion": parsed["concentracion"],
                "forma_farmaceutica": parsed["forma_farmaceutica"],
                "presentacion": parsed["presentacion"],
                "es_generico": parsed["es_generico"],
                "laboratorio": parsed["laboratorio"],
            }
            inserted = supabase_upsert("drugs", [drug_row], on_conflict="slug")
            drug_id = inserted[0]["id"]
            existing_drugs[key] = drug_id
            match_method = "ia"
            nuevos += 1

        if parsed["confidence"] < 0.85:
            baja_confianza += 1

        supabase_upsert(
            "pharmacy_products",
            [
                {
                    "pharmacy": prod["pharmacy"],
                    "external_id": prod["external_id"],
                    "nombre_en_tienda": prod["nombre_en_tienda"],
                    "drug_id": drug_id,
                    "match_confidence": round(parsed["confidence"], 2),
                    "match_method": match_method,
                }
            ],
            on_conflict="pharmacy,external_id",
        )
        print(f"[{i}/{len(products)}] {text[:60]!r} -> {parsed['principio_activo']} {parsed['concentracion']} ({match_method}, conf={parsed['confidence']})")

    print(f"\nListo. {exact} emparejados a medicamentos existentes, {nuevos} medicamentos nuevos creados, {baja_confianza} con confidence < 0.85 (revisión manual pendiente).")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pharmacy", required=True, help="cadena a normalizar, ej. cruzazul")
    parser.add_argument("--limit", type=int, help="limitar cantidad de productos")
    parser.add_argument("--all", action="store_true", help="normalizar todos los pendientes")
    args = parser.parse_args()
    normalize_batch(args.pharmacy, limit=args.limit, run_all=args.all)


if __name__ == "__main__":
    main()
