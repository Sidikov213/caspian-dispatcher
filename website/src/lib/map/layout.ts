// Схема коридора в координатах карты макета (1120×820). Карта в макете схематичная, а не
// географическая: Москва и Мумбаи придвинуты к Каспию, поэтому узлы лежат в таблице, а не
// считаются проекцией. Узлы, которых нет в макете, расставлены по той же схеме.

import type { Edge, GraphNode, Shipment } from "../types";

export type Pt = [number, number];
/** Кубическая кривая Безье: начало, две опорные точки, конец. */
export type Bezier = [Pt, Pt, Pt, Pt];

export const MAP_W = 1120;
export const MAP_H = 820;
export const GRID_DX = 88;
export const GRID_DY = 75.33;
export const GRID_Y0 = 25.7;

const line = (a: Pt, b: Pt): Bezier => [
  a,
  [a[0] + (b[0] - a[0]) / 3, a[1] + (b[1] - a[1]) / 3],
  [a[0] + ((b[0] - a[0]) * 2) / 3, a[1] + ((b[1] - a[1]) * 2) / 3],
  b,
];

export function bezierAt([p0, p1, p2, p3]: Bezier, t: number): Pt {
  const u = 1 - t;
  const a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t;
  return [a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]];
}

/** Участок кривой между t0 и t1 (алгоритм де Кастельжо). */
export function subBezier(bz: Bezier, t0: number, t1: number): Bezier {
  const split = ([p0, p1, p2, p3]: Bezier, t: number): [Bezier, Bezier] => {
    const lerp = (a: Pt, b: Pt): Pt => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    const p01 = lerp(p0, p1), p12 = lerp(p1, p2), p23 = lerp(p2, p3);
    const p012 = lerp(p01, p12), p123 = lerp(p12, p23);
    const m = lerp(p012, p123);
    return [[p0, p01, p012, m], [m, p123, p23, p3]];
  };
  const right = t0 > 0 ? split(bz, t0)[1] : bz;
  const tt = t0 < 1 ? (t1 - t0) / (1 - t0) : 1;
  return tt < 1 ? split(right, tt)[0] : right;
}

// Кривые сняты с макета W1.
const C = {
  moscowSamara: [[299.5, 146.5], [327.5, 148], [359.8, 153.1], [377.5, 177.1]] as Bezier,
  samaraSaratov: line([377.5, 177.1], [392.5, 223.5]),
  saratovAstrakhan: [[392.5, 223.5], [428.8, 225.7], [464.2, 228.2], [500.5, 226.5]] as Bezier,
  astrakhanAnzali: [[500.5, 226.5], [591.6, 295.4], [590.2, 422.3], [556.5, 520.5]] as Bezier,
  // Ж/д Астрахань → Махачкала на схеме выходит от Саратова (как в макете W3/W5), море Махачкала → Энзели идёт вдоль западного берега.
  astrakhanMakhachkala: [[392.5, 223.5], [445, 245], [492, 278], [509.5, 307.6]] as Bezier,
  makhachkalaAnzali: [[509.5, 307.6], [575, 358], [573, 450], [556.5, 520.5]] as Bezier,
  bakuAnzali: [[517.5, 377.1], [500, 402], [514, 466], [556.5, 520.5]] as Bezier,
  anzaliBandar: [[556.5, 520.5], [602, 584.9], [663.8, 508.5], [709.5, 552.5]] as Bezier,
  bandarMumbai: [[709.5, 552.5], [773.9, 646.8], [897.4, 662.8], [1002.5, 667.1]] as Bezier,
};

const T_ASTARA = 0.8;
const T_RASHT = 0.06;
const T_TEHRAN = 0.42;

export const NODE_POS: Record<string, Pt> = {
  moscow: [299.5, 146.5],
  samara: [377.5, 177.1],
  saratov: [392.5, 223.5],
  astrakhan: [500.5, 226.5],
  olya: [508, 247],
  makhachkala: [509.5, 307.6],
  samur: [514, 343],
  baku: [517.5, 377.1],
  astara: bezierAt(C.bakuAnzali, T_ASTARA),
  anzali: [556.5, 520.5],
  rasht: bezierAt(C.anzaliBandar, T_RASHT),
  tehran: bezierAt(C.anzaliBandar, T_TEHRAN),
  amirabad: [612, 512],
  aktau: [626, 330],
  incheh: [668, 492],
  bandar_abbas: [709.5, 552.5],
  mumbai: [1002.5, 667.1],
};

/** Геометрия рёбер графа; рёбра вне таблицы рисуются прямой между узлами. */
const EDGE_GEOMETRY: Record<string, Bezier[]> = {
  "e-moscow-astrakhan": [C.moscowSamara, C.samaraSaratov, C.saratovAstrakhan],
  "e-samara-astrakhan": [C.samaraSaratov, C.saratovAstrakhan],
  "e-saratov-astrakhan": [C.saratovAstrakhan],
  "e-astrakhan-anzali": [C.astrakhanAnzali],
  "e-astrakhan-makhachkala": [C.astrakhanMakhachkala],
  "e-makhachkala-anzali": [C.makhachkalaAnzali],
  "e-baku-astara": [subBezier(C.bakuAnzali, 0, T_ASTARA)],
  "e-astara-rasht": [subBezier(C.bakuAnzali, T_ASTARA, 1), subBezier(C.anzaliBandar, 0, T_RASHT)],
  "e-anzali-rasht": [subBezier(C.anzaliBandar, 0, T_RASHT)],
  "e-rasht-tehran": [subBezier(C.anzaliBandar, T_RASHT, T_TEHRAN)],
  "e-tehran-bandar_abbas": [subBezier(C.anzaliBandar, T_TEHRAN, 1)],
  "e-bandar_abbas-mumbai": [C.bandarMumbai],
};

export function nodePos(id: string): Pt | null {
  return NODE_POS[id] ?? null;
}

export function edgeGeometry(edge: Pick<Edge, "id" | "from" | "to">): Bezier[] | null {
  const g = EDGE_GEOMETRY[edge.id];
  if (g) return g;
  const a = nodePos(edge.from);
  const b = nodePos(edge.to);
  return a && b ? [line(a, b)] : null;
}

export function bezierPath(segs: Bezier[]): string {
  return segs
    .map(([p0, p1, p2, p3], i) => `${i === 0 ? `M${p0[0]} ${p0[1]}` : ""}C${p1[0]} ${p1[1]} ${p2[0]} ${p2[1]} ${p3[0]} ${p3[1]}`)
    .join("");
}

function segLength(bz: Bezier): number {
  let len = 0;
  let prev = bz[0];
  for (let i = 1; i <= 24; i++) {
    const p = bezierAt(bz, i / 24);
    len += Math.hypot(p[0] - prev[0], p[1] - prev[1]);
    prev = p;
  }
  return len;
}

/** Точка на схеме ребра на доле пути f ∈ [0, 1]. */
export function pointAlong(segs: Bezier[], f: number): Pt {
  const lens = segs.map(segLength);
  let target = Math.min(Math.max(f, 0), 1) * lens.reduce((a, b) => a + b, 0);
  for (let i = 0; i < segs.length; i++) {
    if (target <= lens[i] || i === segs.length - 1) return bezierAt(segs[i], lens[i] ? Math.min(target / lens[i], 1) : 0);
    target -= lens[i];
  }
  return segs[segs.length - 1][3];
}

function haversineKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const r = Math.PI / 180;
  const dLat = (b.lat - a.lat) * r;
  const dLon = (b.lon - a.lon) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}

/**
 * Положение груза на схеме: доля пройденного пути по текущему этапу (по координатам с бэкенда)
 * переносится на схему ребра. Без этапа — узел отправления.
 */
export function shipmentPos(s: Shipment, nodes: Map<string, GraphNode>, edges: Map<string, Edge>): Pt | null {
  const leg = s.current_leg != null ? s.route.legs[s.current_leg] : null;
  if (!leg || !s.position) return nodePos(leg?.from ?? s.origin);
  const from = nodes.get(leg.from);
  const to = nodes.get(leg.to);
  const geom = edgeGeometry(edges.get(leg.edge_id) ?? { id: leg.edge_id, from: leg.from, to: leg.to });
  if (!from || !to || !geom) return nodePos(leg.from);
  const done = haversineKm(from, s.position);
  const left = haversineKm(s.position, to);
  return pointAlong(geom, done + left > 0 ? done / (done + left) : 0);
}

// ---------- подписи ----------

/** Подписи городов: смещение от центра узла до точки привязки текста (середина по высоте). */
export const NODE_LABELS: Record<string, { dx: number; dy: number; anchor: "start" | "end" }> = {
  moscow: { dx: -6, dy: -18, anchor: "end" },
  samara: { dx: -30, dy: -16.5, anchor: "start" },
  saratov: { dx: -7.5, dy: 20, anchor: "end" },
  astrakhan: { dx: -12.5, dy: -25, anchor: "start" },
  makhachkala: { dx: -15.5, dy: -5, anchor: "end" },
  baku: { dx: -15.5, dy: 11.5, anchor: "end" },
  anzali: { dx: -23.5, dy: 13, anchor: "end" },
  bandar_abbas: { dx: -26.5, dy: 20, anchor: "start" },
  mumbai: { dx: 12.5, dy: -3.5, anchor: "start" },
};

export const COUNTRY_LABELS: { text: string[]; x: number; y: number; anchor: "start" | "middle"; sea?: boolean }[] = [
  { text: ["РОССИЯ"], x: 194, y: 121, anchor: "middle" },
  { text: ["КАЗАХСТАН"], x: 752, y: 197, anchor: "middle" },
  { text: ["ГРУЗИЯ"], x: 377, y: 358, anchor: "middle" },
  { text: ["АЗЕРБАЙДЖАН"], x: 447, y: 409, anchor: "middle" },
  { text: ["КАСПИЙСКОЕ", "МОРЕ"], x: 571, y: 374, anchor: "start", sea: true },
  { text: ["ТУРКМЕНИСТАН"], x: 734, y: 387, anchor: "middle" },
  { text: ["ИРАН"], x: 619, y: 484, anchor: "start" },
  { text: ["ИНДИЯ"], x: 978, y: 583, anchor: "middle" },
];

/** Плашки волны у портов: левый верхний угол плашки относительно узла. */
export const WAVE_CHIPS: Record<string, { dx: number; dy: number }> = {
  astrakhan: { dx: 14.5, dy: 18.5 },
  makhachkala: { dx: -66.5, dy: 21.5 },
  anzali: { dx: 6.5, dy: 10.5 },
};

/** Рамка вида по умолчанию: Каспий от Волгограда до Тегерана с концами коридора. */
export const DEFAULT_VIEW = { x: 0, y: 0, w: MAP_W, h: MAP_H };
