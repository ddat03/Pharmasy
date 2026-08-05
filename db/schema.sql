-- Esquema de base de datos (Supabase / PostgreSQL)
-- Ver sección 6 del documento maestro comparador-medicamentos-ecuador.md

create extension if not exists pg_trgm;
create extension if not exists "uuid-ossp";

create type pharmacy_enum as enum (
  'fybeca', 'pharmacys', 'medicity', 'cruzazul', 'economicas'
);

create type match_method_enum as enum ('exact', 'ia', 'manual');

create type subscription_type_enum as enum ('precio_baja', 'repone_stock');

-- Catálogo maestro.
create table drugs (
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

create index idx_drugs_principio_activo on drugs using gin (principio_activo gin_trgm_ops);
create index idx_drugs_nombre_comercial on drugs using gin (nombre_comercial gin_trgm_ops);
create index idx_drugs_registro_sanitario on drugs (registro_sanitario);

-- Producto de una cadena de farmacia, emparejado a un drug del catálogo maestro.
create table pharmacy_products (
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

create index idx_pharmacy_products_drug_id on pharmacy_products (drug_id);

-- Una fila por producto por día.
create table price_snapshots (
  id uuid primary key default uuid_generate_v4(),
  pharmacy_product_id uuid not null references pharmacy_products (id) on delete cascade,
  fecha date not null,
  precio_usd numeric(10, 2),
  en_stock boolean,
  precio_promocional numeric(10, 2),
  created_at timestamptz not null default now(),
  unique (pharmacy_product_id, fecha)
);

create index idx_price_snapshots_fecha on price_snapshots (fecha);
create index idx_price_snapshots_pharmacy_product_fecha on price_snapshots (pharmacy_product_id, fecha);

-- Suscripciones a alertas por Telegram.
create table subscriptions (
  id uuid primary key default uuid_generate_v4(),
  telegram_chat_id text not null,
  drug_id uuid not null references drugs (id) on delete cascade,
  tipo subscription_type_enum not null,
  umbral numeric(10, 2),
  created_at timestamptz not null default now(),
  unique (telegram_chat_id, drug_id, tipo)
);

create index idx_subscriptions_drug_id on subscriptions (drug_id);

-- Bitácora de corridas de scraping.
create table scrape_runs (
  id uuid primary key default uuid_generate_v4(),
  fuente text not null,
  fecha timestamptz not null default now(),
  productos_ok integer not null default 0,
  errores integer not null default 0,
  duracion_segundos numeric(10, 2)
);

create index idx_scrape_runs_fuente_fecha on scrape_runs (fuente, fecha desc);

-- Caché de normalización con IA: nunca pagar dos veces la misma pregunta.
create table ai_cache (
  id uuid primary key default uuid_generate_v4(),
  input_hash text unique not null,
  response_json jsonb not null,
  created_at timestamptz not null default now()
);

-- Clicks salientes hacia cada farmacia (preparación de monetización, sección 7.6).
create table outbound_clicks (
  id uuid primary key default uuid_generate_v4(),
  drug_id uuid references drugs (id) on delete set null,
  pharmacy pharmacy_enum not null,
  fecha timestamptz not null default now()
);

create index idx_outbound_clicks_drug_pharmacy on outbound_clicks (drug_id, pharmacy);

-- Row Level Security: lectura pública solo en drugs, pharmacy_products,
-- price_snapshots. Escritura únicamente con service key (que hace bypass de RLS).
alter table drugs enable row level security;
alter table pharmacy_products enable row level security;
alter table price_snapshots enable row level security;
alter table subscriptions enable row level security;
alter table scrape_runs enable row level security;
alter table ai_cache enable row level security;
alter table outbound_clicks enable row level security;

create policy "lectura publica drugs" on drugs for select using (true);
create policy "lectura publica pharmacy_products" on pharmacy_products for select using (true);
create policy "lectura publica price_snapshots" on price_snapshots for select using (true);

-- subscriptions, scrape_runs, ai_cache y outbound_clicks: sin política de
-- select pública -> solo accesibles con la service key.
