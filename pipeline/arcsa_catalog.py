"""Carga el registro sanitario de ARCSA como catálogo de referencia.

Qué resuelve: el normalizador con IA descarta ~858 productos porque su
nombre comercial no declara el principio activo — "Glioten", "Zoltum",
"Genfargrip" no dicen qué tienen adentro, y un modelo no puede inventarlo.
Pero ese dato no hay que inferirlo: es público y oficial. ARCSA publica el
registro sanitario completo de Ecuador, con la marca y sus principios
activos declarados por el propio fabricante.

O sea: dejamos de pagarle a un modelo para que adivine un hecho que el
Estado publica gratis.

Fuente: el reporte "Registros Sanitarios Vigentes" del sistema de consulta
pública (aplicaciones.controlsanitario.gob.ec). Se sirve como una tabla
HTML en latin-1 de ~43 MB, con 15.000+ registros. No requiere clave ni
registro, y no hay robots.txt que lo impida: es justamente un portal de
consulta pública.

Uso:
    python pipeline/arcsa_catalog.py --descargar     # baja el reporte (~43 MB)
    python pipeline/arcsa_catalog.py --construir     # genera db/arcsa_marcas.json
    python pipeline/arcsa_catalog.py --cobertura     # cuántas marcas nuestras cubre
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
from base import USER_AGENT, supabase_select  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
CRUDO = BASE_DIR / "db" / "arcsa_registros.html"  # ~43 MB, no se commitea
SALIDA = BASE_DIR / "db" / "arcsa_marcas.json"

URL_REPORTE = "https://aplicaciones.controlsanitario.gob.ec/publico/consultas/reporte/1"

# Líneas del bloque de principios activos que no nombran un principio: son
# encabezados de la fórmula o códigos de referencia internacional.
RUIDO = re.compile(
    r"^\s*(cada\b|c/u\b|por\s+cada\b|contiene\b|excipientes?\b|dci\b|cas\b|c\.?s\.?p\.?\b|"
    r"equivalente\b|\(?\s*ver\b|formula\b|f[oó]rmula\b|composici[oó]n\b|se\s|exceso\b|"
    r"correspondiente\b|calculado\b|reemplazo\b|granulado\b|potencia\b|sobredosific|"
    r"veh[ií]culo\b|colorante\b|saborizante\b|conservante\b|edulcorante\b|agua\b|"
    r"para\s|en\s|de\s|con\s|un\b|una\b|el\b|la\b|los\b|las\b)",
    re.I,
)

# Frases que el fabricante intercala dentro de la fórmula y que el corte por
# cantidad deja pasar como si fueran un principio. No describen un compuesto.
NO_ES_PRINCIPIO = re.compile(
    r"\b(exceso|correspondiente|calculado|reemplazo|potencia|granulado|preparar|"
    r"suspension oral|equivalente|vehiculo|excipiente|c\.?s\.?p)\b",
    re.I,
)

# Descriptores que aparecen solos en una línea de la fórmula. Son la sal, el
# grado de hidratación o una parte del comprimido — no un principio activo.
SOLO_DESCRIPTOR = {
    "monohidrato", "dihidrato", "trihidrato", "hemihidrato", "sesquihidrato",
    "anhidro", "nucleo", "cubierta", "recubrimiento", "capa", "varia",
    "sodica", "sodico", "calcica", "calcico", "potasica", "potasico",
    "magnesico", "besilato", "maleato", "fumarato", "tartrato", "succinato",
    "clorhidrato", "hidrocloruro", "sulfato", "fosfato", "acetato", "citrato",
    "estearato", "bromhidrato", "mesilato", "base", "polvo", "solvente",
}

# Sales escritas como prefijo: "Hidrocloruro de Sitagliptina" es sitagliptina.
# Quitarlas deja el nombre de la molécula, que es como lo escribe nuestro
# propio catálogo y por lo tanto lo que permite cruzarlos.
PREFIJO_SAL = re.compile(
    r"^(hidrocloruro|clorhidrato|bromhidrato|sulfato|fosfato|acetato|citrato|"
    r"besilato|maleato|fumarato|tartrato|succinato|mesilato|estearato|sal)\s+de\s+",
    re.I,
)

BASURA = re.compile(r"-{3,}|_{3,}")

# El nombre del principio termina donde empieza la cantidad: una corrida de
# puntos, dos puntos, o el primer número con unidad.
CORTA_CANTIDAD = re.compile(r"[.·]{2,}|\?{2,}|:\s|\s\d+[.,]?\d*\s*(mg|g|ml|mcg|ui|%)", re.I)

PARENTESIS = re.compile(r"\([^)]*\)")
NO_LETRAS = re.compile(r"[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ /-]+")


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def norm(texto: str) -> str:
    return re.sub(r"\s+", " ", sin_tildes(texto or "").lower()).strip()


def extraer_principios(bloque: str) -> list[str]:
    """Del texto libre de la fórmula saca solo los nombres de los principios.

    El campo viene como lo escribió el fabricante, con formatos muy
    distintos entre registros:
        "Cada 100 gramos contiene :\\nAciclovir .......... 5,00 g"
        "CADA TABLETA CONTIENE:\\nPARACETAMOL (ACETAMINOFENO) ?..500,0 mg"
    Se corta cada línea donde empieza la cantidad y se descartan las líneas
    que son encabezado o código. Lo que no se pueda interpretar se omite —
    nunca se adivina un principio activo.
    """
    principios: list[str] = []
    for linea in re.split(r"[\n\r+]+", bloque or ""):
        linea = linea.strip()
        if not linea or RUIDO.match(linea):
            continue
        nombre = CORTA_CANTIDAD.split(linea, maxsplit=1)[0]
        nombre = PARENTESIS.sub(" ", nombre)
        nombre = NO_LETRAS.sub(" ", nombre)
        nombre = re.sub(r"\s+", " ", nombre).strip(" -/")
        # Menos de 4 letras no es un principio activo; más de 60 es una
        # frase entera que el corte no supo separar.
        if not (4 <= len(nombre) <= 60):
            continue
        if RUIDO.match(nombre) or NO_ES_PRINCIPIO.search(sin_tildes(nombre)):
            continue
        if BASURA.search(nombre):
            continue
        nombre = PREFIJO_SAL.sub("", nombre).strip()
        if norm(nombre) in SOLO_DESCRIPTOR:
            continue
        if len(nombre) < 4:
            continue
        principios.append(nombre.title())

    # Se deduplica por la PRIMERA palabra, que es la molécula: el mismo
    # compuesto aparece escrito de varias formas entre registros
    # ("Candesartán Cilexetilo", "Candesartan Ciloexetilo") y con distintas
    # sales ("Bisoprolol Fumarato" vs "Bisoprolol"). Se conserva el nombre
    # más corto de cada grupo, que es el de la molécula sin la sal — que es
    # además el que usa nuestro propio catálogo.
    por_molecula: dict[str, str] = {}
    orden: list[str] = []
    for p in principios:
        clave = norm(p).split(" ")[0]
        if len(clave) < 4:
            continue
        if clave not in por_molecula:
            por_molecula[clave] = p
            orden.append(clave)
        elif len(p) < len(por_molecula[clave]):
            por_molecula[clave] = p
    return [por_molecula[k] for k in orden][:5]


def descargar():
    print(f"Descargando el registro sanitario vigente de ARCSA...\n  {URL_REPORTE}")
    CRUDO.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(URL_REPORTE, headers={"User-Agent": USER_AGENT}, timeout=600, stream=True) as r:
        r.raise_for_status()
        total = 0
        with open(CRUDO, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                total += len(chunk)
                print(f"\r  {total / 1_000_000:.1f} MB", end="", flush=True)
    print(f"\nGuardado en {CRUDO}")


def filas():
    if not CRUDO.exists():
        sys.exit("Falta el reporte. Corré primero: python pipeline/arcsa_catalog.py --descargar")
    raw = CRUDO.read_text(encoding="latin-1")
    partes = raw.split("<tr>")
    cabecera = next((p for p in partes if "<th>" in p), None)
    if not cabecera:
        sys.exit("El reporte de ARCSA cambió de formato: no se encontró la fila de encabezados.")
    columnas = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<th>(.*?)</th>", cabecera, re.S)]
    idx = {c: i for i, c in enumerate(columnas)}

    requeridas = ["Nombre_producto", "Marca_producto", "Forma_farmaceutica", "Principios_activos"]
    faltan = [c for c in requeridas if c not in idx]
    if faltan:
        sys.exit(f"El reporte de ARCSA ya no trae estas columnas: {faltan}")

    for parte in partes:
        celdas = [re.sub(r"<[^>]+>", " ", c).strip() for c in re.findall(r"<td>(.*?)</td>", parte, re.S)]
        if len(celdas) < len(columnas):
            continue
        yield {c: celdas[i] for c, i in idx.items()}


def construir():
    por_marca: dict[str, dict] = {}
    total = 0
    con_principios = 0

    for fila in filas():
        total += 1
        marca = (fila.get("Marca_producto") or "").strip()
        if not marca:
            continue
        principios = extraer_principios(fila.get("Principios_activos", ""))
        if not principios:
            continue
        con_principios += 1

        clave = norm(marca)
        entrada = por_marca.setdefault(
            clave,
            {"marca": marca.title(), "principios": [], "formas": [], "registros": []},
        )
        # La misma marca tiene varias fichas (una por presentación) y cada
        # fabricante escribe el principio distinto ("Candesartán Cilexetilo",
        # "Candesartan Ciloexetilo"). Se deduplica por molécula igual que
        # dentro de una ficha, no por texto exacto, o la marca terminaría
        # listando tres veces el mismo compuesto mal escrito.
        for p in principios:
            clave_mol = norm(p).split(" ")[0]
            existente = next((q for q in entrada["principios"] if norm(q).split(" ")[0] == clave_mol), None)
            if existente is None:
                entrada["principios"].append(p)
            elif len(p) < len(existente):
                entrada["principios"][entrada["principios"].index(existente)] = p
        forma = (fila.get("Forma_farmaceutica") or "").strip().title()
        if forma and forma not in entrada["formas"]:
            entrada["formas"].append(forma)
        registro = (fila.get("Numero_registro_sanitario") or "").strip()
        if registro and len(entrada["registros"]) < 3:
            entrada["registros"].append(registro)

    SALIDA.write_text(json.dumps(por_marca, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"Registros leídos:        {total}")
    print(f"Con principios legibles: {con_principios}")
    print(f"Marcas distintas:        {len(por_marca)}")
    print(f"Escrito en {SALIDA} ({SALIDA.stat().st_size / 1_000_000:.1f} MB)")


# --- Cobertura contra nuestras propias marcas -----------------------------

CORTE = {
    "caps", "capsulas", "capsula", "tabs", "tabletas", "tableta", "tab", "comp",
    "comprimidos", "comprimido", "recub", "recubiertas", "jarabe", "suspension",
    "susp", "sol", "solucion", "gotas", "crema", "unguento", "amp", "ampolla",
    "ampollas", "inyectable", "polvo", "sobres", "sachet", "caja", "frasco",
    "unidades", "unidad", "x", "c", "con", "oral", "emulsion", "locion", "spray",
    "gel", "ovulos", "supositorios",
}


def marca_de(nombre: str) -> str:
    """Misma extracción que web/src/lib/marcas.ts, para medir sobre lo mismo
    que el sitio publica."""
    limpio = re.sub(r"[().,/]", " ", sin_tildes(nombre or ""))
    palabras = []
    for bruta in limpio.split():
        palabra = bruta.strip(".")
        if not palabra:
            continue
        if palabra.lower() in CORTE or any(c.isdigit() for c in palabra):
            break
        palabras.append(palabra)
        if len(palabras) == 3:
            break
    return " ".join(palabras).strip()


def cobertura():
    if not SALIDA.exists():
        sys.exit("Falta el catálogo. Corré: python pipeline/arcsa_catalog.py --construir")
    arcsa = json.loads(SALIDA.read_text(encoding="utf-8"))

    productos = supabase_select(
        "pharmacy_products",
        {"select": "nombre_en_tienda,pharmacy", "drug_id": "is.null", "limit": "5000"},
    )
    tiene_dosis = re.compile(r"\d+\s*(mg|mcg|ug|g|gr|ml|ui)\b", re.I)

    nuestras = defaultdict(int)
    for p in productos:
        nombre = p["nombre_en_tienda"] or ""
        if not tiene_dosis.search(nombre):
            continue
        m = marca_de(nombre)
        if len(m) >= 4:
            nuestras[norm(m)] += 1

    encontradas = {m: n for m, n in nuestras.items() if m in arcsa}
    print(f"Marcas nuestras sin principio activo: {len(nuestras)}")
    print(f"Encontradas en ARCSA:                 {len(encontradas)}")
    if nuestras:
        print(f"Cobertura:                            {len(encontradas) * 100 // len(nuestras)}%")
    print(f"Productos que se destraban:           {sum(encontradas.values())}")
    print()
    print("--- ejemplos ---")
    for m, n in sorted(encontradas.items(), key=lambda x: -x[1])[:12]:
        entrada = arcsa[m]
        print(f"  {entrada['marca']:22} -> {', '.join(entrada['principios'][:3])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--descargar", action="store_true")
    parser.add_argument("--construir", action="store_true")
    parser.add_argument("--cobertura", action="store_true")
    args = parser.parse_args()

    if args.descargar:
        descargar()
    if args.construir:
        construir()
    if args.cobertura:
        cobertura()
    if not (args.descargar or args.construir or args.cobertura):
        parser.print_help()


if __name__ == "__main__":
    main()
