import { defineConfig } from "astro/config";

// Dominio propio, conectado al proyecto "dark-star-3bb3" de Cloudflare Pages.
// De acá salen el <link rel="canonical"> de cada página, los og:url y todas
// las URLs del sitemap: cambiarlo acá los cambia en los 1557 lados a la vez.
//
// Se usa el hostname con www y no la raíz porque www se sirve con un CNAME,
// que es un registro DNS estándar y se comporta igual en todos los
// proveedores. La raíz necesita un ALIAS —un parche no estándar, ya que el
// DNS prohíbe un CNAME en el ápex— y el de Porkbun dio problemas. Para
// Google las dos son equivalentes; lo que importa es elegir una sola y que
// el resto redirija (ver public/_redirects).
export default defineConfig({
  output: "static",
  site: "https://www.farmapreciosec.com",
});
