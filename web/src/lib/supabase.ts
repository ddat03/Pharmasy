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
  "pharmacy_product_id,pharmacy,nombre_en_tienda,url,drug_id,drug_slug,precio_techo_usd,precio_usd,precio_promocional,en_stock,fecha";

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

// Color fijo por cadena (no depende de datos, solo para que el avatar de
// cada farmacia sea reconocible/consistente entre búsquedas).
export const PHARMACY_COLORS: Record<string, string> = {
  fybeca: "#7c3aed",
  pharmacys: "#0e9f6e",
  medicity: "#d97706",
  cruzazul: "#2563eb",
  economicas: "#db2777",
};

export function pharmacyInitials(pharmacy: string): string {
  const label = PHARMACY_LABELS[pharmacy] ?? pharmacy;
  return label
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
