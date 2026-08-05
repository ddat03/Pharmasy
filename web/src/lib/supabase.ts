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
  precio_usd: number | null;
  precio_promocional: number | null;
  en_stock: boolean | null;
  fecha: string;
};

export async function searchProducts(term: string, limit = 30): Promise<LatestPriceRow[]> {
  const params = new URLSearchParams({
    select: "pharmacy_product_id,pharmacy,nombre_en_tienda,url,drug_id,precio_usd,precio_promocional,en_stock,fecha",
    nombre_en_tienda: `ilike.*${term}*`,
    order: "precio_usd.asc",
    limit: String(limit),
  });
  const resp = await fetch(`${SUPABASE_URL}/rest/v1/latest_prices?${params.toString()}`, {
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
    },
  });
  if (!resp.ok) {
    throw new Error(`Supabase respondió ${resp.status}`);
  }
  return resp.json();
}

export const PHARMACY_LABELS: Record<string, string> = {
  fybeca: "Fybeca",
  pharmacys: "Pharmacys",
  medicity: "Medicity",
  cruzazul: "Cruz Azul",
  economicas: "Farmacias Económicas",
};
