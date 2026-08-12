# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Astro (output: static) desplegado en Cloudflare Pages. Supabase
(PostgreSQL vía PostgREST) es el único backend, consultado directo desde
el navegador con la clave anónima (protegido por Row Level Security, no
por ocultamiento). Sin framework de componentes (no React/Vue) — HTML/CSS
+ un poco de TypeScript vanilla para la búsqueda interactiva. Sin cuentas
de usuario ni login.

## Users

Público general en Ecuador que busca el precio de un medicamento puntual
— no necesariamente un comprador recurrente. Situación: ya sabe qué
medicamento necesita y quiere confirmar/comparar su precio entre varias
cadenas de farmacia antes de comprarlo, para no pagar de más. Trabajo:
encontrar rápido dónde está más barato.

## Product Purpose

Comparador de precios de medicamentos en Ecuador. Agrega precios reales
scrapeados de 5 cadenas de farmacia (Fybeca, Pharmacys, Medicity, Cruz
Azul, Farmacias Económicas) y los presenta buscables y comparables.
Éxito = el usuario encuentra rápido dónde comprar más barato el
medicamento que busca, con información confiable, nunca inventada.

## Positioning

Cataloga precios reales scrapeados directamente de las 5 cadenas más
grandes de Ecuador (no una sola tienda, no precios reportados por
usuarios) y muestra el precio techo oficial del gobierno (Consejo Nacional
de Fijación de Precios, MSP) como referencia — ningún competidor local
conocido hace esto. Servicio gratuito; monetización por publicidad
preparada técnicamente pero no activada.

## Operating Context

- Datos actualizados por scraping automatizado (a programar como corrida
  nocturna vía GitHub Actions).
- Sitio 100% estático (Astro) — sin backend propio más allá de Supabase.
- Precios mostrados exactamente como aparecen en la página de origen de
  cada farmacia. Nunca se calculan, deducen ni convierten (ej. no se
  compara precio por caja contra el precio techo oficial, que es por
  unidad) — principio explícito y no negociable del usuario.

## Capabilities and Constraints

- 873 medicamentos reales en catálogo; 137 con precio techo oficial
  cargado como referencia informativa (nunca comparado matemáticamente
  contra el precio de farmacia).
- 5 cadenas: Fybeca, Pharmacys, Medicity, Cruz Azul, Farmacias Económicas
  (esta última vía su vitrina en Rappi, ya que su sitio propio no tiene
  catálogo funcional — cobertura parcial por diseño, no un bug).
- Presupuesto $0/mes de infraestructura — toda elección técnica debe
  mantenerse dentro de planes gratuitos (Cloudflare Pages, Supabase free
  tier, GitHub Actions).
- Restricción legal/ética dura: nunca dar consejo médico; descargo
  obligatorio visible en cada página. Nunca inventar datos no confirmados.
- El buscador libre (home) todavía no agrupa automáticamente genéricos
  equivalentes por principio activo — eso sí existe en la página dedicada
  por principio activo.

## Brand Commitments

Nombre de trabajo: "Farma Precios Ecuador" — **no definitivo**, el usuario
está abierto a explorar alternativas de naming como parte de este
rediseño. Sin logo ni identidad visual establecida más allá de un emoji 💊
usado como marcador provisional. Sin paleta de marca deliberada (la
versión anterior usó azul/verde de forma funcional, no como decisión de
marca).

## Evidence on Hand

- 873 medicamentos reales con precios reales de las 5 cadenas, en Supabase
  (tabla `drugs` + vista `latest_prices`).
- Logos reales de las 5 cadenas: **por obtener de cada sitio oficial**, no
  generados por IA (son marcas registradas de terceros; uso
  informativo/comparativo, decisión de riesgo ya tomada por el usuario).
- Sin testimonios, sin casos de estudio, sin prensa, sin usuarios reales
  todavía — proyecto nuevo.

## Product Principles

1. Nunca inventar ni calcular datos — todo precio mostrado es exactamente
   el que aparece en la página de origen de esa farmacia.
2. Nunca dar consejo médico — el sitio compara precios/disponibilidad,
   nada más.
3. Costo de infraestructura $0/mes — toda decisión técnica debe respetar
   planes gratuitos.
4. Transparencia sobre limitaciones — cuando un dato no está confirmado o
   no es comparable, se dice explícitamente en vez de ocultarlo o forzar
   una comparación falsa.
5. Scraping respetuoso — nunca evadir bloqueos de los sitios fuente.
