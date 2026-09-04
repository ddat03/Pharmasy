-- Migración: tabla catalog_urls para el crawl de "cola larga" por sitemap.
--
-- Problema: los scrapers de las 4 cadenas con sitio propio (Fybeca, Pharmacys,
-- Medicity, Cruz Azul) solo buscan los ~557 términos de
-- db/seed_medicamentos.csv. Medido el 2026-09-04 contra los sitemaps reales:
-- ~40,600 productos existen en total entre las 4 cadenas y solo ~5,840
-- estaban en la base (~14% de cobertura) -- faltan categorías enteras como
-- shampoos medicados, cosmética, suplementos de marca, etc.
--
-- Esta tabla registra qué URLs de producto existen en cada sitio (descubierto
-- leyendo su sitemap.xml, que los propios sitios publican para ser rastreados
-- -- no es evadir nada) y cuándo se visitó cada una por última vez, para que
-- scrapers/cola_larga.py pueda rotar de a tandas por noche (ver Boveda
-- Farmacia/Conceptos/Cola larga del catálogo.md) sin recorrer el catálogo
-- completo de una sola vez -- a 1 petición cada 5-10s, un catálogo de miles
-- de productos tarda semanas en recorrerse una vez, no una noche.
--
-- Cómo aplicarla: pegar este archivo entero en el SQL Editor de Supabase
-- (proyecto de farma-precios) y ejecutar. Es seguro re-ejecutarlo.

create table if not exists catalog_urls (
  id uuid primary key default uuid_generate_v4(),
  pharmacy text not null,
  url text not null,
  first_seen timestamptz not null default now(),
  last_seen_in_sitemap timestamptz not null default now(),
  last_scraped timestamptz,
  unique (pharmacy, url)
);

create index if not exists idx_catalog_urls_pharmacy_last_scraped on catalog_urls (pharmacy, last_scraped nulls first);

alter table catalog_urls enable row level security;
-- Sin política de select pública -> solo accesible con la service key,
-- igual que scrape_runs (es bitácora interna, no dato de cara al público).
