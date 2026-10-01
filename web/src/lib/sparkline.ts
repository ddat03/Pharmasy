// Mini-gráfico de tendencia de precio (sparkline), client-side: ver pedido
// del usuario del 2026-10-01 de que la pantalla principal y los resultados
// "se ven muy planos, como solo listas". No hace falta una librería de
// gráficos para 2-21 puntos — un <path> en línea, mismo lenguaje visual que
// CategoryIcon.astro (trazo simple, sin relleno).
//
// Corre en el navegador, no en el build: igual que searchProducts() en
// supabase.ts, pega directo contra PostgREST con la anon key. Evita inflar
// el build estático con miles de consultas históricas (una por cada fila de
// cada una de las ~1900 páginas de medicamento) para un dato que además
// cambia noche a noche -- pedirlo al momento de la visita es lo correcto.
import { SUPABASE_URL, SUPABASE_ANON_KEY } from "./supabase";

export type PuntoPrecio = { fecha: string; precio: number };

// Historial de los últimos `dias` días para un lote de pharmacy_product_id,
// en una sola consulta por lote (nunca una por fila). 21 días alcanza para
// ver si un precio viene subiendo, bajando o quieto sin pedir de más.
export async function historialPrecios(ids: string[], dias = 21): Promise<Map<string, PuntoPrecio[]>> {
  const mapa = new Map<string, PuntoPrecio[]>();
  if (ids.length === 0) return mapa;

  const desde = new Date();
  desde.setDate(desde.getDate() - dias);
  const qs = new URLSearchParams({
    select: "pharmacy_product_id,fecha,precio_usd,precio_promocional",
    pharmacy_product_id: `in.(${ids.join(",")})`,
    fecha: `gte.${desde.toISOString().slice(0, 10)}`,
    order: "fecha.asc",
  });

  let rows: {
    pharmacy_product_id: string;
    fecha: string;
    precio_usd: number | null;
    precio_promocional: number | null;
  }[];
  try {
    const resp = await fetch(`${SUPABASE_URL}/rest/v1/price_snapshots?${qs.toString()}`, {
      headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${SUPABASE_ANON_KEY}` },
    });
    if (!resp.ok) return mapa;
    rows = await resp.json();
  } catch {
    // Sin conexión o Supabase caído: el sparkline simplemente no aparece.
    // No es un dato esencial -- no vale la pena romper la fila por esto.
    return mapa;
  }

  for (const r of rows) {
    // El precio que la persona realmente paga: el promocional si existe,
    // igual criterio que precioEfectivo() en index.astro.
    const precio = r.precio_promocional ?? r.precio_usd;
    if (precio == null) continue;
    const lista = mapa.get(r.pharmacy_product_id);
    if (lista) lista.push({ fecha: r.fecha, precio });
    else mapa.set(r.pharmacy_product_id, [{ fecha: r.fecha, precio }]);
  }
  return mapa;
}

// SVG en línea a mano: con 2-21 puntos no justifica una librería de
// gráficos. Devuelve null si no hay suficientes puntos para que una línea
// signifique algo (un producto nuevo con un solo snapshot no tiene
// "tendencia" todavía).
export function renderSparklineSVG(puntos: PuntoPrecio[]): string | null {
  if (puntos.length < 2) return null;

  const precios = puntos.map((p) => p.precio);
  const min = Math.min(...precios);
  const max = Math.max(...precios);
  const w = 68;
  const h = 22;
  const pad = 2.5;
  const rango = max - min || 1; // precio plano los N días: evita dividir por cero

  const coords = puntos.map((p, i) => {
    const x = pad + (i / (puntos.length - 1)) * (w - pad * 2);
    const y = h - pad - ((p.precio - min) / rango) * (h - pad * 2);
    return [x, y] as const;
  });
  const d = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

  // Color según dirección neta en la ventana: sube = tono de la marca
  // (alerta suave, no rojo de "error"), baja = verde de buen precio (mismo
  // verde que "Mejor precio" en el resto del sitio), igual = gris neutro.
  const delta = precios[precios.length - 1] - precios[0];
  const color = delta < -0.004 ? "var(--deal-dark)" : delta > 0.004 ? "var(--stamp-dark)" : "var(--ink-muted)";
  const [lastX, lastY] = coords[coords.length - 1];

  return (
    `<svg class="spark-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" ` +
    `aria-label="Tendencia de precio, últimos ${puntos.length} días con dato">` +
    `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />` +
    `<circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="2" fill="${color}" />` +
    `</svg>`
  );
}
