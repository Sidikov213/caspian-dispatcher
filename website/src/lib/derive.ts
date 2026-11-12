import { addHours } from "./format";
import type {
  Alert,
  AlertOption,
  Alternative,
  DisplayStatus,
  Edge,
  Mode,
  RiskLevel,
  Route,
  Scenario,
  Shipment,
  Weather,
  WeatherPoint,
} from "./types";

export const STATUS_LABEL: Record<DisplayStatus, string> = {
  planned: "Запланирован",
  in_transit: "В пути",
  at_risk: "Под риском",
  rerouted: "Перестроен",
  delivered: "Доставлен",
};

export const RISK_LEVEL_LABEL: Record<RiskLevel, string> = {
  low: "Низкий",
  medium: "Средний",
  high: "Высокий",
};

const CARGO_LABEL: Record<string, string> = {
  grain: "Сыпучий груз",
  metal: "Металлопрокат",
  equipment: "Генеральный груз",
  textile: "Генеральный груз",
  fertilizer: "Навалочный груз",
};

export function cargoLabel(cargoType: string): string {
  return CARGO_LABEL[cargoType] ?? cargoType;
}

export type CargoIcon = "rail" | "box" | "truck" | "ship";

const CARGO_ICON: Record<string, CargoIcon> = {
  grain: "rail",
  metal: "box",
  equipment: "truck",
  textile: "truck",
  fertilizer: "ship",
};

const MODE_ICON: Record<Mode, CargoIcon> = { rail: "rail", sea: "ship", road: "truck" };

/** Выбранный груз или, по умолчанию, первый в пути: его маршрут рисуется на карте как основной. */
export function pickFocus(shipments: Shipment[], id: string | null): Shipment | null {
  return shipments.find((s) => s.id === id) ?? shipments.find((s) => s.stage === "in_transit") ?? shipments[0] ?? null;
}

/** «порт Махачкала», «пункт пропуска Самур». */
export function checkpointLabel(node: { name: string; type: string } | undefined, fallback: string): string {
  if (!node) return fallback;
  const name = node.name.replace(/\s*\(.*\)\s*$/, "").replace(/\s*\/.*$/, "").trim();
  return `${node.type === "port" ? "порт " : node.type === "border" ? "пункт пропуска " : ""}${name}`;
}

export function cargoIcon(s: Shipment): CargoIcon {
  if (CARGO_ICON[s.cargo_type]) return CARGO_ICON[s.cargo_type];
  const leg = s.route.legs[s.current_leg ?? 0];
  return leg ? MODE_ICON[leg.mode] : "box";
}

export function modeIcon(mode: Mode): CargoIcon {
  return MODE_ICON[mode];
}

// ---------- этапы маршрута ----------

export interface RouteStop {
  nodeId: string;
  mode: Mode;
  note: string;
  tone: "done" | "danger" | "default";
  planned: string;
  forecast: string | null;
}

/** Узлы смены транспорта плюс начало и конец: Москва → Астрахань → Энзели → Бендер-Аббас → Мумбаи. */
export function routeStops(s: Shipment): RouteStop[] {
  const legs = s.route.legs;
  if (legs.length === 0) return [];
  const first = legs[0];
  const departed = first.status === "done" || first.status === "active";
  const stops: RouteStop[] = [
    {
      nodeId: first.from,
      mode: first.mode,
      note: departed ? "Пройден" : "Отправление",
      tone: departed ? "done" : "default",
      planned: first.planned_start,
      forecast: null,
    },
  ];
  legs.forEach((leg, i) => {
    const next = legs[i + 1];
    if (next && next.mode === leg.mode) return;
    if (next && next.status === "blocked") {
      const shift = s.risk?.departure_shift_h ?? next.predicted_delay_h;
      stops.push({
        nodeId: leg.to,
        mode: leg.mode,
        note: next.mode === "sea" ? "Стыковка с паромом · под угрозой" : "Стыковка · под угрозой",
        tone: "danger",
        planned: next.planned_start,
        forecast: shift > 0 ? addHours(next.planned_start, shift) : null,
      });
      return;
    }
    stops.push({
      nodeId: leg.to,
      mode: leg.mode,
      note: leg.status === "done" ? "Пройден" : leg.status === "active" ? "В пути" : "Впереди",
      tone: leg.status === "done" ? "done" : "default",
      planned: leg.planned_end,
      forecast: leg.predicted_delay_h > 0 ? addHours(leg.planned_end, leg.predicted_delay_h) : null,
    });
  });
  return stops;
}

// ---------- CO₂ ----------

export function co2ByMode(s: Shipment, edges: Map<string, Edge>): Record<Mode, number> {
  const out: Record<Mode, number> = { rail: 0, sea: 0, road: 0 };
  for (const leg of s.route.legs) {
    const e = edges.get(leg.edge_id);
    if (e) out[leg.mode] += (s.weight_t * e.distance_km * e.co2_g_per_tkm) / 1000;
  }
  return out;
}

// ---------- погода ----------

/** Предел волны для парома, м (DEMO_SCENARIO.md). */
export const WAVE_LIMIT_M = 2.5;
export const ALERT_HORIZON_H = 48;

export function peakWave48(p: WeatherPoint): number {
  return p.forecast.slice(0, ALERT_HORIZON_H).reduce((m, f) => Math.max(m, f.wave_height_m), p.wave_height_m);
}

export interface WeatherSummary {
  storm: boolean;
  waveM: number;
  windMs: number;
}

/**
 * Размах шторма по прогнозу на 48 ч: «north» — только север моря, «full» — не меньше 60% точек.
 * Зона на карте и заголовок алерта берутся отсюда, а не из названия сценария.
 */
export type StormScope = "none" | "north" | "full";

export function stormScope(w: Weather | null): StormScope {
  if (!w || w.points.length === 0) return "none";
  const stormy = w.points.filter((p) => peakWave48(p) > WAVE_LIMIT_M).length;
  if (stormy === 0) return "none";
  return stormy / w.points.length >= 0.6 ? "full" : "north";
}

/**
 * Сводка для шапки. Пока решение не принято, показываем пик шторма; после «Принять» угроза снята,
 * и шапка возвращается к текущему состоянию моря (так в макетах W5 и W6).
 */
export function weatherSummary(w: Weather | null, scenario: Scenario | null, calm = false): WeatherSummary | null {
  if (!w || w.points.length === 0) return null;
  const worst = w.points.reduce((a, b) => (peakWave48(b) > peakWave48(a) ? b : a));
  const peak = peakWave48(worst);
  if (peak > WAVE_LIMIT_M && !calm) {
    return { storm: true, waveM: scenario?.params.wave_height_m ?? peak, windMs: scenario?.params.wind_ms ?? worst.wind_ms };
  }
  return {
    storm: false,
    waveM: Math.max(...w.points.map((p) => p.wave_height_m)),
    windMs: Math.max(...w.points.map((p) => p.wind_ms)),
  };
}

export function pointWave(p: WeatherPoint, calm = false): { value: number; storm: boolean } {
  const peak = peakWave48(p);
  return peak > WAVE_LIMIT_M && !calm ? { value: peak, storm: true } : { value: p.wave_height_m, storm: false };
}

// ---------- алерты и варианты решения ----------

/** Новый алерт, в котором есть этот груз. */
export function newAlertFor(alerts: Alert[], shipmentId: string): Alert | null {
  return alerts.find((a) => a.status === "new" && a.items.some((i) => i.shipment_id === shipmentId)) ?? null;
}

/** Маршрут «ничего не делать»: плановый, с заблокированным этапом. */
export function isWaitRoute(route: Route): boolean {
  return route.legs.some((l) => l.status === "blocked");
}

/** Вариант алерта для альтернативы груза: id маршрута кончается тегом варианта (`r-sh-01-mkh` ↔ `mkh`). */
export function optionFor(alt: Alternative, alert: Alert | null): AlertOption | null {
  if (!alert) return null;
  if (isWaitRoute(alt.route)) return alert.options.find((o) => o.id === "wait") ?? null;
  return alert.options.find((o) => o.id !== "wait" && alt.route.id.endsWith(`-${o.id}`)) ?? null;
}

/** «Через Махачкалу (паром М, 15 ноя, 06:00)» → «Через Махачкалу». */
export function optionTitle(option: AlertOption | null, alt: Alternative): string {
  if (option) return option.title.replace(/\s*\(.*\)\s*$/, "");
  return isWaitRoute(alt.route) ? "Ждать следующий рейс" : "Обходной маршрут";
}

/** Порядок карточек: рекомендованный, потом по задержке, «ждать» последним. */
export function sortAlternatives(list: Alternative[]): Alternative[] {
  const rank = (a: Alternative) => (isWaitRoute(a.route) ? 2 : a.recommended ? 0 : 1);
  return [...list].sort((a, b) => rank(a) - rank(b) || a.delta.hours - b.delta.hours);
}

/** Узлы, по которым вариант отличается от плана: «Махачкала → Энзели». */
export function divergentNodes(route: Route, plan: Route | null): string[] {
  const blocked = route.legs.find((l) => l.status === "blocked");
  if (blocked) return [blocked.from, blocked.to];
  if (plan) {
    const planEdges = new Set(plan.legs.map((l) => l.edge_id));
    const start = route.legs.findIndex((l) => !planEdges.has(l.edge_id));
    if (start >= 0) {
      const back = route.legs.findIndex((l, i) => i > start && planEdges.has(l.edge_id));
      return route.legs.slice(start, back < 0 ? undefined : back).map((l) => l.to);
    }
  }
  return route.legs.map((l) => l.to);
}

/** Первый узел, где вариант уходит с плановых рёбер: точка пересадки на карте. */
export function divergenceNode(route: Route, plan: Route | null): string | null {
  if (!plan) return null;
  const planEdges = new Set(plan.legs.map((l) => l.edge_id));
  return route.legs.find((l) => !planEdges.has(l.edge_id))?.to ?? null;
}

/** Запасной отсчёт, если в алерте нет starts_in_h. Живой бэкенд отдаёт starts_in_h от sim_now. */
export function stormLeadHours(alert: Alert, weather: Weather | null, scenario: Scenario | null): number | null {
  let start: number | null = scenario ? Date.parse(scenario.start) : null;
  if (start === null && weather) {
    const from = alert.items[0]?.from_route?.legs.find((l) => l.status === "blocked")?.from;
    const hit = weather.points.find((p) => p.node_id === from)?.forecast.find((f) => f.wave_height_m > WAVE_LIMIT_M);
    if (hit) start = Date.parse(hit.ts);
  }
  return start === null ? null : Math.max(0, Math.round((start - Date.parse(alert.created_at)) / 3_600_000));
}
