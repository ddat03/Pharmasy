// Adelanto de productos por categoria, compartido entre el menu del header
// (Layout.astro, renderizado en las 2293 paginas del sitio) y la seccion
// "Categorias" del inicio (index.astro).
//
// Cacheado a nivel de modulo con el mismo patron que getResumen() en
// supabase.ts: sin esto, Layout.astro dispararia getAllDrugs() +
// getAllPricedProductsByDrug() -- la consulta mas pesada del sitio, trae
// TODO el catalogo paginado de a 1000 filas -- una vez por cada una de las
// 2293 paginas del build. Medido hoy mismo con otro dato: sin cache, 217s;
// con cache, 11s. La diferencia acá sería peor, porque esta consulta es más
// pesada que la que se midio entonces.

import { getAllDrugs, getAllPricedProductsByDrug, type Drug } from "./supabase";
import { categoriaDe } from "./categorias";

export type PreviewItem = { nombre: string; precio: number; slug: string };

let previewPromise: Promise<Map<string, PreviewItem[]>> | null = null;

export function getPreviewPorCategoria(): Promise<Map<string, PreviewItem[]>> {
  if (!previewPromise) {
    previewPromise = calcular();
  }
  return previewPromise;
}

async function calcular(): Promise<Map<string, PreviewItem[]>> {
  const [drugs, pricesByDrug] = await Promise.all([getAllDrugs(), getAllPricedProductsByDrug()]);

  const byCategoria = new Map<string, Drug[]>();
  for (const d of drugs) {
    const cat = categoriaDe(d.principio_activo);
    if (!cat) continue;
    if (!byCategoria.has(cat)) byCategoria.set(cat, []);
    byCategoria.get(cat)!.push(d);
  }

  const resultado = new Map<string, PreviewItem[]>();
  for (const [catSlug, drugsDeCategoria] of byCategoria) {
    const items = drugsDeCategoria
      .map((d) => {
        const prices = (pricesByDrug.get(d.id) ?? []).filter((p) => p.precio_usd != null && !p.precio_por_unidad);
        if (prices.length === 0) return null;
        const min = prices.reduce((a, b) => ((b.precio_usd as number) < (a.precio_usd as number) ? b : a));
        return {
          nombre: [d.principio_activo, d.concentracion].filter(Boolean).join(" "),
          precio: min.precio_usd as number,
          slug: d.slug,
        };
      })
      .filter((x): x is PreviewItem => x !== null)
      .sort((a, b) => a.precio - b.precio)
      .slice(0, 8);
    resultado.set(catSlug, items);
  }
  return resultado;
}
