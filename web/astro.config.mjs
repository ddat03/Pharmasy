import { defineConfig } from "astro/config";

// Dominio real del deploy en Cloudflare Pages (proyecto "dark-star-3bb3").
// Si se conecta un dominio propio más adelante, actualizar aquí también.
export default defineConfig({
  output: "static",
  site: "https://dark-star-3bb3.pages.dev",
});
