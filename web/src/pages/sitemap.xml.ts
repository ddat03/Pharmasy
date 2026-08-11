// Sitemap generado a mano (en vez de @astrojs/sitemap, que en esta versión
// requiere un hook de Astro que no existe en Astro 4.x — ver
// Boveda Farmacia/Conceptos/Monetización.md). Rutas estáticas conocidas +
// todas las páginas de medicamento/principio activo generadas desde `drugs`.
import { getAllDrugs, slugifyPrincipio } from "../lib/supabase";

export async function GET() {
  const base = import.meta.env.SITE ?? "https://farmaprecios.pages.dev";
  const drugs = await getAllDrugs();
  const principios = new Set(drugs.map((d) => slugifyPrincipio(d.principio_activo)));

  const urls = [
    `${base}/`,
    `${base}/politica-de-privacidad`,
    ...drugs.map((d) => `${base}/medicamento/${d.slug}`),
    ...Array.from(principios).map((p) => `${base}/principio/${p}`),
  ];

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url><loc>${u}</loc></url>`).join("\n")}
</urlset>
`;

  return new Response(xml, {
    headers: { "Content-Type": "application/xml; charset=utf-8" },
  });
}
