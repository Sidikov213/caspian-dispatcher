"use client";

import "leaflet/dist/leaflet.css";
import "./RealMap.css";

import type * as LT from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { pickFocus, pointWave } from "@/lib/derive";
import { formatDecimal, shipmentIndex, shortNodeName } from "@/lib/format";
import { useSiteTheme, type SiteTheme } from "@/lib/theme";
import type { Alert, DisplayStatus, Edge, GraphNode, Leg, Mode, Route, Shipment, Weather } from "@/lib/types";
import { CorridorMap } from "./CorridorMap";
import { MinusIcon, PlusIcon, RailIcon, RoadIcon, RouteIcon, SeaIcon } from "./icons";

type LatLng = [number, number];

interface Props {
  nodes: Map<string, GraphNode>;
  edges: Map<string, Edge>;
  shipments: Shipment[];
  weather: Weather | null;
  focusId: string | null;
  preview?: Route | null;
  calmWaves?: boolean;
  checkpointNode?: string | null;
  insetRight: number;
  freshness: { text: string; stale: boolean } | null;
  onSelect(id: string): void;
  /** Клик по узлу (порт, станция): карточка с фактами из Node.facts. */
  onNode?(id: string): void;
  /** Зона угрозы активного сценария (Scenario.zone); сайт её не угадывает. */
  zone?: LatLng[] | null;
  /** Тип угрозы зоны (Scenario.hazard): лёд — синим, шторм — красным, затор — жёлтым. */
  zoneHazard?: string | null;
  /** Алерты: исходный маршрут перестроенного груза берётся из принятого алерта (from_route). */
  alerts?: Alert[];
  /** Прежняя SVG-схема — запасной вариант, если подложка не загрузилась. */
  stormZone?: React.ComponentProps<typeof CorridorMap>["stormZone"];
}

// ---------- подложка: адреса в настройках сборки, цепочка основная → запасная → SVG-схема ----------
// CARTO без ключа отдаёт тайлы с водяным знаком «API KEY REQUIRED» (код 200 — запасная цепочка такое не
// ловит), поэтому по умолчанию OpenStreetMap. С ключом CARTO подключается переменными, например
// NEXT_PUBLIC_TILE_URL_DARK=https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?api_key=…
const OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILES = {
  light: process.env.NEXT_PUBLIC_TILE_URL_LIGHT || OSM,
  dark: process.env.NEXT_PUBLIC_TILE_URL_DARK || OSM,
  fallback: process.env.NEXT_PUBLIC_TILE_URL_FALLBACK || "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
};
/** Своей тёмной подложки нет — в тёмной теме приглушаем светлую CSS-фильтром. */
const DIM_IN_DARK = !process.env.NEXT_PUBLIC_TILE_URL_DARK;
const ATTR_OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">участники OpenStreetMap</a>';
const ATTR_CARTO = `${ATTR_OSM} &copy; <a href="https://carto.com/attributions">CARTO</a>`;
const attributionFor = (url: string) => (url.includes("cartocdn") ? ATTR_CARTO : ATTR_OSM);
/** Подложка не загрузилась — только если за это время не пришёл ни один тайл. */
const TILE_TIMEOUT_MS = 5000;
type Stage = "primary" | "fallback" | "svg";

// ---------- вид: рамка из данных графа, не координаты в коде ----------
/** Каспий от Волгограда до Тегерана: рамка по узлам у моря (порты) с полями. */
function caspianBounds(nodes: Map<string, GraphNode>): LatLng[] {
  const sea = [...nodes.values()].filter((n) => n.type === "port" && n.id !== "mumbai" && n.id !== "bandar_abbas");
  const tehran = nodes.get("tehran");
  const pts = [...sea, ...(tehran ? [tehran] : [])];
  if (!pts.length) return [];
  const lats = pts.map((n) => n.lat);
  const lons = pts.map((n) => n.lon);
  // поля: на север — до широты Волгограда (≈ 2,3° выше устья Волги), к краям — по 1,5°
  return [[Math.min(...lats) - 0.8, Math.min(...lons) - 1.5], [Math.max(...lats) + 2.3, Math.max(...lons) + 1.5]];
}
function corridorBounds(nodes: Map<string, GraphNode>): LatLng[] {
  const all = [...nodes.values()];
  return all.length
    ? [[Math.min(...all.map((n) => n.lat)) - 1, Math.min(...all.map((n) => n.lon)) - 1],
       [Math.max(...all.map((n) => n.lat)) + 1, Math.max(...all.map((n) => n.lon)) + 1]]
    : [];
}

// ---------- стиль линий ----------
const STATUS_COLOR: Record<DisplayStatus, string> = {
  in_transit: "var(--color-transit)",
  at_risk: "var(--color-risk)",
  rerouted: "var(--color-rerouted)",
  planned: "var(--color-muted)",
  delivered: "var(--color-muted)",
};
const DASH: Record<Mode, string | undefined> = { rail: undefined, sea: "12 10", road: "1 10" };

function edgeLine(edge: Edge | undefined, nodes: Map<string, GraphNode>, from?: string): LatLng[] | null {
  if (!edge) return null;
  const a = nodes.get(edge.from);
  const b = nodes.get(edge.to);
  if (!a || !b) return null;
  const pts: LatLng[] = [[a.lat, a.lon], ...(edge.path ?? []), [b.lat, b.lon]];
  return from && from === edge.to ? pts.reverse() : pts;
}

function legLines(route: Route, edges: Map<string, Edge>, nodes: Map<string, GraphNode>) {
  return route.legs
    .map((leg: Leg) => ({ leg, pts: edgeLine(edges.get(leg.edge_id), nodes, leg.from) }))
    .filter((x): x is { leg: Leg; pts: LatLng[] } => !!x.pts);
}

export function RealMap(props: Props) {
  const { nodes, edges, shipments, weather, focusId, preview, calmWaves, checkpointNode, insetRight, freshness, onSelect, zone, alerts } = props;
  const theme = useSiteTheme();
  const host = useRef<HTMLDivElement>(null);
  const L = useRef<typeof LT | null>(null);
  const map = useRef<LT.Map | null>(null);
  const tiles = useRef<LT.TileLayer | null>(null);
  const layer = useRef<LT.LayerGroup | null>(null);
  const loaded = useRef(false);
  const [stage, setStage] = useState<Stage>("primary");
  const [ready, setReady] = useState(false);
  const [wide, setWide] = useState(false);
  /** Размер контейнера «ширина×высота»; пусто, пока раскладка не дала обе стороны. */
  const [size, setSize] = useState("");
  const onSelectRef = useRef(onSelect);
  const onNodeRef = useRef(props.onNode);
  const themeRef = useRef<SiteTheme>(theme);
  useEffect(() => {
    onSelectRef.current = onSelect;
    onNodeRef.current = props.onNode;
    themeRef.current = theme;
  });

  const focus = useMemo(() => pickFocus(shipments, focusId), [shipments, focusId]);

  // ---------- создание карты и цепочка подложек ----------
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let resize: ResizeObserver | undefined;
    (async () => {
      const lib = (await import("leaflet")).default;
      if (cancelled || !host.current) return;
      L.current = lib;
      const m = lib.map(host.current, { zoomControl: false, attributionControl: true, minZoom: 3, maxZoom: 11, zoomSnap: 0.25, zoomDelta: 0.5 });
      m.attributionControl.setPrefix(false);
      // без вида Leaflet откладывает добавление слоёв (и запрос тайлов); точный вид ставит эффект ниже
      m.setView([0, 0], 3);
      map.current = m;      layer.current = lib.layerGroup().addTo(m);

      const add = (url: string) => {
        tiles.current?.remove();
        const t = lib.tileLayer(url, { attribution: attributionFor(url), subdomains: "abcd", maxZoom: 19, crossOrigin: true });
        t.on("tileload", () => { loaded.current = true; });
        t.addTo(m);
        tiles.current = t;
      };
      // контейнер получает размер позже (флекс-раскладка): без invalidateSize Leaflet не знает размеров
      const hasSize = () => !!host.current && host.current.clientWidth > 0 && host.current.clientHeight > 0;
      resize = new ResizeObserver(() => {
        m.invalidateSize();
        if (hasSize()) setSize(`${host.current!.clientWidth}x${host.current!.clientHeight}`);
      });
      resize.observe(host.current);
      if (hasSize()) setSize(`${host.current.clientWidth}x${host.current.clientHeight}`);  // размер уже есть
      add(themeRef.current === "dark" ? TILES.dark : TILES.light);
      // отсчёт 5 с — с момента, когда у карты есть размер и она реально запросила тайлы;
      // сорвавшийся тайл не в счёт: переключаемся, только если не пришёл ни один
      const startChain = () => {
        timer = setTimeout(() => {
          if (loaded.current || cancelled) return;
          setStage("fallback");
          add(TILES.fallback);
          timer = setTimeout(() => { if (!loaded.current && !cancelled) setStage("svg"); }, TILE_TIMEOUT_MS);
        }, TILE_TIMEOUT_MS);
      };
      const waitSize = () => {
        if (cancelled) return;
        if (hasSize()) startChain();
        else timer = setTimeout(waitSize, 200);
      };
      waitSize();
      setReady(true);
    })().catch((e) => {
      console.error("Карта не создалась, показываем схему:", e);
      if (!cancelled) setStage("svg");
    });
    return () => {
      cancelled = true;
      clearTimeout(timer);
      resize?.disconnect();
      map.current?.remove();
      map.current = null;
    };
  }, []);

  // тема сайта сменилась — меняем основную подложку (если светлая и тёмная заданы разными адресами)
  useEffect(() => {
    if (stage === "primary" && tiles.current) tiles.current.setUrl(theme === "dark" ? TILES.dark : TILES.light);
  }, [theme, stage]);
  const dim = theme === "dark" && (DIM_IN_DARK || stage === "fallback");

  // вид по умолчанию — Каспий; «Весь коридор» — до Мумбаи. Пересчёт — когда известны обе стороны контейнера
  useEffect(() => {
    const m = map.current;
    if (!ready || !size || !m || !nodes.size) return;
    m.invalidateSize();
    const b = wide ? corridorBounds(nodes) : caspianBounds(nodes);
    if (b.length) m.fitBounds(b as LT.LatLngBoundsExpression, { paddingTopLeft: [24, 24], paddingBottomRight: [insetRight + 24, 72], animate: false });
  }, [ready, size, nodes, wide, insetRight]);

  // ---------- слои данных ----------
  useEffect(() => {
    const lib = L.current;
    const g = layer.current;
    if (!ready || !lib || !g) return;
    g.clearLayers();
    const net = theme === "dark" ? "#5B6B86" : "#94A3B8";

    // 1. зона угрозы — из Scenario.zone
    if (zone && zone.length >= 3) {
      const zc = props.zoneHazard === "ice" ? "var(--color-transit)" : props.zoneHazard === "congestion" || props.zoneHazard === "customs" ? "var(--color-warn)" : "var(--color-risk)";
      lib.polygon(zone, { color: zc, weight: 2, dashArray: "6 6", fillColor: zc, fillOpacity: props.zoneHazard === "ice" ? 0.2 : 0.14, interactive: false }).addTo(g);
    }

    // 2. вся сеть коридора: тонко и приглушённо, стиль по виду транспорта
    for (const e of edges.values()) {
      const pts = edgeLine(e, nodes);
      if (pts) lib.polyline(pts, { color: net, weight: 3, opacity: 0.75, dashArray: DASH[e.mode], lineCap: "round", interactive: false }).addTo(g);
    }

    // 3. маршруты грузов: цвет — статус груза; выбранный толще
    const drawRoute = (route: Route, color: string, weight: number, opacity = 1, dash?: string) => {
      for (const { leg, pts } of legLines(route, edges, nodes)) {
        lib.polyline(pts, { color, weight, opacity, dashArray: dash ?? DASH[leg.mode], lineCap: "round", interactive: false }).addTo(g);
      }
    };
    for (const s of shipments) {
      if (s.id === focus?.id) continue;
      drawRoute(s.route, STATUS_COLOR[s.display_status], 4, 0.55);
    }
    if (focus) {
      if (focus.rerouted) {   // прежний маршрут — из принятого алерта, серым пунктиром
        const old = (alerts ?? []).filter((a) => a.status === "accepted")
          .flatMap((a) => a.items).find((i) => i.shipment_id === focus.id)?.from_route;
        if (old) drawRoute(old, theme === "dark" ? "#CBD5E1" : "#475569", 5, 0.95, "4 10");
      }
      drawRoute(focus.route, STATUS_COLOR[focus.display_status], 7);
      if (preview) drawRoute(preview, "var(--color-transit)", 6, 0.9, "10 8");
    }

    // 4. узлы и подписи (не меньше 14 px, с подложкой под текстом)
    for (const n of nodes.values()) {
      const dot = lib.circleMarker([n.lat, n.lon], {
        radius: n.type === "border" ? 4 : 6, color: theme === "dark" ? "#E6EDF7" : "var(--color-text)", weight: 2,
        fillColor: theme === "dark" ? "#0B1220" : "var(--color-panel)", fillOpacity: 1,
      }).addTo(g);
      if (n.type !== "border") {
        dot.bindTooltip(shortNodeName(n.name), { permanent: true, direction: "auto", className: "rm-node", offset: [8, 0], interactive: true });
      }
      dot.on("click", () => onNodeRef.current?.(n.id));
    }
    if (checkpointNode) {
      const c = nodes.get(checkpointNode);
      if (c) lib.circleMarker([c.lat, c.lon], { radius: 10, color: "var(--color-rerouted)", weight: 3, fillColor: "#22C55E", fillOpacity: 0.9 }).addTo(g);
    }

    // 5. волна у всех портов из /api/weather; красным выше предела
    for (const p of weather?.points ?? []) {
      const n = nodes.get(p.node_id);
      if (!n) continue;
      const w = pointWave(p, calmWaves);
      lib.circleMarker([n.lat, n.lon], { radius: 0, opacity: 0, fillOpacity: 0, interactive: false })
        .bindTooltip(`≈ ${formatDecimal(w.value)} м`, { permanent: true, direction: "bottom", offset: [0, 10], className: `rm-wave${w.storm ? " storm" : ""}` })
        .addTo(g);
    }

    // 6. грузы — маркеры с номером в цвете статуса; клик открывает двойник
    for (const s of shipments) {
      if (!s.position) continue;
      const isFocus = s.id === focus?.id && !!focusId;
      const size = isFocus ? 36 : 30;
      const icon = lib.divIcon({
        className: "",
        html: `<div class="rm-ship${isFocus ? " focus" : ""}" style="background:${STATUS_COLOR[s.display_status]}">${shipmentIndex(s.id)}</div>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });
      lib.marker([s.position.lat, s.position.lon], { icon, zIndexOffset: isFocus ? 2000 : 1000, title: s.title, keyboard: true })
        .on("click", () => onSelectRef.current(s.id))
        .addTo(g);
    }
  }, [ready, theme, nodes, edges, shipments, weather, focus, focusId, preview, calmWaves, checkpointNode, zone, alerts, props.zoneHazard]);

  if (stage === "svg") {
    // подложка не пришла ни с CARTO, ни с OSM — прежняя схема, демо от тайлов не зависит
    const { zone: _z, alerts: _a, zoneHazard: _h, ...rest } = props;
    void _z;
    void _a;
    void _h;
    return <CorridorMap {...rest} />;
  }

  const btn = "flex size-[40px] items-center justify-center rounded-[10px] border border-line-strong bg-field text-text shadow-sm hover:bg-tile";
  return (
    <div className="relative min-w-0 flex-1 overflow-hidden">
      <div ref={host} className={`rm rm-${theme}${dim ? " rm-dim" : ""}`} aria-label="Карта коридора «Север–Юг»" />

      <div className="absolute top-5 z-[500] flex flex-col gap-[8px] transition-[right] duration-300" style={{ right: insetRight + 21 }}>
        <button type="button" aria-label="Приблизить" className={btn} onClick={() => map.current?.zoomIn()}><PlusIcon size={18} /></button>
        <button type="button" aria-label="Отдалить" className={btn} onClick={() => map.current?.zoomOut()}><MinusIcon size={18} /></button>
      </div>
      <button
        type="button"
        onClick={() => setWide((w) => !w)}
        className="absolute top-5 left-5 z-[500] flex h-[40px] items-center gap-[8px] rounded-[10px] border border-line-strong bg-field px-[14px] text-[14px] font-bold text-text shadow-sm hover:bg-tile"
      >
        <RouteIcon size={16} />
        {wide ? "Каспий" : "Весь коридор"}
      </button>

      <div className="absolute bottom-[21px] left-5 z-[500] flex h-[42px] items-center gap-[16px] rounded-[10px] border border-line-strong bg-field px-[14px] text-[13px] font-bold text-text">
        <span className="flex items-center gap-[6px]"><RailIcon size={14} />Ж/д <i className="inline-block h-[3px] w-[22px] rounded bg-current" /></span>
        <span className="flex items-center gap-[6px]"><SeaIcon size={14} />Море <i className="inline-block h-[3px] w-[22px] border-t-[3px] border-dashed border-current" /></span>
        <span className="flex items-center gap-[6px]"><RoadIcon size={14} />Авто <i className="inline-block h-[3px] w-[22px] border-t-[3px] border-dotted border-current" /></span>
      </div>

      <div
        className="pointer-events-none absolute bottom-[34px] z-[500] rounded-[6px] bg-field/85 px-[8px] py-[3px] text-right text-[11px] leading-[15px] text-muted transition-[right] duration-300"
        style={{ right: insetRight + 12 }}
      >
        <div>
          {stage === "fallback" ? "Запасная подложка" : "Карта коридора"}
          {freshness && <span className={freshness.stale ? "text-warn" : undefined}> · {freshness.text}</span>}
        </div>
        <div>Расписание и загрузка портов — демо-данные</div>
      </div>
    </div>
  );
}
