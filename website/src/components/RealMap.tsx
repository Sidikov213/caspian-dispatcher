"use client";

import "leaflet/dist/leaflet.css";
import "./RealMap.css";

import type * as LT from "leaflet";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { pickFocus, pointWave } from "@/lib/derive";
import { formatDecimal, shipmentIndex, shortNodeName } from "@/lib/format";
import { useSiteTheme, type SiteTheme } from "@/lib/theme";
import type { Alert, DisplayStatus, Edge, GraphNode, Leg, Mode, Route, Shipment, Weather } from "@/lib/types";
import { edgeLine, routeKey, routeTrack, trackPoint, trackS, type Track } from "@/lib/map/live";
import { CorridorMap } from "./CorridorMap";
import { LiveCard, LiveList } from "./LiveCard";
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

function legLines(route: Route, edges: Map<string, Edge>, nodes: Map<string, GraphNode>) {
  return route.legs
    .map((leg: Leg) => ({ leg, pts: edgeLine(edges.get(leg.edge_id), nodes, leg.from) }))
    .filter((x): x is { leg: Leg; pts: LatLng[] } => !!x.pts);
}

// ---------- живые грузы: значки по виду транспорта, вид сверху, нос на север — поворот по heading_deg ----------
const GLYPH: Record<Mode, string> = {
  rail: '<path d="M10 13V6.2Q10 3 14 3t4 3.2V13Z"/><rect x="10" y="15" width="8" height="10" rx="1.6"/><path d="M14 13v2M11.8 6.5h4.4"/>',
  road: '<rect x="9.5" y="2.8" width="9" height="6.4" rx="2.2"/><rect x="8.5" y="10.6" width="11" height="14.6" rx="1.6"/><path d="M11.5 5.4h5"/>',
  sea: '<path d="M14 2.6c4.3 3.4 5.4 7.2 5.4 11.2v9.6c0 1.2-.8 2-2 2h-6.8c-1.2 0-2-.8-2-2v-9.6c0-4 1.1-7.8 5.4-11.2Z"/><rect x="11" y="16.6" width="6" height="5" rx="1"/>',
};
const LIVE_PX = 28;
const ANIM_MS = 1500;
/** Значки ближе этого (px на текущем масштабе) собираются в один со счётчиком. */
const CLUSTER_PX = 22;
const STATUS_RANK: Record<DisplayStatus, number> = { at_risk: 3, rerouted: 2, in_transit: 1, planned: 0, delivered: 0 };

function liveHtml(s: Shipment, dim: boolean, picked: boolean): string {
  const p = s.position!;
  const cls = ["rm-live", s.display_status === "at_risk" ? "pulse" : "", dim ? "dim" : "", picked ? "picked" : "", p.waiting ? "wait" : ""]
    .filter(Boolean)
    .join(" ");
  return (
    `<div class="${cls}" style="--c:${STATUS_COLOR[s.display_status]}">` +
    `<svg class="rm-live-rot" viewBox="0 0 28 28" width="${LIVE_PX}" height="${LIVE_PX}" style="transform:rotate(${p.heading_deg}deg)">${GLYPH[p.mode]}</svg>` +
    `<span class="rm-live-no">${shipmentIndex(s.id)}</span></div>`
  );
}

function clusterHtml(list: Shipment[]): string {
  const top = [...list].sort((a, b) => STATUS_RANK[b.display_status] - STATUS_RANK[a.display_status])[0];
  return `<div class="rm-cluster${top.display_status === "at_risk" ? " pulse" : ""}" style="--c:${STATUS_COLOR[top.display_status]}">${list.length}</div>`;
}

const ease = (t: number) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

/** Состояние одного значка между обновлениями с сервера. */
interface Live {
  marker: LT.Marker;
  track: Track;
  key: string;
  /** Показанная точка — расстояние вдоль маршрута; null — ребра нет в маршруте, стоим в точке сервера. */
  s: number | null;
  from: number;
  to: number;
  t0: number;
  html: string;
}

export function RealMap(props: Props) {
  const { nodes, edges, shipments, weather, focusId, preview, calmWaves, checkpointNode, insetRight, freshness, onSelect, zone, alerts } = props;
  const theme = useSiteTheme();
  const host = useRef<HTMLDivElement>(null);
  const L = useRef<typeof LT | null>(null);
  const map = useRef<LT.Map | null>(null);
  const tiles = useRef<LT.TileLayer | null>(null);
  const layer = useRef<LT.LayerGroup | null>(null);
  const liveLayer = useRef<LT.LayerGroup | null>(null);
  const lives = useRef<Map<string, Live>>(new Map());
  const clusters = useRef<LT.Marker[]>([]);
  const raf = useRef<number | null>(null);
  /** Груз, выбранный кликом по значку: карточка и подсветка маршрута. */
  const [picked, setPicked] = useState<string | null>(null);
  /** Несколько грузов в одной точке: список по клику на счётчик. */
  const [group, setGroup] = useState<string[] | null>(null);
  const [zoomSeq, setZoomSeq] = useState(0);
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
    const liveMap = lives.current;
    (async () => {
      const lib = (await import("leaflet")).default;
      if (cancelled || !host.current) return;
      L.current = lib;
      const m = lib.map(host.current, { zoomControl: false, attributionControl: true, minZoom: 3, maxZoom: 11, zoomSnap: 0.25, zoomDelta: 0.5 });
      m.attributionControl.setPrefix(false);
      // без вида Leaflet откладывает добавление слоёв (и запрос тайлов); точный вид ставит эффект ниже
      m.setView([0, 0], 3);
      map.current = m;
      layer.current = lib.layerGroup().addTo(m);
      liveLayer.current = lib.layerGroup().addTo(m);
      // клик по пустому месту карты снимает выделение (значки и узлы клик дальше не пропускают)
      m.on("click", () => {
        setPicked(null);
        setGroup(null);
      });
      m.on("zoomend", () => setZoomSeq((n) => n + 1));

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
      if (raf.current) cancelAnimationFrame(raf.current);
      liveMap.clear();
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

    // 2. вся сеть коридора: тонко и приглушённо, стиль по виду транспорта; при выбранном значке — ещё тусклее
    const pickedShip = picked ? (shipments.find((x) => x.id === picked) ?? null) : null;
    for (const e of edges.values()) {
      const pts = edgeLine(e, nodes);
      if (pts) lib.polyline(pts, { color: net, weight: 3, opacity: pickedShip ? 0.35 : 0.75, dashArray: DASH[e.mode], lineCap: "round", interactive: false }).addTo(g);
    }

    // 3. маршруты грузов: цвет — статус груза; выбранный толще
    const drawRoute = (route: Route, color: string, weight: number, opacity = 1, dash?: string) => {
      for (const { leg, pts } of legLines(route, edges, nodes)) {
        lib.polyline(pts, { color, weight, opacity, dashArray: dash ?? DASH[leg.mode], lineCap: "round", interactive: false }).addTo(g);
      }
    };
    if (pickedShip) {
      // клик по значку: весь маршрут груза бирюзой, остальные тускнеют
      for (const s of shipments) if (s.id !== pickedShip.id) drawRoute(s.route, STATUS_COLOR[s.display_status], 3, 0.18);
      drawRoute(pickedShip.route, theme === "dark" ? "#0B1220" : "#FFFFFF", 11, 0.9, "");
      drawRoute(pickedShip.route, "var(--color-cyan)", 7, 1);
    }
    for (const s of pickedShip ? [] : shipments) {
      if (s.id === focus?.id) continue;
      drawRoute(s.route, STATUS_COLOR[s.display_status], 4, 0.55);
    }
    if (focus && !pickedShip) {
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
        fillColor: theme === "dark" ? "#0B1220" : "var(--color-panel)", fillOpacity: 1, bubblingMouseEvents: false,
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

    // 6. грузы — отдельный слой живых значков (ниже): он не пересоздаётся, значки едут плавно
  }, [ready, theme, nodes, edges, shipments, weather, focus, focusId, preview, calmWaves, checkpointNode, zone, alerts, props.zoneHazard, picked]);

  // ---------- живые грузы: значок едет к точке сервера вдоль линии маршрута ----------
  const tick = useCallback(function step() {
    raf.current = null;
    const now = performance.now();
    let more = false;
    for (const lv of lives.current.values()) {
      if (lv.s === null || lv.s === lv.to) continue;
      const k = Math.min((now - lv.t0) / ANIM_MS, 1);
      lv.s = k >= 1 ? lv.to : lv.from + (lv.to - lv.from) * ease(k);
      const { pt, heading } = trackPoint(lv.track, lv.s);
      lv.marker.setLatLng(pt);
      const rot = lv.marker.getElement()?.querySelector<SVGElement>(".rm-live-rot");
      if (rot && k < 1) rot.style.transform = `rotate(${heading}deg)`;
      if (k < 1) more = true;
    }
    if (more) raf.current = requestAnimationFrame(step);
  }, []);

  useEffect(() => {
    const lib = L.current;
    const g = liveLayer.current;
    const m = map.current;
    if (!ready || !lib || !g || !m) return;
    const icon = (html: string) => lib.divIcon({ className: "", html, iconSize: [LIVE_PX, LIVE_PX], iconAnchor: [LIVE_PX / 2, LIVE_PX / 2] });
    const seen = new Set<string>();
    const moving = shipments.filter((x) => x.position);
    for (const s of moving) {
      const pos = s.position!;
      seen.add(s.id);
      const html = liveHtml(s, !!picked && picked !== s.id, picked === s.id || (!picked && focusId === s.id));
      const key = routeKey(s);
      let lv = lives.current.get(s.id);
      if (!lv) {
        const track = routeTrack(s.route, edges, nodes);
        const at = trackS(track, pos);
        const marker = lib.marker([pos.lat, pos.lon], { icon: icon(html), zIndexOffset: 1000, title: s.title, keyboard: true, bubblingMouseEvents: false });
        marker.on("click", () => {
          setGroup(null);
          setPicked(s.id);
        });
        marker.addTo(g);
        lives.current.set(s.id, { marker, track, key, s: at, from: at ?? 0, to: at ?? 0, t0: 0, html });
        continue;
      }
      if (lv.html !== html) {
        lv.marker.setIcon(icon(html));
        lv.html = html;
      }
      lv.marker.setZIndexOffset(picked === s.id ? 3000 : 1000);
      // маршрут сменился (перестроение): показанную точку переносим на новую линию по ребру и доле пути
      let cur = lv.s;
      if (lv.key !== key) {
        const track = routeTrack(s.route, edges, nodes);
        if (cur !== null) {
          const c = cur;
          const old = lv.track.legs.find((l) => c >= l.start && c <= l.start + l.len);
          const same = old ? track.legs.find((l) => l.edge_id === old.edge_id) : undefined;
          cur = old && same ? same.start + (old.len ? ((c - old.start) / old.len) * same.len : 0) : null;
        }
        lv = Object.assign(lv, { track, key });
      }
      const target = trackS(lv.track, pos);
      if (target === null || cur === null) {
        lv.s = target;
        lv.from = lv.to = target ?? 0;
        lv.marker.setLatLng([pos.lat, pos.lon]);
      } else if (Math.abs(target - cur) > 1e-6) {
        lv.s = cur;
        lv.from = cur;
        lv.to = target;
        lv.t0 = performance.now();
      } else {
        lv.s = lv.from = lv.to = target;
        lv.marker.setLatLng([pos.lat, pos.lon]);
      }
      const rot = lv.marker.getElement()?.querySelector<SVGElement>(".rm-live-rot");
      if (rot && lv.s === lv.to) rot.style.transform = `rotate(${pos.heading_deg}deg)`;
    }
    for (const [id, lv] of lives.current) {
      if (seen.has(id)) continue;
      lv.marker.remove();
      lives.current.delete(id);
    }
    if (!raf.current) raf.current = requestAnimationFrame(tick);

    // несколько грузов в одной точке — один значок со счётчиком (по точкам сервера, на текущем масштабе)
    for (const c of clusters.current) c.remove();
    clusters.current = [];
    const pts = moving.map((x) => ({ s: x, p: m.latLngToLayerPoint([x.position!.lat, x.position!.lon]) }));
    const used = new Set<string>();
    for (const a of pts) {
      if (used.has(a.s.id)) continue;
      const near = pts.filter((b) => !used.has(b.s.id) && a.p.distanceTo(b.p) < CLUSTER_PX);
      if (near.length < 2) continue;
      near.forEach((b) => used.add(b.s.id));
      const list = near.map((b) => b.s);
      const c = lib.marker([a.s.position!.lat, a.s.position!.lon], {
        icon: lib.divIcon({ className: "", html: clusterHtml(list), iconSize: [32, 32], iconAnchor: [16, 16] }),
        zIndexOffset: 2500,
        title: `Грузов в точке: ${list.length}`,
        keyboard: true,
        bubblingMouseEvents: false,
      });
      c.on("click", () => {
        setPicked(null);
        setGroup(list.map((x) => x.id));
      });
      c.addTo(g);
      clusters.current.push(c);
    }
    for (const [id, lv] of lives.current) lv.marker.setOpacity(used.has(id) && picked !== id ? 0 : 1);
  }, [ready, shipments, edges, nodes, picked, focusId, zoomSeq, tick]);

  // выбранный груз исчез (сброс демо, доставлен) — снять выделение
  const pickedShipment = picked ? (shipments.find((x) => x.id === picked && x.position) ?? null) : null;
  useEffect(() => {
    if (picked && !pickedShipment) setPicked(null);
  }, [picked, pickedShipment]);
  const groupShipments = group ? shipments.filter((x) => group.includes(x.id) && x.position) : [];

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

      {pickedShipment && (
        <LiveCard
          shipment={pickedShipment}
          nodes={nodes}
          onOpen={() => {
            setPicked(null);
            onSelect(pickedShipment.id);
          }}
          onClose={() => setPicked(null)}
        />
      )}
      {!pickedShipment && groupShipments.length > 1 && (
        <LiveList
          shipments={groupShipments}
          onPick={(id) => {
            setGroup(null);
            setPicked(id);
          }}
          onClose={() => setGroup(null)}
        />
      )}

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
