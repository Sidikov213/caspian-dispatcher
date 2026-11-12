"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type {
  AcceptResult,
  Alert,
  Block,
  Edge,
  Graph,
  GraphNode,
  LedgerVerify,
  Pass,
  Scenario,
  ScenarioPreset,
  Shipment,
  Stats,
  Weather,
} from "./types";

const POLL_MS = 3000;

export interface Dashboard {
  graph: Graph | null;
  nodes: Map<string, GraphNode>;
  edges: Map<string, Edge>;
  shipments: Shipment[];
  weather: Weather | null;
  stats: Stats | null;
  alerts: Alert[];
  presets: ScenarioPreset[];
  scenario: Scenario | null;
  passes: Map<string, Pass>;
  ledger: Block[];
  /** Алерт, принятый в этой сессии (с сайта или из Telegram): для подтверждения «Маршрут изменён». */
  justAccepted: { id: string; at: number } | null;
  /** Результат последней проверки реестра; `checked` — сколько записей проверено. */
  ledgerCheck: (LedgerVerify & { checked: number }) | null;
  verifying: boolean;
  error: string | null;
  loading: boolean;
  runScenario(preset: string): Promise<void>;
  resetDemo(): Promise<void>;
  /** Принять вариант алерта; без `optionId` — рекомендованный. Возвращает null при ошибке. */
  accept(alertId: string, optionId?: string): Promise<AcceptResult | null>;
  reject(alertId: string): Promise<boolean>;
  verifyLedger(): Promise<void>;
  tamperLedger(index: number): Promise<void>;
}

export function useDashboard(): Dashboard {
  const [graph, setGraph] = useState<Graph | null>(null);
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [weather, setWeather] = useState<Weather | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [presets, setPresets] = useState<ScenarioPreset[]>([]);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [passes, setPasses] = useState<Map<string, Pass>>(new Map());
  const [ledger, setLedger] = useState<Block[]>([]);
  const [ledgerCheck, setLedgerCheck] = useState<(LedgerVerify & { checked: number }) | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [justAccepted, setJustAccepted] = useState<{ id: string; at: number } | null>(null);
  const alertsRef = useRef<Alert[]>([]);
  const ledgerLenRef = useRef(-1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const wsOpen = useRef(false);

  const fail = useCallback((e: unknown) => setError(e instanceof Error ? e.message : String(e)), []);

  const loadPasses = useCallback(async (list: Shipment[]) => {
    const ids = list.map((s) => s.pass_id).filter((id): id is string => !!id);
    const loaded = await Promise.all(ids.map((id) => api.getPass(id).catch(() => null)));
    setPasses(new Map(loaded.filter((p): p is Pass => !!p).map((p) => [p.id, p])));
  }, []);

  const verifyLedger = useCallback(async () => {
    setVerifying(true);
    try {
      const [res, blocks] = await Promise.all([api.verifyLedger(), api.getLedger()]);
      setLedger(blocks);
      setLedgerCheck({ ...res, checked: blocks.length });
    } catch (e) {
      fail(e);
    } finally {
      setVerifying(false);
    }
  }, [fail]);

  const refreshLive = useCallback(async () => {
    const [sh, st, al, lg] = await Promise.all([api.getShipments(), api.getStats(), api.getAlerts(), api.getLedger()]);
    setShipments(sh);
    setStats(st);
    setAlerts(al);
    setLedger(lg);
    const turned = al.find((a) => a.status === "accepted" && alertsRef.current.find((p) => p.id === a.id)?.status === "new");
    if (turned) setJustAccepted({ id: turned.id, at: Date.now() });
    alertsRef.current = al;
    // Новая запись в реестре — проверяем цепочку заново; дальше проверка по кнопке.
    if (lg.length !== ledgerLenRef.current) {
      ledgerLenRef.current = lg.length;
      verifyLedger().catch(() => undefined);
    }
    setError(null);
    await loadPasses(sh);
  }, [loadPasses, verifyLedger]);

  const refreshWeather = useCallback(async () => {
    setWeather(await api.getWeather());
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [g, p] = await Promise.all([api.getGraph(), api.getScenarioPresets()]);
        if (cancelled) return;
        setGraph(g);
        setPresets(p);
        await Promise.all([refreshLive(), refreshWeather()]);
      } catch (e) {
        if (!cancelled) fail(e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshLive, refreshWeather, fail]);

  useEffect(() => {
    const url = api.wsUrl();
    if (!url) return;
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const connect = () => {
      ws = new WebSocket(url);
      ws.onopen = () => (wsOpen.current = true);
      ws.onclose = () => {
        wsOpen.current = false;
        if (!closed) retry = setTimeout(connect, 5000);
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data as string) as { type: string };
        if (msg.type === "weather.updated") refreshWeather().catch(fail);
        else refreshLive().catch(fail);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, [refreshLive, refreshWeather, fail]);

  useEffect(() => {
    const t = setInterval(() => {
      if (!wsOpen.current) refreshLive().catch(fail);
    }, POLL_MS);
    return () => clearInterval(t);
  }, [refreshLive, fail]);

  const runScenario = useCallback(
    async (preset: string) => {
      try {
        const res = await api.createScenario(preset);
        setScenario(res.scenario);
        await Promise.all([refreshLive(), refreshWeather()]);
      } catch (e) {
        fail(e);
      }
    },
    [refreshLive, refreshWeather, fail],
  );

  const resetDemo = useCallback(async () => {
    try {
      await api.resetDemo();
      setScenario(null);
      await Promise.all([refreshLive(), refreshWeather()]);
      await verifyLedger();
    } catch (e) {
      fail(e);
    }
  }, [refreshLive, refreshWeather, verifyLedger, fail]);

  const accept = useCallback(
    async (alertId: string, optionId?: string) => {
      try {
        const res = await api.acceptAlert(alertId, { via: "web", ...(optionId ? { option_id: optionId } : {}) });
        await refreshLive();
        return res;
      } catch (e) {
        fail(e);
        // «Предложение устарело»: подтянуть актуальный алерт.
        refreshLive().catch(() => undefined);
        return null;
      }
    },
    [refreshLive, fail],
  );

  const reject = useCallback(
    async (alertId: string) => {
      try {
        await api.rejectAlert(alertId);
        await refreshLive();
        return true;
      } catch (e) {
        fail(e);
        return false;
      }
    },
    [refreshLive, fail],
  );

  const tamperLedger = useCallback(
    async (index: number) => {
      try {
        await api.tamperLedger(index);
      } catch (e) {
        fail(e);
      }
    },
    [fail],
  );

  // Сценарий нужен и после решения: от него зависят подписи (ветер шторма, заголовок алерта).
  const activeScenarioId = (alerts.find((a) => a.status === "new") ?? alerts[0])?.scenario_id ?? null;
  useEffect(() => {
    if (!activeScenarioId || scenario?.id === activeScenarioId || !api.getScenario) return;
    api.getScenario(activeScenarioId).then((s) => s && setScenario(s), fail);
  }, [activeScenarioId, scenario, fail]);

  const nodes = useMemo(() => new Map((graph?.nodes ?? []).map((n) => [n.id, n])), [graph]);
  const edges = useMemo(() => new Map((graph?.edges ?? []).map((e) => [e.id, e])), [graph]);

  return {
    graph,
    nodes,
    edges,
    shipments,
    weather,
    stats,
    alerts,
    presets,
    scenario,
    passes,
    ledger,
    justAccepted,
    ledgerCheck,
    verifying,
    error,
    loading,
    runScenario,
    resetDemo,
    accept,
    reject,
    verifyLedger,
    tamperLedger,
  };
}
