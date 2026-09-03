// Sitemap generado a mano (en vez de @astrojs/sitemap, que en esta versión
// requiere un hook de Astro que no existe en Astro 4.x — ver
// Boveda Farmacia/Conceptos/Monetización.md). Rutas estáticas conocidas +
// todas las páginas de medicamento/principio/categoría generadas desde `drugs`.
import { getAllDrugs, slugifyPrincipio } from "../lib/supabase";
import { CATEGORIAS } from "../lib/categorias";
import { getMarcas } from "../lib/marcas";

// Cloudflare Pages sirve cada página en su ruta con barra final y redirige
// (308) la versión sin barra. Un sitemap que lista la versión sin barra le
// entrega a Google 1223 URLs que redirigen: las marca como "Página con
// redirección" y no indexa la que se le pasó. La barra final tiene que
// coincidir con lo que sirve el servidor y con el `<link rel="canonical">`
// que emite Layout.astro.
function conBarraFinal(url: string): string {
  return url.endsWith("/") ? url : `${url}/`;
}

export async function GET() {
  // Sin SITE configurado el sitemap saldría apuntando a un dominio
  // inexistente, que es peor que no publicarlo: preferimos fallar fuerte.
  const base = import.meta.env.SITE;
  if (!base) {
    throw new Error("Falta `site` en astro.config.mjs: el sitemap necesita el dominio real.");
  }

  const [drugs, marcas] = await Promise.all([getAllDrugs(), getMarcas()]);
  const principios = new Set(drugs.map((d) => slugifyPrincipio(d.principio_activo)));

  const urls = [
    `${base}/`,
    `${base}/acerca`,
    `${base}/contacto`,
    `${base}/marcas`,
    `${base}/politica-de-privacidad`,
    ...CATEGORIAS.map((c) => `${base}/categoria/${c.slug}`),
    ...drugs.map((d) => `${base}/medicamento/${d.slug}`),
    ...Array.from(principios).map((p) => `${base}/principio/${p}`),
    ...marcas.map((m) => `${base}/marca/${m.slug}`),
  ].map(conBarraFinal);

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url><loc>${u}</loc></url>`).join("\n")}
</urlset>
`;

  return new Response(xml, {
    headers: { "Content-Type": "application/xml; charset=utf-8" },
  });
}
