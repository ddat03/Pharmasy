import { defineConfig } from "astro/config";

// TODO: actualizar site con el dominio real en cuanto se conecte
// Cloudflare Pages (ver Boveda Farmacia/Orden de construcción.md, fase 4).
// Necesario para que el sitemap y las URLs canónicas/OG sean absolutas.
export default defineConfig({
  output: "static",
  site: "https://farmaprecios.pages.dev",
});
