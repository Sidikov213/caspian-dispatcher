"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { pickFocus, pointWave, type StormScope } from "@/lib/derive";
import { formatDecimal, shipmentIndex, shortNodeName } from "@/lib/format";
import { BORDERS, CASPIAN, CASPIAN_CONTOURS, INLAND_SEA, LAND, STORM_ZONE_FULL, STORM_ZONE_NORTH } from "@/lib/map/geometry";
import {
  COUNTRY_LABELS,
  DEFAULT_VIEW,
  GRID_DX,
  GRID_DY,
  GRID_Y0,
  NODE_LABELS,
  WAVE_CHIPS,
  bezierPath,
  edgeGeometry,
  nodePos,
  shipmentPos,
  type Pt,
} from "@/lib/map/layout";
import type { DisplayStatus, Edge, GraphNode, Leg, Route, Shipment, Weather } from "@/lib/types";
import { LayersIcon, LocateIcon, MinusIcon, PlusIcon, RailIcon, RoadIcon, RouteIcon, SeaIcon, WavesIcon } from "./icons";

interface Props {
  nodes: Map<string, GraphNode>;
  edges: Map<string, Edge>;
  shipments: Shipment[];
  weather: Weather | null;
  focusId: string | null;
  /** Вариант решения, который показываем поверх маршрута выбранного груза (W3). */
  preview?: Route | null;
  /** Зона шторма на карте: север моря или всё море. */
  stormZone?: StormScope;
  /** Решение принято: плашки волны показывают текущую волну, а не пик шторма. Зона остаётся как прогноз. */
  calmWaves?: boolean;
  /** Узел пересадки нового маршрута: рисуется зелёной точкой. */
  checkpointNode?: string | null;
  /** Ширина правой панели, которая перекрывает карту. */
  insetRight: number;
  freshness: { text: string; stale: boolean } | null;
  onSelect(id: string): void;
}

interface View {
  s: number;
  tx: number;
  ty: number;
}

const MIN_SCALE = 0.35;
const MAX_SCALE = 4;
const BOX = { x: 0, y: 0, w: 0, h: 0 };

const MARKER_FILL: Record<DisplayStatus, string> = {
  in_transit: "var(--color-transit)",
  at_risk: "var(--color-risk)",
  rerouted: "var(--color-rerouted)",
  planned: "var(--color-muted)",
  delivered: "var(--color-muted)",
};

const ROUTE = {
  active: "var(--color-transit)",
  pending: "var(--color-cyan)",
  blocked: "var(--color-risk)",
  rerouted: "var(--color-rerouted)",
  other: "#94A3B8",
  casing: "#E2E8F0",
  preview: "#60A5FA",
};

/** Подогнать прямоугольник карты в видимую часть контейнера. */
function fit(box: { x: number; y: number; w: number; h: number }, vw: number, vh: number, pad: number): View {
  const s = Math.min(Math.max(Math.min((vw - pad * 2) / box.w, (vh - pad * 2) / box.h), MIN_SCALE), MAX_SCALE);
  return { s, tx: vw / 2 - (box.x + box.w / 2) * s, ty: vh / 2 - (box.y + box.h / 2) * s };
}

function routeBox(s: Shipment, edges: Map<string, Edge>) {
  const pts: Pt[] = [];
  for (const leg of s.route.legs) {
    const g = edgeGeometry(edges.get(leg.edge_id) ?? { id: leg.edge_id, from: leg.from, to: leg.to });
    g?.forEach((b) => pts.push(b[0], b[3]));
  }
  if (pts.length === 0) return DEFAULT_VIEW;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  // Запас под подписи городов слева и справа.
  const x0 = Math.min(...xs) - 50;
  const x1 = Math.max(...xs) + 75;
  const y0 = Math.min(...ys) - 40;
  const y1 = Math.max(...ys) + 30;
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

function legColor(leg: Leg, s: Shipment, focused: boolean): string {
  if (!focused) return ROUTE.other;
  if (leg.status === "blocked") return ROUTE.blocked;
  if (leg.status === "active" || leg.status === "done") return ROUTE.active;
  return s.rerouted ? ROUTE.rerouted : ROUTE.pending;
}

function dash(mode: Leg["mode"], k: number): { dasharray?: string; cap: "round" | "butt" } {
  if (mode === "sea") return { dasharray: `${7 * k} ${5 * k}`, cap: "butt" };
  if (mode === "road") return { dasharray: `${0.01 * k} ${5.2 * k}`, cap: "round" };
  return { cap: "round" };
}

export function CorridorMap({
  nodes,
  edges,
  shipments,
  weather,
  focusId,
  preview = null,
  stormZone = "none",
  calmWaves = false,
  checkpointNode = null,
  insetRight,
  freshness,
  onSelect,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [view, setView] = useState<View>({ s: 1, tx: 0, ty: 0 });
  const [layers, setLayers] = useState({ waves: true, borders: true, grid: true });
  const [layersOpen, setLayersOpen] = useState(false);
  const anim = useRef<number | null>(null);
  const drag = useRef<{ x: number; y: number; tx: number; ty: number; moved: boolean } | null>(null);
  const viewRef = useRef(view);
  const [dragging, setDragging] = useState(false);
  useLayoutEffect(() => {
    viewRef.current = view;
  }, [view]);

  const focus = useMemo(() => pickFocus(shipments, focusId), [shipments, focusId]);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const animateTo = useCallback((to: View, ms = 380) => {
    if (anim.current) cancelAnimationFrame(anim.current);
    const from = viewRef.current;
    const t0 = performance.now();
    const step = (now: number) => {
      const t = Math.min((now - t0) / ms, 1);
      const e = 1 - Math.pow(1 - t, 3);
      setView({ s: from.s + (to.s - from.s) * e, tx: from.tx + (to.tx - from.tx) * e, ty: from.ty + (to.ty - from.ty) * e });
      anim.current = t < 1 ? requestAnimationFrame(step) : null;
    };
    anim.current = requestAnimationFrame(step);
  }, []);

  const targetView = useCallback((): View => {
    const vw = size.w - insetRight;
    if (insetRight > 0 && focusId && focus) return fit(routeBox(focus, edges), vw, size.h, 16);
    const v = fit(DEFAULT_VIEW, vw, size.h, 0);
    // Вид по умолчанию совпадает с макетом (масштаб 1) и не увеличивает схему сверх него.
    return v.s > 1 ? { s: 1, tx: (vw - DEFAULT_VIEW.w) / 2, ty: (size.h - DEFAULT_VIEW.h) / 2 } : v;
  }, [size, insetRight, focusId, focus, edges]);

  const firstFit = useRef(true);
  useEffect(() => {
    if (size.w === 0) return;
    const v = targetView();
    if (firstFit.current) {
      firstFit.current = false;
      setView(v);
    } else animateTo(v);
    // Перестраиваем вид только при смене размера, панели или выбранного груза.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.w, size.h, insetRight, focusId]);

  const zoomAt = useCallback((factor: number, cx: number, cy: number, animated = false) => {
    const v = viewRef.current;
    const s = Math.min(Math.max(v.s * factor, MIN_SCALE), MAX_SCALE);
    const k = s / v.s;
    const next = { s, tx: cx - (cx - v.tx) * k, ty: cy - (cy - v.ty) * k };
    if (animated) animateTo(next, 220);
    else setView(next);
  }, [animateTo]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (anim.current) cancelAnimationFrame(anim.current);
      const r = el.getBoundingClientRect();
      zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest("[data-map-ui]")) return;
    if (anim.current) cancelAnimationFrame(anim.current);
    drag.current = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty, moved: false };
    setDragging(true);
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
    setView((v) => ({ ...v, tx: d.tx + dx, ty: d.ty + dy }));
  };
  const onPointerUp = () => {
    drag.current = null;
    setDragging(false);
  };

  const { s, tx, ty } = view;
  const toScreen = (p: Pt): Pt => [p[0] * s + tx, p[1] * s + ty];
  const k = 1 / s;

  // ---------- маршруты ----------
  const ordered = useMemo(() => {
    const rest = shipments.filter((x) => x.id !== focus?.id);
    return focus ? [...rest, focus] : rest;
  }, [shipments, focus]);

  const legGeometry = (leg: Leg) => edgeGeometry(edges.get(leg.edge_id) ?? { id: leg.edge_id, from: leg.from, to: leg.to });
  // Участки, по которым идёт выбранный груз, рисуются только его цветом.
  const focusCurves = new Set(focus?.route.legs.flatMap((leg) => legGeometry(leg) ?? []));
  const routePaths = ordered.flatMap((sh) => {
    const focused = sh.id === focus?.id;
    return sh.route.legs.flatMap((leg) => {
      const g = legGeometry(leg)?.filter((b) => focused || !focusCurves.has(b));
      if (!g?.length) return [];
      return [{ key: `${sh.id}-${leg.index}`, d: bezierPath(g), leg, color: legColor(leg, sh, focused), focused }];
    });
  });

  const focusEdgeIds = new Set(focus?.route.legs.map((l) => l.edge_id));
  const previewPaths =
    preview && focus
      ? preview.legs
          .filter((l) => !focusEdgeIds.has(l.edge_id))
          .flatMap((leg) => {
            const g = legGeometry(leg);
            return g ? [{ key: `preview-${leg.index}`, d: bezierPath(g), leg }] : [];
          })
      : [];

  const usedNodes = new Set<string>(Object.keys(NODE_LABELS).filter((id) => nodes.has(id)));
  shipments.forEach((sh) => sh.route.legs.forEach((l) => (usedNodes.add(l.from), usedNodes.add(l.to))));

  const stormPath = stormZone === "full" ? STORM_ZONE_FULL : stormZone === "north" ? STORM_ZONE_NORTH : null;

  const markers = shipments.flatMap((sh) => {
    const p = shipmentPos(sh, nodes, edges);
    if (!p) return [];
    const atNode = sh.current_leg == null;
    const [x, y] = toScreen(p);
    return [{ sh, x: atNode ? x + 16 : x, y: atNode ? y + 18 : y }];
  });

  const focusFrom = focus ? nodes.get(focus.origin) : null;
  const focusTo = focus ? nodes.get(focus.destination) : null;
  const controlsRight = insetRight + 21;

  return (
    <div
      ref={ref}
      className="relative min-w-0 flex-1 touch-none overflow-hidden bg-bg select-none"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      style={{ cursor: dragging ? "grabbing" : "grab" }}
    >
      <svg className="absolute inset-0 size-full" aria-label="Схема коридора «Север–Юг»">
        <defs>
          <pattern id="storm-hatch" width={10} height={10} patternUnits="userSpaceOnUse" patternTransform="rotate(32)">
            <line x1="0" y1="0" x2="0" y2="10" stroke="rgba(220,38,38,0.55)" strokeWidth={1.4} />
          </pattern>
        </defs>

        <g transform={`matrix(${s} 0 0 ${s} ${tx} ${ty})`}>
          <path d={LAND} fill="#E8EEF5" stroke="#CDD7E4" strokeWidth={1.1 * k} strokeLinejoin="round" />
          <path d={INLAND_SEA} fill="#D5E4F0" stroke="#B7CADA" strokeWidth={1.1 * k} />
          <path d={CASPIAN} fill="#C5DBEC" stroke="#8FB0C8" strokeWidth={1.2 * k} strokeLinejoin="round" />
          {CASPIAN_CONTOURS.map((d, i) => (
            <path key={i} d={d} fill="none" stroke="rgba(8,127,140,0.18)" strokeWidth={1 * k} strokeLinejoin="round" />
          ))}
          {layers.borders &&
            BORDERS.map((d, i) => (
              <path
                key={i}
                d={d}
                fill="none"
                stroke="#A8B8C9"
                strokeWidth={1.1 * k}
                strokeDasharray={`${2.6 * k} ${3.4 * k}`}
                strokeLinejoin="round"
              />
            ))}
          {layers.grid && <Grid k={k} />}

          {stormPath && (
            <g>
              <path d={stormPath} fill="rgba(220,38,38,0.14)" />
              <path d={stormPath} fill="url(#storm-hatch)" />
              <path
                d={stormPath}
                fill="none"
                stroke="rgba(220,38,38,0.65)"
                strokeWidth={1.1 * k}
                strokeDasharray={`${4 * k} ${3 * k}`}
              />
            </g>
          )}

          {routePaths.map((r) => (
            <path
              key={`${r.key}-casing`}
              d={r.d}
              fill="none"
              stroke={ROUTE.casing}
              strokeWidth={(r.focused ? 7 : 6) * k}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {routePaths.map((r) => {
            const st = dash(r.leg.mode, k);
            return (
              <path
                key={r.key}
                d={r.d}
                fill="none"
                stroke={r.color}
                strokeOpacity={r.focused ? 1 : 0.85}
                strokeWidth={(r.leg.mode === "road" ? 3.2 : 2.6) * k}
                strokeDasharray={st.dasharray}
                strokeLinecap={st.cap}
                strokeLinejoin="round"
              />
            );
          })}

          {previewPaths.map((r) => (
            <path
              key={`${r.key}-casing`}
              d={r.d}
              fill="none"
              stroke={ROUTE.casing}
              strokeWidth={7 * k}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {previewPaths.map((r) => {
            const st = dash(r.leg.mode, k);
            return (
              <path
                key={r.key}
                d={r.d}
                fill="none"
                stroke={ROUTE.preview}
                strokeWidth={(r.leg.mode === "road" ? 3.2 : 2.6) * k}
                strokeDasharray={st.dasharray}
                strokeLinecap={st.cap}
                strokeLinejoin="round"
              />
            );
          })}
        </g>

        {COUNTRY_LABELS.map((c) => {
          const [x, y] = toScreen([c.x, c.y]);
          return (
            <text
              key={c.text.join(" ")}
              x={x}
              y={y}
              textAnchor={c.anchor}
              dominantBaseline="central"
              fill={c.sea ? "var(--color-cyan)" : "var(--color-muted)"}
              fontSize={c.sea ? 11 : 9.5}
              fontWeight={700}
              letterSpacing={c.sea ? "0.2em" : "0.16em"}
              className="pointer-events-none"
            >
              {c.text.map((t, i) => (
                <tspan key={t} x={x} dy={i === 0 ? 0 : 17}>
                  {t}
                </tspan>
              ))}
            </text>
          );
        })}

        {[...usedNodes].map((id) => {
          const p = nodePos(id);
          if (!p) return null;
          const [x, y] = toScreen(p);
          const label = NODE_LABELS[id];
          const node = nodes.get(id);
          return (
            <g key={id} className="pointer-events-none">
              {label && (
                <circle cx={x} cy={y} r={4.6} fill={id === checkpointNode ? "var(--color-rerouted)" : "var(--color-panel)"} stroke="var(--color-text)" strokeWidth={1.8} />
              )}
              {label && node && (
                <text
                  x={x + label.dx}
                  y={y + label.dy}
                  textAnchor={label.anchor}
                  dominantBaseline="central"
                  fill="var(--color-text)"
                  fontSize={11}
                  fontWeight={700}
                >
                  {shortNodeName(node.name)}
                </text>
              )}
            </g>
          );
        })}

        {markers.map(({ sh, x, y }) => (
          <g
            key={sh.id}
            transform={`translate(${x} ${y})`}
            className="cursor-pointer"
            data-map-ui
            onClick={() => onSelect(sh.id)}
          >
            <rect
              x={-9.5}
              y={-8.75}
              width={19}
              height={17.5}
              rx={5}
              fill={MARKER_FILL[sh.display_status]}
              stroke="var(--color-panel)"
              strokeOpacity={0.9}
              strokeWidth={1}
            />
            <text textAnchor="middle" dominantBaseline="central" y={0.5} fill="var(--color-panel)" fontSize={10.5} fontWeight={700}>
              {shipmentIndex(sh.id)}
            </text>
            <title>{`${sh.title}: ${sh.display_status}`}</title>
          </g>
        ))}
      </svg>

      {layers.waves &&
        weather?.points.map((pt) => {
          const chip = WAVE_CHIPS[pt.node_id];
          const p = nodePos(pt.node_id);
          if (!chip || !p) return null;
          const [x, y] = toScreen(p);
          const w = pointWave(pt, calmWaves);
          return (
            <div
              key={pt.node_id}
              className="pointer-events-none absolute flex h-[20px] items-center gap-[6px] rounded-[6px] border bg-field pr-[8px] pl-[7px] text-[11px] leading-none font-bold"
              style={{
                left: x + chip.dx,
                top: y + chip.dy,
                color: w.storm ? "var(--color-risk)" : "var(--color-cyan)",
                borderColor: w.storm ? "var(--color-risk-line)" : "var(--color-line)",
                background: w.storm ? "var(--color-risk-soft)" : "var(--color-panel)",
              }}
            >
              <WavesIcon size={12} strokeWidth={1.8} />
              <span className="tnum">{formatDecimal(w.value)}&nbsp;м</span>
            </div>
          );
        })}

      {focus && (
        <div
          data-map-ui
          className="absolute top-5 left-5 flex h-[49px] min-w-[200px] items-center gap-[13px] rounded-[9px] border border-line-strong bg-field pr-[18px] pl-[13px]"
        >
          <RouteIcon size={15} className="text-cyan" />
          <div>
            <div className="text-[14px] leading-[17px] font-bold">
              {focusFrom ? shortNodeName(focusFrom.name) : focus.origin} → {focusTo ? shortNodeName(focusTo.name) : focus.destination}
            </div>
            <div className="mt-[2px] text-[11.5px] leading-[14px] text-muted">Коридор «Север–Юг»</div>
          </div>
        </div>
      )}

      <div
        data-map-ui
        className="absolute top-6 flex flex-col gap-[9px] transition-[right] duration-300"
        style={{ right: controlsRight }}
      >
        <div className="relative">
          <MapButton label="Слои" active={layersOpen} onClick={() => setLayersOpen((v) => !v)}>
            <LayersIcon size={16} />
          </MapButton>
          {layersOpen && (
            <div className="absolute top-0 right-[44px] w-[168px] rounded-[10px] border border-line-strong bg-panel p-[6px] text-[12.5px] font-semibold shadow-[0_16px_40px_var(--color-shadow)]">
              {(
                [
                  ["waves", "Волна в портах"],
                  ["borders", "Границы"],
                  ["grid", "Сетка"],
                ] as const
              ).map(([key, title]) => (
                <label key={key} className="flex cursor-pointer items-center gap-[9px] rounded-[7px] px-[9px] py-[8px] hover:bg-tile">
                  <input
                    type="checkbox"
                    checked={layers[key]}
                    onChange={(e) => setLayers((l) => ({ ...l, [key]: e.target.checked }))}
                    className="accent-action"
                  />
                  {title}
                </label>
              ))}
            </div>
          )}
        </div>
        <MapButton label="Приблизить" onClick={() => zoomAt(1.3, (size.w - insetRight) / 2, size.h / 2, true)}>
          <PlusIcon size={16} />
        </MapButton>
        <MapButton label="Отдалить" onClick={() => zoomAt(1 / 1.3, (size.w - insetRight) / 2, size.h / 2, true)}>
          <MinusIcon size={16} />
        </MapButton>
        <MapButton label="Показать маршрут" onClick={() => animateTo(targetView())}>
          <LocateIcon size={16} />
        </MapButton>
      </div>

      <div
        data-map-ui
        className="absolute bottom-[21px] left-5 flex h-[42px] items-center rounded-[10px] border border-line-strong bg-field pr-[20px] pl-[14px] text-[12px] font-bold"
      >
        <LegendItem icon={<RailIcon size={14} />} label="Ж/д" pattern="rail" />
        <LegendItem icon={<SeaIcon size={14} />} label="Море" pattern="sea" />
        <LegendItem icon={<RoadIcon size={14} />} label="Авто" pattern="road" last />
      </div>

      <div
        className="pointer-events-none absolute bottom-[22px] text-right text-[9.5px] leading-[13px] text-muted transition-[right] duration-300"
        style={{ right: insetRight + 24 }}
      >
        <div>
          Схема маршрутов
          {freshness && <span className={freshness.stale ? "text-warn" : undefined}> · {freshness.text}</span>}
        </div>
        <div>Расписание и загрузка портов — демо-данные</div>
      </div>
    </div>
  );
}

function Grid({ k }: { k: number }) {
  const lines: React.ReactNode[] = [];
  const x0 = BOX.x - 3000;
  const x1 = BOX.x + 4000;
  const y0 = -3000;
  const y1 = 3800;
  for (let x = Math.ceil(x0 / GRID_DX) * GRID_DX; x <= x1; x += GRID_DX) {
    lines.push(<line key={`x${x}`} x1={x} y1={y0} x2={x} y2={y1} />);
  }
  for (let y = GRID_Y0 + Math.ceil((y0 - GRID_Y0) / GRID_DY) * GRID_DY; y <= y1; y += GRID_DY) {
    lines.push(<line key={`y${y}`} x1={x0} y1={y} x2={x1} y2={y} />);
  }
  return (
    <g stroke="var(--color-shadow)" strokeWidth={1.6 * k}>
      {lines}
    </g>
  );
}

function MapButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string;
  active?: boolean;
  onClick(): void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={`flex size-[35px] items-center justify-center rounded-[9px] border border-line-strong text-text transition-colors hover:bg-tile ${
        active ? "bg-tile" : "bg-panel"
      }`}
    >
      {children}
    </button>
  );
}

function LegendItem({
  icon,
  label,
  pattern,
  last,
}: {
  icon: React.ReactNode;
  label: string;
  pattern: "rail" | "sea" | "road";
  last?: boolean;
}) {
  return (
    <div className={`flex items-center ${last ? "" : "mr-[21px]"}`}>
      <span className="text-transit-text">{icon}</span>
      <span className="ml-[9px]">{label}</span>
      <svg width={33} height={4} className="ml-[10px]" aria-hidden>
        <line
          x1={pattern === "road" ? 1.5 : 0}
          y1={2}
          x2={33}
          y2={2}
          stroke="var(--color-cyan)"
          strokeWidth={pattern === "road" ? 2.2 : 2}
          strokeDasharray={pattern === "sea" ? "6 3" : pattern === "road" ? "0.01 4.2" : undefined}
          strokeLinecap={pattern === "road" ? "round" : "butt"}
        />
      </svg>
    </div>
  );
}
