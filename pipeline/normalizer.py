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
            "es_medicamento": {
                "type": "boolean",
                "description": (
                    "true si el producto es un medicamento/fármaco con principio activo "
                    "farmacológico real. false para pañales, toallas húmedas, champú, "
                    "cosméticos, alimento infantil, higiene, dispositivos, cepillos, etc. "
                    "— cualquier cosa vendida en una farmacia que NO sea un medicamento."
                ),
            },
            "principio_activo": {
                "type": ["string", "null"],
                "description": (
                    "Principio activo en forma genérica estándar (ej. 'Losartan', no "
                    "'Losartán Potásico 50mg Caja x30'). null si es_medicamento es false "
                    "o si no se puede determinar — nunca un string vacío ni texto como "
                    "'null' o ':'."
                ),
            },
            "concentracion": {
                "type": ["string", "null"],
                "description": "Sin espacios entre número y unidad (ej. '50mg', '20/12.5mg'), null si no aparece",
            },
            "forma_farmaceutica": {
                "type": ["string", "null"],
                "description": (
                    "Elige EXACTAMENTE uno de esta lista (singular, minúsculas), el más cercano al "
                    "producto, o null si no se puede inferir: tableta, capsula, jarabe, suspension, "
                    "inyectable, crema, gel, ovulo, gotas, supositorio, parche, polvo, kit. "
                    "'comprimido' y 'comprimidos' cuentan como 'tableta'."
                ),
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
            "es_medicamento",
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
    "ecuatorianas. El catálogo de una farmacia incluye de todo, no solo "
    "medicamentos: pañales, cosméticos, higiene, alimento infantil, etc. "
    "Primero decide es_medicamento con honestidad. Si es false, deja "
    "principio_activo/concentracion/forma_farmaceutica en null — no "
    "inventes un principio activo falso para encajar el producto en el "
    "esquema. Si es true: normaliza el principio activo a su forma "
    "genérica estándar en español (mismo texto exacto para el mismo "
    "principio activo cada vez, ej. siempre 'Enalapril', nunca a veces "
    "'Enalapril' y a veces 'ENALAPRIL' o 'Enalapril Maleato'). "
    "concentracion sin espacios entre número y unidad. forma_farmaceutica: "
    "usa siempre la misma palabra canónica de la lista dada, nunca "
    "sinónimos ni variantes. Nunca inventes un valor: si no puedes "
    "determinar un campo, usa null (el valor JSON null, nunca el string "
    "'null' ni un string vacío). Reporta tu confianza real en la "
    "extracción."
)

# Sinónimos comunes en Ecuador que la IA a veces no normaliza (defensa
# adicional a nivel de código, además del prompt/schema más prescriptivos).
FORMA_SYNONYMS = {
    "comprimido": "tableta",
    "comprimidos": "tableta",
    "comprimido recubierto": "tableta",
    "tabletas": "tableta",
    "tab": "tableta",
    "tabs": "tableta",
    "capsulas": "capsula",
    "cap": "capsula",
    "caps": "capsula",
    "ampolla": "inyectable",
    "vial": "inyectable",
    "ovulos": "ovulo",
}


def is_garbage_text(text):
    """True si `text` no tiene contenido real más allá de puntuación/espacios
    o de las palabras 'null'/'none' escritas como texto literal (el modelo a
    veces devuelve eso en vez de un JSON null real, con variantes como
    '/null', ':null', 'null/' que un simple `in (...)` no detecta)."""
    if not text:
        return True
    letters_only = re.sub(r"[^a-zA-Z]", "", text).lower()
    return letters_only in ("", "null", "none")


def normalize_key(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = FORMA_SYNONYMS.get(text, text)  # solo aplica si el texto completo matchea (forma_farmaceutica)
    text = re.sub(r"\s+", "", text)  # ignora diferencias de espaciado para la clave de dedupe
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


# Se incluye en el hash de ai_cache junto al texto: si el prompt o el
# schema cambian de forma que afecte la extracción, subir esta versión
# invalida el caché viejo automáticamente en vez de arrastrar respuestas
# obtenidas con instrucciones desactualizadas.
PROMPT_VERSION = "v3"


def get_cached_extraction(client, text):
    h = hashlib.sha256(f"{PROMPT_VERSION}:{text}".encode("utf-8")).hexdigest()
    cached = supabase_select("ai_cache", {"select": "response_json", "input_hash": f"eq.{h}"})
    if cached:
        return cached[0]["response_json"]

    resp = client.chat.completions.create(
        model=MODEL,
        # gpt-5-mini es un modelo de razonamiento: sin esto, genera cientos de
        # "reasoning tokens" ocultos (facturados como output, $1/1M) incluso
        # para esta extracción trivial -- confirmado con una prueba real: 704
        # tokens de razonamiento por llamada, ~15x el costo esperado. Con
        # "minimal" + json_schema queda en 0 tokens de razonamiento y
        # respuesta correcta.
        reasoning_effort="minimal",
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
        # es_medicamento = false son productos que ya se evaluaron y se
        # descartaron por no ser medicamentos (panales, champu, biberones).
        # Sin este filtro volvian a la cola todas las noches para siempre: el
        # filtro por drug_id nulo no distingue "todavia sin procesar" de
        # "procesado y descartado". Ver db/migracion_es_medicamento.sql.
        "es_medicamento": "not.is.false",
        "pharmacy": f"eq.{pharmacy}",
    }
    if not run_all:
        params["limit"] = str(limit or 10)
    products = supabase_select("pharmacy_products", params)
    print(f"{len(products)} productos de {pharmacy} sin drug_id por normalizar")

    exact = 0
    nuevos = 0
    baja_confianza = 0
    no_medicamento = 0

    for i, prod in enumerate(products, start=1):
        text = prod["nombre_en_tienda"]
        parsed = get_cached_extraction(client, text)

        if not parsed.get("es_medicamento") or is_garbage_text(parsed.get("principio_activo")):
            no_medicamento += 1
            # Se deja constancia del descarte para no volver a preguntarlo.
            # La respuesta no puede cambiar: `ai_cache` devuelve siempre la
            # misma extraccion para el mismo nombre de producto.
            supabase_upsert(
                "pharmacy_products",
                [
                    {
                        "pharmacy": prod["pharmacy"],
                        "external_id": prod["external_id"],
                        "nombre_en_tienda": prod["nombre_en_tienda"],
                        "es_medicamento": False,
                    }
                ],
                on_conflict="pharmacy,external_id",
            )
            print(f"[{i}/{len(products)}] {text[:60]!r} -> no es medicamento, se descarta")
            continue

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
                    "es_medicamento": True,
                    "match_confidence": round(parsed["confidence"], 2),
                    "match_method": match_method,
                }
            ],
            on_conflict="pharmacy,external_id",
        )
        print(f"[{i}/{len(products)}] {text[:60]!r} -> {parsed['principio_activo']} {parsed['concentracion']} ({match_method}, conf={parsed['confidence']})")

    print(
        f"\nListo. {exact} emparejados a medicamentos existentes, {nuevos} medicamentos nuevos creados, "
        f"{no_medicamento} descartados por no ser medicamentos (no vuelven a procesarse), "
        f"{baja_confianza} con confidence < 0.85 "
        "(revisión manual pendiente)."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pharmacy", required=True, help="cadena a normalizar, ej. cruzazul")
    parser.add_argument("--limit", type=int, help="limitar cantidad de productos")
    parser.add_argument("--all", action="store_true", help="normalizar todos los pendientes")
    args = parser.parse_args()
    normalize_batch(args.pharmacy, limit=args.limit, run_all=args.all)


if __name__ == "__main__":
    main()
