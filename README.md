# farma-precios

Comparador de precios de medicamentos en Ecuador. Arquitectura serverless,
$0/mes de infraestructura. Especificación completa en
`comparador-medicamentos-ecuador.md` (carpeta padre del repo). Bitácora del
proyecto en `Boveda Farmacia/` (bóveda de Obsidian).

## Estado

Fase 1 del [Orden de construcción](../Boveda%20Farmacia/Orden%20de%20construcci%C3%B3n.md)
en progreso: esqueleto de repo, esquema de base de datos, y lista semilla de
medicamentos.

## Estructura

Ver sección 5 del documento maestro.

## Secrets necesarios

`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`,
`OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`,
`CLOUDFLARE_API_TOKEN` — configurar en GitHub y Cloudflare cuando se llegue
a las fases que los requieren.
