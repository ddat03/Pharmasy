// Páginas por marca comercial.
//
// Por qué existen: el catálogo maestro se organiza por principio activo, y
// eso deja afuera a los productos cuyo nombre comercial no declara qué
// tienen adentro (Glioten, Cardiol, Zoltum). El normalizador los descarta —
// no puede inventar un principio activo que el nombre no dice — y quedan
// invisibles para Google aunque el buscador del sitio sí los encuentre.
//
// Son búsquedas de mucho volumen: en Ecuador se receta bastante por marca,
// así que quien tiene algo agudo escribe "Genfargrip", no "paracetamol
// clorfenamina fenilefrina". Una página por marca convierte 500 productos
// muertos en superficie indexable, sin gastar un centavo de IA: el dato ya
// está, solo hay que agruparlo.
//
// Cuando ARCSA esté cargado (ver pipeline/arcsa_catalog.py) estas marcas se
// van a poder enlazar con su principio activo, y ahí aparece la función que
// de verdad justifica un comparador: "buscabas Apronax a $8, el mismo
// naproxeno genérico está $2".

import { SUPABASE_URL, SUPABASE_ANON_KEY, type LatestPriceRow } from "./supabase";

// Un nombre con dosis es, casi siempre, un fármaco. Sin esta señal entran
// pañales, preservativos y bebidas hidratantes — que no son lo que este
// sitio compara.
const TIENE_DOSIS = /\d+\s*(mg|mcg|ug|g|gr|ml|ui)\b/i;

const NO_ES_FARMACO =
  /pa[ñn]al|toalla|shampoo|champ[uú]|jab[oó]n|preservativ|biber[oó]n|leche|crema dental|cepillo|desodorante|papel|algod[oó]n|gel antibac|alcohol|mascarilla|guante|term[oó]metro|bebida/i;

// Palabras que marcan el fin del nombre comercial y el comienzo de la
// descripción de la presentación.
const CORTE = new Set([
  "caps", "capsulas", "capsula", "tabs", "tabletas", "tableta", "tab", "comp",
  "comprimidos", "comprimido", "recub", "recubiertas", "jarabe", "suspension",
  "susp", "sol", "solucion", "gotas", "crema", "unguento", "amp", "ampolla",
  "ampollas", "inyectable", "polvo", "sobres", "sachet", "caja", "frasco",
  "unidades", "unidad", "x", "c", "con", "oral", "emulsion", "locion", "spray",
  "gel", "ovulos", "supositorios",
]);

function sinTildes(texto: string): string {
  return texto.normalize("NFKD").replace(/[̀-ͯ]/g, "");
}

/** Extrae el nombre comercial: las primeras palabras hasta que aparece una
 *  forma farmacéutica o un número. Máximo 3 palabras — algunas marcas son
 *  compuestas ("Minart Am", "La Santé"). */
export function extraerMarca(nombre: string): string {
  const limpio = sinTildes(nombre).replace(/[().,/]/g, " ");
  const palabras: string[] = [];
  for (const bruta of limpio.split(/\s+/)) {
    const palabra = bruta.replace(/^\.+|\.+$/g, "");
    if (!palabra) continue;
    if (CORTE.has(palabra.toLowerCase()) || /\d/.test(palabra)) break;
    palabras.push(palabra);
    if (palabras.length === 3) break;
  }
  return palabras.join(" ").trim();
}

export function slugMarca(marca: string): string {
  return sinTildes(marca)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export type Marca = {
  slug: string;
  nombre: string;
  productos: LatestPriceRow[];
  cadenas: string[];
  desde: number | null;
};

const COLUMNAS =
  "pharmacy_product_id,pharmacy,nombre_en_tienda,url,drug_id,drug_slug,precio_techo_usd,precio_usd,precio_promocional,en_stock,fecha,precio_por_unidad";

let marcasPromise: Promise<Marca[]> | null = null;

/** Productos sin principio activo asignado, agrupados por nombre comercial.
 *  Cacheado a nivel de módulo: el build genera cientos de páginas y esto se
 *  consulta una sola vez. */
export function getMarcas(): Promise<Marca[]> {
  if (!marcasPromise) {
    marcasPromise = cargarMarcas();
  }
  return marcasPromise;
}

async function cargarMarcas(): Promise<Marca[]> {
  const pageSize = 1000;
  let offset = 0;
  const filas: LatestPriceRow[] = [];
  for (;;) {
    const qs = new URLSearchParams({
      select: COLUMNAS,
      drug_id: "is.null",
      limit: String(pageSize),
      offset: String(offset),
    });
    const resp = await fetch(`${SUPABASE_URL}/rest/v1/latest_prices?${qs.toString()}`, {
      headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${SUPABASE_ANON_KEY}` },
    });
    if (!resp.ok) throw new Error(`Supabase respondió ${resp.status} consultando latest_prices`);
    const page: LatestPriceRow[] = await resp.json();
    filas.push(...page);
    if (page.length < pageSize) break;
    offset += pageSize;
  }

  const porSlug = new Map<string, Marca>();
  for (const fila of filas) {
    const nombre = fila.nombre_en_tienda ?? "";
    if (!TIENE_DOSIS.test(nombre) || NO_ES_FARMACO.test(nombre)) continue;
    if (fila.precio_usd == null) continue;

    const marca = extraerMarca(nombre);
    // Menos de 4 letras casi nunca es una marca; suele ser ruido del nombre.
    if (marca.length < 4) continue;

    const slug = slugMarca(marca);
    if (!slug) continue;

    const existente = porSlug.get(slug);
    if (existente) {
      existente.productos.push(fila);
    } else {
      porSlug.set(slug, { slug, nombre: marca, productos: [fila], cadenas: [], desde: null });
    }
  }

  const marcas: Marca[] = [];
  for (const marca of porSlug.values()) {
    marca.productos.sort((a, b) => (a.precio_usd ?? Infinity) - (b.precio_usd ?? Infinity));
    marca.cadenas = Array.from(new Set(marca.productos.map((p) => p.pharmacy)));
    // Mismo criterio que el resto del sitio: un precio por unidad suelta no
    // es comparable con el de una caja, así que no puede ser el "desde".
    const comparables = marca.productos.filter((p) => !p.precio_por_unidad && p.precio_usd != null);
    marca.desde = comparables.length ? Math.min(...comparables.map((p) => p.precio_usd as number)) : null;
    marcas.push(marca);
  }

  marcas.sort((a, b) => b.cadenas.length - a.cadenas.length || b.productos.length - a.productos.length);
  return marcas;
}
