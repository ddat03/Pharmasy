"""Fusiona entradas duplicadas del catálogo maestro `drugs`.

El problema: el normalizador crea una fila de `drugs` por cada variante de
texto que devuelve la IA. "Paracetamol 1g tableta" y "Paracetamol 1gr
tableta" son el mismo medicamento y quedaron como dos páginas distintas,
cada una con una parte de las farmacias. Resultado medido el 2026-09-02:
507 de 873 páginas de medicamento mostraban un solo precio, o sea una
comparación sin nada que comparar.

La causa no es falta de datos, es fragmentación de la clave.

Reglas de agrupación (deliberadamente conservadoras — es preferible dejar
dos páginas separadas que fusionar dos medicamentos distintos y mostrar
una comparación falsa):

  1. Principio activo: minúsculas, sin tildes, y sinónimos conocidos
     mapeados a un nombre canónico (acetaminofén = paracetamol).
  2. Concentración: se parsea a un valor numérico en mg. 1g = 1gr =
     1000mg. Las concentraciones compuestas (120mg/5ml) y las
     combinaciones de varios principios se normalizan como una tupla
     ordenada, nunca se aplanan a un solo número.
  3. Forma farmacéutica: sinónimos evidentes (comprimido = tableta). Una
     forma vacía se absorbe SOLO si el grupo tiene exactamente una forma
     concreta — si hay tableta y cápsula, no hay forma de saber a cuál
     pertenece y se deja sola.

Nunca se fusiona por parecido de texto ni por distancia de edición: si dos
concentraciones no se parsean al mismo valor exacto, son medicamentos
distintos.

Uso:
    python pipeline/fusion_catalogo.py --analizar          # solo mirar
    python pipeline/fusion_catalogo.py --proponer          # escribe la propuesta
    python pipeline/fusion_catalogo.py --aplicar           # ejecuta (pide respaldo antes)
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
from base import supabase_delete, supabase_patch, supabase_select  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
PROPUESTA = BASE_DIR / "db" / "fusion_propuesta.json"
RESPALDO = BASE_DIR / "db" / "fusion_respaldo.json"

# Sinónimos de principio activo. Solo pares donde es el MISMO compuesto con
# dos nombres aceptados, nunca "parecidos" ni familias.
SINONIMOS = {
    "acetaminofen": "paracetamol",
    "acido acetilsalicilico": "aspirina",
    "acido ascorbico": "vitamina c",
    "salbutamol": "albuterol",
    "metamizol": "dipirona",
    "hidroxido de aluminio y magnesio": "hidroxido de aluminio/magnesio",
    "vitamina b1": "tiamina",
    "vitamina b6": "piridoxina",
    "vitamina b12": "cianocobalamina",
    "trimetoprima sulfametoxazol": "sulfametoxazol/trimetoprima",
    "trimetoprima/sulfametoxazol": "sulfametoxazol/trimetoprima",
}

FORMAS = {
    "comprimido": "tableta",
    "comprimidos": "tableta",
    "tabletas": "tableta",
    "tablet": "tableta",
    "gragea": "tableta",
    "grageas": "tableta",
    "capsulas": "capsula",
    "caps": "capsula",
    "jarabes": "jarabe",
    "suspensiones": "suspension",
    "solucion oral": "solucion",
    "gotas orales": "gotas",
    "crema topica": "crema",
    "unguento": "pomada",
    "inyeccion": "inyectable",
    "ampolla": "inyectable",
    "ampollas": "inyectable",
}

UNIDADES_A_MG = {
    "mg": 1.0,
    "mgs": 1.0,
    "g": 1000.0,
    "gr": 1000.0,
    "grs": 1000.0,
    "gramo": 1000.0,
    "gramos": 1000.0,
    "mcg": 0.001,
    "ug": 0.001,
    "µg": 0.001,
    "ui": None,  # unidades internacionales: no convertibles, se compara el número tal cual
    "u": None,
    "%": None,
    "ml": None,
}

# Las concentraciones compuestas escriben la unidad una sola vez al final:
# "50/12.5mg" son 50mg y 12.5mg, no solo 12.5mg. Un patrón que exija unidad
# pegada a cada número se come el primero y hace que 8/12.5, 20/12.5, 40/12.5
# y 50/12.5 se vean idénticos — o sea, fusionaría dosis distintas en una
# misma página. Por eso se captura el grupo entero de números y se le
# reparte la unidad que lo cierra.
GRUPO_UNIDAD = re.compile(
    r"(\d+(?:[.,]\d+)?(?:\s*[/\-+]\s*\d+(?:[.,]\d+)?)*)\s*(mcg|µg|ug|mgs|mg|grs|gr|gramos|gramo|g|ui|u|ml|%)",
    re.I,
)
SEPARADOR = re.compile(r"\s*[/\-+]\s*")


def sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def norm_principio(texto):
    if not texto:
        return ""
    t = sin_tildes(texto).lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = t.replace(" / ", "/").replace(" + ", "/").replace("+", "/")
    return SINONIMOS.get(t, t)


def norm_forma(texto):
    if not texto:
        return ""
    t = sin_tildes(texto).lower().strip()
    t = re.sub(r"\s+", " ", t)
    return FORMAS.get(t, t)


def norm_concentracion(texto):
    """Devuelve una tupla canónica de la concentración, o None si no se
    puede parsear (en cuyo caso se usa el texto crudo y no se fusiona con
    nada que no sea idéntico)."""
    if not texto:
        return ()
    t = sin_tildes(texto).lower().replace(",", ".")
    partes = []
    resto = t
    for numeros, unidad in GRUPO_UNIDAD.findall(t):
        unidad = unidad.lower()
        factor = UNIDADES_A_MG.get(unidad)
        resto = resto.replace(f"{numeros}{unidad}", " ", 1).replace(f"{numeros} {unidad}", " ", 1)
        for numero in SEPARADOR.split(numeros):
            if not numero:
                continue
            valor = float(numero)
            if factor is None:
                # Unidad no convertible (UI, ml, %): se conserva tal cual para
                # que 5ml nunca se confunda con 5mg.
                partes.append((unidad, round(valor, 4)))
            else:
                partes.append(("mg", round(valor * factor, 4)))

    # Todo lo que quede sin consumir y contenga un numero es una parte de la
    # descripcion que distingue al medicamento y que el parser no entiende:
    # "insulina humana 70/30 100UI/mL" no es "insulina humana 100UI/mL", la
    # premezcla 70/30 es otro producto. Se conserva como token opaco para que
    # nunca se fusionen dos cosas cuya diferencia no supimos interpretar.
    sobrante = re.sub(r"[^0-9a-z/.]+", "", resto)
    if any(c.isdigit() for c in sobrante):
        partes.append(("otro", sobrante))

    if not partes:
        return ("raw", re.sub(r"\s+", "", t))
    # El orden se conserva: 5/10mg y 10/5mg son combinaciones distintas.
    return tuple(partes)


def clave(drug):
    return (
        norm_principio(drug.get("principio_activo")),
        norm_concentracion(drug.get("concentracion")),
        norm_forma(drug.get("forma_farmaceutica")),
    )


def cargar():
    drugs = supabase_select(
        "drugs",
        {
            "select": "id,slug,principio_activo,concentracion,forma_farmaceutica,presentacion,es_generico,precio_techo_usd",
            "limit": "5000",
        },
    )
    productos = supabase_select(
        "pharmacy_products",
        {"select": "id,drug_id,pharmacy", "drug_id": "not.is.null", "limit": "10000"},
    )
    por_drug = defaultdict(list)
    for p in productos:
        por_drug[p["drug_id"]].append(p)
    return drugs, por_drug


def agrupar(drugs):
    """Agrupa por (principio, concentracion, forma). Después absorbe las
    entradas de forma vacía SOLO si el (principio, concentracion) tiene
    exactamente una forma concreta."""
    por_clave = defaultdict(list)
    for d in drugs:
        por_clave[clave(d)].append(d)

    formas_por_base = defaultdict(set)
    for (principio, conc, forma) in por_clave:
        if forma:
            formas_por_base[(principio, conc)].add(forma)

    grupos = defaultdict(list)
    for (principio, conc, forma), lista in por_clave.items():
        destino = (principio, conc, forma)
        if not forma:
            candidatas = formas_por_base.get((principio, conc), set())
            if len(candidatas) == 1:
                destino = (principio, conc, next(iter(candidatas)))
        grupos[destino].extend(lista)
    return grupos


def elegir_canonico(lista, por_drug):
    """El canónico es el que más productos reales tiene enganchados; a
    igualdad, el de descripción más completa. Así se conserva la página que
    ya podría estar indexada con más contenido."""
    def puntaje(d):
        return (
            len(por_drug.get(d["id"], [])),
            1 if d.get("forma_farmaceutica") else 0,
            1 if d.get("concentracion") else 0,
            len(d.get("presentacion") or ""),
            -len(d["slug"]),
        )

    return max(lista, key=puntaje)


def construir_propuesta():
    drugs, por_drug = cargar()
    grupos = agrupar(drugs)

    fusiones = []
    for k, lista in grupos.items():
        if len(lista) < 2:
            continue
        canonico = elegir_canonico(lista, por_drug)
        absorbidos = [d for d in lista if d["id"] != canonico["id"]]
        fusiones.append(
            {
                "clave": " | ".join(str(x) for x in k),
                "canonico": {
                    "id": canonico["id"],
                    "slug": canonico["slug"],
                    "nombre": " ".join(
                        filter(None, [canonico["principio_activo"], canonico.get("concentracion"), canonico.get("forma_farmaceutica")])
                    ),
                    "productos": len(por_drug.get(canonico["id"], [])),
                },
                "absorbidos": [
                    {
                        "id": d["id"],
                        "slug": d["slug"],
                        "nombre": " ".join(
                            filter(None, [d["principio_activo"], d.get("concentracion"), d.get("forma_farmaceutica")])
                        ),
                        "productos": len(por_drug.get(d["id"], [])),
                    }
                    for d in absorbidos
                ],
                # Si alguno del grupo tiene precio techo cargado y el canónico
                # no, se conserva ese dato en vez de perderlo al borrar la fila.
                "precio_techo_rescatado": next(
                    (d["precio_techo_usd"] for d in lista if d.get("precio_techo_usd") is not None),
                    None,
                )
                if canonico.get("precio_techo_usd") is None
                else None,
            }
        )

    fusiones.sort(key=lambda f: -(f["canonico"]["productos"] + sum(a["productos"] for a in f["absorbidos"])))
    return drugs, por_drug, fusiones


def resumen(drugs, por_drug, fusiones):
    absorbidos_total = sum(len(f["absorbidos"]) for f in fusiones)
    antes_delgadas = sum(1 for d in drugs if len(por_drug.get(d["id"], [])) <= 1)
    despues = []
    ids_absorbidos = {a["id"] for f in fusiones for a in f["absorbidos"]}
    for d in drugs:
        if d["id"] in ids_absorbidos:
            continue
        total = len(por_drug.get(d["id"], []))
        for f in fusiones:
            if f["canonico"]["id"] == d["id"]:
                total += sum(a["productos"] for a in f["absorbidos"])
        despues.append(total)
    despues_delgadas = sum(1 for n in despues if n <= 1)

    print(f"Catálogo actual:            {len(drugs)} medicamentos")
    print(f"Grupos con duplicados:      {len(fusiones)}")
    print(f"Páginas que se absorben:    {absorbidos_total}")
    print(f"Catálogo después:           {len(drugs) - absorbidos_total} medicamentos")
    print()
    print(f"Páginas con 0-1 precios ANTES:    {antes_delgadas} de {len(drugs)} ({antes_delgadas * 100 // len(drugs)}%)")
    print(
        f"Páginas con 0-1 precios DESPUÉS:  {despues_delgadas} de {len(despues)} "
        f"({despues_delgadas * 100 // max(len(despues), 1)}%)"
    )


def mostrar_ejemplos(fusiones, n=15):
    print(f"\n--- {n} fusiones más grandes ---")
    for f in fusiones[:n]:
        total = f["canonico"]["productos"] + sum(a["productos"] for a in f["absorbidos"])
        print(f"\n  {f['canonico']['nombre']}  ->  {total} productos")
        print(f"    QUEDA:    /{f['canonico']['slug']}  ({f['canonico']['productos']})")
        for a in f["absorbidos"]:
            print(f"    absorbe:  /{a['slug']}  ({a['productos']})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analizar", action="store_true", help="Solo resumen y ejemplos, no escribe nada")
    parser.add_argument("--proponer", action="store_true", help="Escribe db/fusion_propuesta.json")
    parser.add_argument("--aplicar", action="store_true", help="Aplica la propuesta ya escrita")
    parser.add_argument("--ejemplos", type=int, default=15)
    args = parser.parse_args()

    if args.aplicar:
        aplicar()
        return

    drugs, por_drug, fusiones = construir_propuesta()
    resumen(drugs, por_drug, fusiones)
    mostrar_ejemplos(fusiones, args.ejemplos)

    if args.proponer:
        PROPUESTA.write_text(json.dumps(fusiones, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nPropuesta escrita en {PROPUESTA}")
        print("Revisala y despues: python pipeline/fusion_catalogo.py --aplicar")


def aplicar():
    if not PROPUESTA.exists():
        sys.exit("No hay propuesta. Corré primero: python pipeline/fusion_catalogo.py --proponer")
    fusiones = json.loads(PROPUESTA.read_text(encoding="utf-8"))

    # Respaldo antes de tocar nada: el estado completo de drugs y el mapa
    # producto -> drug_id, que es lo único que esta operación destruye.
    drugs = supabase_select("drugs", {"select": "*", "limit": "5000"})
    productos = supabase_select(
        "pharmacy_products", {"select": "id,drug_id", "drug_id": "not.is.null", "limit": "10000"}
    )
    RESPALDO.write_text(
        json.dumps({"drugs": drugs, "pharmacy_products": productos}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Respaldo escrito en {RESPALDO} ({len(drugs)} drugs, {len(productos)} productos)")

    reasignados = 0
    borrados = 0
    redirects = []

    for f in fusiones:
        destino = f["canonico"]["id"]

        # 1. Rescatar el precio techo antes de borrar la fila que lo tenía.
        #    Se usa PATCH y no upsert: un INSERT ... ON CONFLICT exige todas
        #    las columnas NOT NULL de la tabla aunque termine actualizando.
        if f.get("precio_techo_rescatado") is not None:
            supabase_patch("drugs", {"id": f"eq.{destino}"}, {"precio_techo_usd": f["precio_techo_rescatado"]})

        # 2. Reasignar TODOS los productos antes de borrar. El orden importa:
        #    drugs.id tiene ON DELETE SET NULL en pharmacy_products, así que
        #    borrar primero dejaría los productos huérfanos. Un PATCH filtrado
        #    por drug_id mueve todos los de esa entrada en una sola petición.
        for a in f["absorbidos"]:
            movidos = supabase_patch("pharmacy_products", {"drug_id": f"eq.{a['id']}"}, {"drug_id": destino})
            reasignados += a["productos"]

        # 3. Recién ahora borrar las filas absorbidas, y anotar el redirect
        #    para que la URL vieja no muera con 404 si ya estaba indexada.
        for a in f["absorbidos"]:
            supabase_delete("drugs", {"id": f"eq.{a['id']}"})
            borrados += 1
            redirects.append((a["slug"], f["canonico"]["slug"]))

        print(f"  {f['canonico']['slug']}: absorbió {len(f['absorbidos'])} entrada(s)")

    escribir_redirects(redirects)
    print(f"\nListo. {reasignados} productos reasignados, {borrados} entradas de catálogo eliminadas.")


REDIRECTS = BASE_DIR / "web" / "public" / "_redirects"
MARCA_INICIO = "# --- fusiones de catálogo (generado por pipeline/fusion_catalogo.py) ---"
MARCA_FIN = "# --- fin fusiones ---"


def escribir_redirects(pares):
    """Redirects 301 de cada slug absorbido hacia el canónico.

    Cloudflare Pages lee `public/_redirects`. Sin esto, cada página fusionada
    que Google ya hubiera indexado pasaría a devolver 404 — se perdería la
    señal en vez de traspasarla a la página que quedó.
    """
    bloque = [MARCA_INICIO]
    for viejo, nuevo in sorted(pares):
        bloque.append(f"/medicamento/{viejo}/  /medicamento/{nuevo}/  301")
    bloque.append(MARCA_FIN)
    nuevo_bloque = "\n".join(bloque) + "\n"

    previo = REDIRECTS.read_text(encoding="utf-8") if REDIRECTS.exists() else ""
    if MARCA_INICIO in previo and MARCA_FIN in previo:
        ini = previo.index(MARCA_INICIO)
        fin = previo.index(MARCA_FIN) + len(MARCA_FIN) + 1
        contenido = previo[:ini] + nuevo_bloque + previo[fin:]
    else:
        contenido = (previo.rstrip() + "\n\n" if previo.strip() else "") + nuevo_bloque

    REDIRECTS.parent.mkdir(parents=True, exist_ok=True)
    REDIRECTS.write_text(contenido, encoding="utf-8")
    print(f"{len(pares)} redirects 301 escritos en {REDIRECTS}")


if __name__ == "__main__":
    main()
