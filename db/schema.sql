-- Esquema de base de datos (Supabase / PostgreSQL)
-- Ver sección 6 del documento maestro comparador-medicamentos-ecuador.md

create extension if not exists pg_trgm;
create extension if not exists "uuid-ossp";

-- CREATE TYPE no soporta IF NOT EXISTS en Postgres; se envuelve en DO para
-- que el script completo sea seguro de re-ejecutar.
do $$ begin
  create type pharmacy_enum as enum (
    'fybeca', 'pharmacys', 'medicity', 'cruzazul', 'economicas'
  );
exception when duplicate_object then null;
end $$;

do $$ begin
  create type match_method_enum as enum ('exact', 'ia', 'manual');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type subscription_type_enum as enum ('precio_baja', 'repone_stock');
exception when duplicate_object then null;
end $$;

-- Catálogo maestro.
create table if not exists drugs (
  id uuid primary key default uuid_generate_v4(),
  slug text unique not null,
  principio_activo text not null,
  concentracion text,
  forma_farmaceutica text,
  presentacion text,
  nombre_comercial text,
  laboratorio text,
  registro_sanitario text,          -- ARCSA
  es_generico boolean not null default false,
  precio_techo_usd numeric(10, 2),
  fecha_precio_techo date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_drugs_principio_activo on drugs using gin (principio_activo gin_trgm_ops);
create index if not exists idx_drugs_nombre_comercial on drugs using gin (nombre_comercial gin_trgm_ops);
create index if not exists idx_drugs_registro_sanitario on drugs (registro_sanitario);

-- Producto de una cadena de farmacia, emparejado a un drug del catálogo maestro.
create table if not exists pharmacy_products (
  id uuid primary key default uuid_generate_v4(),
  drug_id uuid references drugs (id) on delete set null,
  pharmacy pharmacy_enum not null,
  external_id text not null,
  url text,
  nombre_en_tienda text not null,
  match_confidence numeric(3, 2) check (match_confidence >= 0 and match_confidence <= 1),
  match_method match_method_enum,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (pharmacy, external_id)
);

create index if not exists idx_pharmacy_products_drug_id on pharmacy_products (drug_id);

-- Una fila por producto por día.
create table if not exists price_snapshots (
  id uuid primary key default uuid_generate_v4(),
  pharmacy_product_id uuid not null references pharmacy_products (id) on delete cascade,
  fecha date not null,
  precio_usd numeric(10, 2),
  en_stock boolean,
  precio_promocional numeric(10, 2),
  created_at timestamptz not null default now(),
  unique (pharmacy_product_id, fecha)
);

create index if not exists idx_price_snapshots_fecha on price_snapshots (fecha);
create index if not exists idx_price_snapshots_pharmacy_product_fecha on price_snapshots (pharmacy_product_id, fecha);

-- Suscripciones a alertas por Telegram.
create table if not exists subscriptions (
  id uuid primary key default uuid_generate_v4(),
  telegram_chat_id text not null,
  drug_id uuid not null references drugs (id) on delete cascade,
  tipo subscription_type_enum not null,
  umbral numeric(10, 2),
  created_at timestamptz not null default now(),
  unique (telegram_chat_id, drug_id, tipo)
);

create index if not exists idx_subscriptions_drug_id on subscriptions (drug_id);

-- Bitácora de corridas de scraping.
create table if not exists scrape_runs (
  id uuid primary key default uuid_generate_v4(),
  fuente text not null,
  fecha timestamptz not null default now(),
  productos_ok integer not null default 0,
  errores integer not null default 0,
  duracion_segundos numeric(10, 2)
);

create index if not exists idx_scrape_runs_fuente_fecha on scrape_runs (fuente, fecha desc);

-- Caché de normalización con IA: nunca pagar dos veces la misma pregunta.
create table if not exists ai_cache (
  id uuid primary key default uuid_generate_v4(),
  input_hash text unique not null,
  response_json jsonb not null,
  created_at timestamptz not null default now()
);

-- Clicks salientes hacia cada farmacia (preparación de monetización, sección 7.6).
create table if not exists outbound_clicks (
  id uuid primary key default uuid_generate_v4(),
  drug_id uuid references drugs (id) on delete set null,
  pharmacy pharmacy_enum not null,
  fecha timestamptz not null default now()
);

create index if not exists idx_outbound_clicks_drug_pharmacy on outbound_clicks (drug_id, pharmacy);

-- Row Level Security: lectura pública solo en drugs, pharmacy_products,
-- price_snapshots. Escritura únicamente con service key (que hace bypass de RLS).
alter table drugs enable row level security;
alter table pharmacy_products enable row level security;
alter table price_snapshots enable row level security;
alter table subscriptions enable row level security;
alter table scrape_runs enable row level security;
alter table ai_cache enable row level security;
alter table outbound_clicks enable row level security;

drop policy if exists "lectura publica drugs" on drugs;
create policy "lectura publica drugs" on drugs for select using (true);

drop policy if exists "lectura publica pharmacy_products" on pharmacy_products;
create policy "lectura publica pharmacy_products" on pharmacy_products for select using (true);

drop policy if exists "lectura publica price_snapshots" on price_snapshots;
create policy "lectura publica price_snapshots" on price_snapshots for select using (true);

-- subscriptions, scrape_runs, ai_cache y outbound_clicks: sin política de
-- select pública -> solo accesibles con la service key.

-- Búsqueda tolerante a errores de tipeo sobre el nombre tal como aparece
-- en cada tienda (mientras drugs/pharmacy_products.drug_id no está
-- poblado por el normalizador, la web busca directamente aquí).
create index if not exists idx_pharmacy_products_nombre on pharmacy_products using gin (nombre_en_tienda gin_trgm_ops);

-- Precio más reciente por producto, para que el buscador de la web no
-- tenga que hacer una segunda consulta a price_snapshots.
-- security_invoker: la vista respeta las policies de RLS de las tablas
-- base para el rol que consulta (anon), no corre con permisos del owner.
create or replace view latest_prices with (security_invoker = true) as
select
  pp.id as pharmacy_product_id,
  pp.pharmacy,
  pp.nombre_en_tienda,
  pp.url,
  pp.drug_id,
  ps.precio_usd,
  ps.precio_promocional,
  ps.en_stock,
  ps.fecha
from pharmacy_products pp
join lateral (
  select *
  from price_snapshots ps2
  where ps2.pharmacy_product_id = pp.id
  order by ps2.fecha desc
  limit 1
) ps on true;
