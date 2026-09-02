-- Migración: dejar de reprocesar productos que no son medicamentos.
--
-- Problema: el normalizador selecciona por `drug_id is null` y, cuando la IA
-- determina que un producto NO es un medicamento (pañales, champú, toallas
-- húmedas, biberones), lo omite y lo deja con `drug_id` nulo. Como el filtro
-- no distingue "todavía no procesado" de "procesado y descartado", esos
-- productos vuelven a la cola todas las noches, para siempre.
--
-- No cuesta dinero — `ai_cache` sirve la respuesta por hash del nombre sin
-- volver a llamar a OpenAI — pero son cientos de consultas a Supabase por
-- corrida que no pueden cambiar de resultado.
--
-- Cómo aplicarla: pegar este archivo entero en el SQL Editor de Supabase
-- (proyecto de farma-precios) y ejecutar. Es seguro re-ejecutarlo.
--
-- Después de aplicarla hay que actualizar pipeline/normalizer.py para que
-- escriba la columna y la filtre — sin ese cambio la columna queda siempre
-- nula y no hace nada. Ver el comentario al pie.

-- null  = todavía no evaluado por el normalizador
-- true  = la IA confirmó que es un medicamento (y entonces tiene drug_id)
-- false = evaluado y descartado; no volver a preguntarlo nunca
alter table pharmacy_products
  add column if not exists es_medicamento boolean;

comment on column pharmacy_products.es_medicamento is
  'null = sin evaluar; true = medicamento; false = evaluado y descartado (no reprocesar). Ver db/migracion_es_medicamento.sql.';

-- Los que ya tienen drug_id son, por definición, medicamentos confirmados.
update pharmacy_products
   set es_medicamento = true
 where drug_id is not null
   and es_medicamento is distinct from true;

-- Índice parcial: la consulta del normalizador es exactamente
-- "de esta cadena, los que no tienen drug_id y no fueron descartados".
create index if not exists idx_pharmacy_products_pendientes
    on pharmacy_products (pharmacy)
 where drug_id is null and es_medicamento is not false;

-- ---------------------------------------------------------------------------
-- Cambio que acompaña en pipeline/normalizer.py (todavía NO aplicado):
--
--   1. En normalize_batch(), agregar al filtro de supabase_select:
--          "es_medicamento": "not.is.false"
--
--   2. Donde hoy se descarta un producto por no ser medicamento, marcarlo:
--          supabase_upsert(
--              "pharmacy_products",
--              [{"pharmacy": prod["pharmacy"], "external_id": prod["external_id"],
--                "nombre_en_tienda": prod["nombre_en_tienda"], "es_medicamento": False}],
--              on_conflict="pharmacy,external_id",
--          )
--
--   3. Al emparejar uno correctamente, incluir "es_medicamento": True en el
--      upsert que ya escribe drug_id y match_confidence.
-- ---------------------------------------------------------------------------
