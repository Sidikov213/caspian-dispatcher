// Живые грузы на карте: только плавность. Где груз — считает сервер (Shipment.position);
// здесь — линия маршрута из рёбер графа и точка на ней, чтобы значок доезжал вдоль пути, а не по прямой.
import type { Edge, GraphNode, Mode, Route, Shipment, ShipmentPosition } from "../types";

export type LatLng = [number, number];

/** Линия ребра в направлении движения: узел → Edge.path → узел. */
export function edgeLine(edge: Edge | undefined, nodes: Map<string, GraphNode>, from?: string): LatLng[] | null {
  if (!edge) return null;
  const a = nodes.get(edge.from);
  const b = nodes.get(edge.to);
  if (!a || !b) return null;
  const pts: LatLng[] = [[a.lat, a.lon], ...((edge.path ?? []) as LatLng[]), [b.lat, b.lon]];
  return from && from === edge.to && from !== edge.from ? pts.reverse() : pts;
}

/** Длина отрезка в «градусах экватора» (долгота сжата по широте) — для долей пути хватает. */
function segLen(p: LatLng, q: LatLng): number {
  const k = Math.cos((((p[0] + q[0]) / 2) * Math.PI) / 180);
  return Math.hypot(q[0] - p[0], (q[1] - p[1]) * k);
}

export function bearing(p: LatLng, q: LatLng): number {
  const r = Math.PI / 180;
  const y = Math.sin((q[1] - p[1]) * r) * Math.cos(q[0] * r);
  const x = Math.cos(p[0] * r) * Math.sin(q[0] * r) - Math.sin(p[0] * r) * Math.cos(q[0] * r) * Math.cos((q[1] - p[1]) * r);
  return ((Math.atan2(y, x) / r) + 360) % 360;
}

/** Маршрут груза одной линией: точки, накопленная длина в каждой точке, начало и длина каждого этапа. */
export interface Track {
  pts: LatLng[];
  cum: number[];
  legs: { edge_id: string; start: number; len: number; mode: Mode }[];
}

export function routeTrack(route: Route, edges: Map<string, Edge>, nodes: Map<string, GraphNode>): Track {
  const pts: LatLng[] = [];
  const cum: number[] = [];
  const legs: Track["legs"] = [];
  let total = 0;
  for (const leg of route.legs) {
    const line = edgeLine(edges.get(leg.edge_id), nodes, leg.from);
    if (!line) continue;
    const start = total;
    for (let i = 0; i < line.length; i++) {
      if (i === 0 && pts.length) continue;      // узел стыка уже в линии
      if (pts.length) total += segLen(pts[pts.length - 1], line[i]);
      pts.push(line[i]);
      cum.push(total);
    }
    legs.push({ edge_id: leg.edge_id, start, len: total - start, mode: leg.mode });
  }
  return { pts, cum, legs };
}

/** Позиция сервера → расстояние вдоль маршрута; null — ребра нет в маршруте. */
export function trackS(track: Track, pos: ShipmentPosition): number | null {
  const leg = track.legs.find((l) => l.edge_id === pos.edge_id);
  return leg ? leg.start + leg.len * (pos.waiting ? 0 : pos.progress) : null;
}

/** Точка и курс на расстоянии s вдоль маршрута. */
export function trackPoint(track: Track, s: number): { pt: LatLng; heading: number } {
  const { pts, cum } = track;
  if (pts.length < 2) return { pt: pts[0] ?? [0, 0], heading: 0 };
  const x = Math.min(Math.max(s, 0), cum[cum.length - 1]);
  let i = 1;
  while (i < cum.length - 1 && cum[i] < x) i++;
  const d = cum[i] - cum[i - 1];
  const t = d > 0 ? (x - cum[i - 1]) / d : 0;
  const p = pts[i - 1];
  const q = pts[i];
  return { pt: [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t], heading: bearing(p, q) };
}

/** Ключ, по которому видно, что маршрут сменился (перестроение) — тогда линию строим заново. */
export const routeKey = (s: Shipment) => `${s.route.id}:${s.route.legs.map((l) => l.edge_id).join(",")}`;
