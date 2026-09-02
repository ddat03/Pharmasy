// La anon key de Supabase está diseñada para ser pública (queda embebida
// en el bundle del navegador de todas formas): protege el acceso vía Row
// Level Security en la base, no ocultándola. Ver Boveda Farmacia/
// Entidades/Supabase si existe, o db/schema.sql para las policies de RLS.
export const SUPABASE_URL = "https://gpdmxiesodnxiqtxaina.supabase.co";
export const SUPABASE_ANON_KEY = "sb_publishable_hZG3e7oMjLJiCQwsWtYkog_3iPdbxda";

export type LatestPriceRow = {
  pharmacy_product_id: string;
  pharmacy: string;
  nombre_en_tienda: string;
  url: string | null;
  drug_id: string | null;
  drug_slug: string | null;
  precio_techo_usd: number | null;
  precio_usd: number | null;
  precio_promocional: number | null;
  en_stock: boolean | null;
  fecha: string;
  // true cuando el precio es por unidad suelta, no por la presentación
  // completa (ej. Medicity marca productos "esFraccionado" cuya API
  // devuelve precio por tableta individual). Nunca se calcula el precio
  // de caja a partir de este valor — solo se etiqueta para no mostrarlo
  // como si fuera el precio de la caja.
  precio_por_unidad: boolean | null;
};

async function supabaseGet<T>(table: string, params: Record<string, string>): Promise<T> {
  const qs = new URLSearchParams(params);
  const resp = await fetch(`${SUPABASE_URL}/rest/v1/${table}?${qs.toString()}`, {
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
    },
  });
  if (!resp.ok) {
    throw new Error(`Supabase respondió ${resp.status} consultando ${table}`);
  }
  return resp.json();
}

const LATEST_PRICE_COLUMNS =
  "pharmacy_product_id,pharmacy,nombre_en_tienda,url,drug_id,drug_slug,precio_techo_usd,precio_usd,precio_promocional,en_stock,fecha,precio_por_unidad";

export async function searchProducts(term: string, limit = 30): Promise<LatestPriceRow[]> {
  return supabaseGet<LatestPriceRow[]>("latest_prices", {
    select: LATEST_PRICE_COLUMNS,
    nombre_en_tienda: `ilike.*${term}*`,
    order: "precio_usd.asc",
    limit: String(limit),
  });
}

export type Drug = {
  id: string;
  slug: string;
  principio_activo: string;
  concentracion: string | null;
  forma_farmaceutica: string | null;
  presentacion: string | null;
  nombre_comercial: string | null;
  laboratorio: string | null;
  es_generico: boolean;
  precio_techo_usd: number | null;
};

export async function getAllDrugs(): Promise<Drug[]> {
  return supabaseGet<Drug[]>("drugs", {
    select:
      "id,slug,principio_activo,concentracion,forma_farmaceutica,presentacion,nombre_comercial,laboratorio,es_generico,precio_techo_usd",
    order: "principio_activo.asc",
    limit: "2000",
  });
}

export async function getPricesForDrug(drugId: string): Promise<LatestPriceRow[]> {
  return supabaseGet<LatestPriceRow[]>("latest_prices", {
    select: LATEST_PRICE_COLUMNS,
    drug_id: `eq.${drugId}`,
    order: "precio_usd.asc",
  });
}

// Trae TODOS los precios con drug_id asignado en una sola pasada (paginada,
// PostgREST limita cada respuesta a 1000 filas por defecto). Se usa en
// getStaticPaths para no disparar una petición HTTP por cada medicamento del
// catálogo (con 800+ medicamentos eso satura las conexiones concurrentes del
// build y el timeout falla).
export async function getAllPricedProductsByDrug(): Promise<Map<string, LatestPriceRow[]>> {
  const pageSize = 1000;
  let offset = 0;
  const all: LatestPriceRow[] = [];
  for (;;) {
    const page = await supabaseGet<LatestPriceRow[]>("latest_prices", {
      select: LATEST_PRICE_COLUMNS,
      drug_id: "not.is.null",
      order: "drug_id.asc,precio_usd.asc",
      limit: String(pageSize),
      offset: String(offset),
    });
    all.push(...page);
    if (page.length < pageSize) break;
    offset += pageSize;
  }
  const byDrug = new Map<string, LatestPriceRow[]>();
  for (const row of all) {
    if (!row.drug_id) continue;
    const list = byDrug.get(row.drug_id);
    if (list) list.push(row);
    else byDrug.set(row.drug_id, [row]);
  }
  return byDrug;
}

// Cuenta filas sin traerlas: PostgREST devuelve el total en Content-Range
// cuando se pide `count=exact` con un rango vacio.
async function supabaseCount(table: string, params: Record<string, string> = {}): Promise<number | null> {
  const qs = new URLSearchParams({ select: "id", ...params });
  const resp = await fetch(`${SUPABASE_URL}/rest/v1/${table}?${qs.toString()}`, {
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
      Range: "0-0",
      Prefer: "count=exact",
    },
  });
  if (!resp.ok) return null;
  const total = resp.headers.get("content-range")?.split("/")[1];
  const n = Number(total);
  return Number.isFinite(n) ? n : null;
}

export type Resumen = {
  fecha: string | null;
  productosHoy: number | null;
  conPrecioTecho: number | null;
};

// El layout corre una vez por pagina y el sitio genera 1231 paginas: sin
// esta cache el build dispararia la misma consulta mas de mil veces. El
// modulo vive lo que dura el build, asi que alcanza con memorizar la
// promesa.
let resumenPromise: Promise<Resumen> | null = null;

export function getResumen(): Promise<Resumen> {
  if (!resumenPromise) {
    resumenPromise = (async () => {
      const fecha = await getUltimaActualizacion().catch(() => null);
      const [productosHoy, conPrecioTecho] = await Promise.all([
        fecha ? supabaseCount("price_snapshots", { fecha: `eq.${fecha}` }).catch(() => null) : Promise.resolve(null),
        supabaseCount("drugs", { precio_techo_usd: "not.is.null" }).catch(() => null),
      ]);
      return { fecha, productosHoy, conPrecioTecho };
    })();
  }
  return resumenPromise;
}

// Fecha del snapshot de precios mas reciente. Es el unico dato que le dice
// al visitante si lo que esta viendo es de hoy o de hace tres semanas — sin
// esto, un catalogo congelado se ve identico a uno fresco, que es justo lo
// que paso entre el 2026-08-11 y el 2026-09-02.
export async function getUltimaActualizacion(): Promise<string | null> {
  const rows = await supabaseGet<{ fecha: string }[]>("price_snapshots", {
    select: "fecha",
    order: "fecha.desc",
    limit: "1",
  });
  return rows[0]?.fecha ?? null;
}

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

// "2026-09-02" -> "2 de septiembre". Se parsea a mano en vez de con Date()
// porque `new Date("2026-09-02")` se interpreta como UTC y en Ecuador (UTC-5)
// retrocede un dia: mostraria "1 de septiembre" para un dato de hoy.
export function formatFechaLarga(fecha: string): string {
  const [, mes, dia] = fecha.split("-").map(Number);
  const nombreMes = MESES[mes - 1];
  if (!nombreMes || !dia) return fecha;
  return `${dia} de ${nombreMes}`;
}

export function slugifyPrincipio(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export const PHARMACY_LABELS: Record<string, string> = {
  fybeca: "Fybeca",
  pharmacys: "Pharmacys",
  medicity: "Medicity",
  cruzazul: "Cruz Azul",
  economicas: "Farmacias Económicas",
};

// Logos reales de cada cadena (favicon oficial de cada sitio, obtenidos
// respetuosamente — ver Boveda Farmacia/Conceptos/Diseño web.md). Usados
// como marca compacta en cada fila del libro mayor de resultados.
export const PHARMACY_LOGOS: Record<string, string> = {
  fybeca: "/logos/fybeca.png",
  pharmacys: "/logos/pharmacys.png",
  medicity: "/logos/medicity.png",
  cruzazul: "/logos/cruzazul.png",
  economicas: "/logos/economicas.png",
};
