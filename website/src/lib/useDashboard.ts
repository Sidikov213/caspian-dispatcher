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
  PlaybackSpeed,
  Sailing,
  Scenario,
  ScenarioPreset,
  Shipment,
  ShipmentCreate,
  Stats,
  Weather,
} from "./types";

const POLL_MS = 3000;
export const PLAYBACK_POLL_MS = 2000;

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
  sailings: Sailing[];
  ledger: Block[];
  /** Растёт при каждом сбросе демо (своём или по событию demo.reset): экраны закрывают окна и выбор. */
  resetSeq: number;
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
  /** Скорость ускоренного просмотра движения; null — сервер не поддерживает (моки). */
  playback: PlaybackSpeed | null;
  setPlayback(speed: PlaybackSpeed): Promise<void>;
  /** Новый груз; ошибка проверки сервера пробрасывается вызывающему (форма показывает поля). */
  createShipment(body: ShipmentCreate): Promise<Shipment>;
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
  const [sailings, setSailings] = useState<Sailing[]>([]);
  const [resetSeq, setResetSeq] = useState(0);
  const [ledgerCheck, setLedgerCheck] = useState<(LedgerVerify & { checked: number }) | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [justAccepted, setJustAccepted] = useState<{ id: string; at: number } | null>(null);
  const alertsRef = useRef<Alert[]>([]);
  const ledgerLenRef = useRef(-1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [playback, setPlaybackState] = useState<PlaybackSpeed | null>(null);
  const wsOpen = useRef(false);

  const fail = useCallback((e: unknown) => setError(e instanceof Error ? e.message : String(e)), []);

  // Кэш пропусков: id → Pass. Запрашиваем только новые id и пропуск груза из события WS;
  // одинаковые запросы в полёте объединяются.
  const passCache = useRef<Map<string, Pass>>(new Map());
  const passInflight = useRef<Map<string, Promise<Pass | null>>>(new Map());
  const passIds = useRef<string[]>([]);

  const publishPasses = useCallback(() => {
    const m = new Map<string, Pass>();
    for (const id of passIds.current) {
      const p = passCache.current.get(id);
      if (p) m.set(id, p);
    }
    setPasses(m);
  }, []);

  const fetchPass = useCallback((id: string): Promise<Pass | null> => {
    const running = passInflight.current.get(id);
    if (running) return running;
    const req = api
      .getPass(id)
      .then((p) => {
        passCache.current.set(id, p);
        return p;
      })
      .catch(() => null)
      .finally(() => passInflight.current.delete(id));
    passInflight.current.set(id, req);
    return req;
  }, []);

  const loadPasses = useCallback(
    async (list: Shipment[]) => {
      passIds.current = list.map((s) => s.pass_id).filter((id): id is string => !!id);
      await Promise.all(passIds.current.filter((id) => !passCache.current.has(id)).map(fetchPass));
      publishPasses();
    },
    [fetchPass, publishPasses],
  );

  /** Пропуск груза из события: запросить только его и только если такого id ещё не видели
   *  (у выпущенного пропуска статус меняется лишь вместе с выпуском нового, то есть с новым pass_id). */
  const refreshPass = useCallback(
    async (id: string) => {
      if (passCache.current.has(id)) return;
      await fetchPass(id);
      publishPasses();
    },
    [fetchPass, publishPasses],
  );

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
    const [sh, st, al, lg, sl] = await Promise.all([
      api.getShipments(),
      api.getStats(),
      api.getAlerts(),
      api.getLedger(),
      api.getSailings().catch(() => null),
    ]);
    setShipments(sh);
    if (sl) setSailings(sl);
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

  /** Демо вернулось к началу: забыть всё локальное и перезапросить состояние целиком. */
  const reload = useCallback(async () => {
    setScenario(null);
    setJustAccepted(null);
    setLedgerCheck(null);
    alertsRef.current = [];
    ledgerLenRef.current = -1;
    setResetSeq((n) => n + 1);
    setPlaybackState(api.getPlayback ? 0 : null);
    const [g, p] = await Promise.all([api.getGraph(), api.getScenarioPresets()]);
    setGraph(g);
    setPresets(p);
    await Promise.all([refreshLive(), refreshWeather()]);
  }, [refreshLive, refreshWeather]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [g, p] = await Promise.all([api.getGraph(), api.getScenarioPresets()]);
        if (cancelled) return;
        setGraph(g);
        setPresets(p);
        api.getPlayback?.().then((pb) => !cancelled && setPlaybackState(pb.speed), () => undefined);
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

  // События WS идут пачками (accept — десятки сообщений): обновляем список не чаще раза в секунду,
  // последнее событие пачки всегда даёт финальный перезапрос.
  const liveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const liveLast = useRef(0);
  const liveRef = useRef(refreshLive);
  useEffect(() => {
    liveRef.current = refreshLive;
  }, [refreshLive]);
  const scheduleLive = useCallback(() => {
    if (liveTimer.current) return;
    const wait = Math.max(0, liveLast.current + 1000 - Date.now());
    liveTimer.current = setTimeout(() => {
      liveTimer.current = null;
      liveLast.current = Date.now();
      liveRef.current().catch(fail);
    }, wait);
  }, [fail]);
  useEffect(() => () => {
    if (liveTimer.current) clearTimeout(liveTimer.current);
  }, []);

  const reloadRef = useRef(reload);
  useEffect(() => {
    reloadRef.current = reload;
  }, [reload]);

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
        const msg = JSON.parse(ev.data as string) as { type: string; payload?: { pass_id?: string | null } | null };
        if (msg.type === "demo.reset") {
          passCache.current.clear();
          reloadRef.current().catch(fail);
        } else if (msg.type === "weather.updated") refreshWeather().catch(fail);
        else if (msg.type === "playback.updated") {
          const sp = (msg.payload as { speed?: PlaybackSpeed } | null)?.speed;
          if (sp !== undefined) setPlaybackState(sp);
        }
        else {
          const pid = msg.type === "shipment.updated" ? msg.payload?.pass_id : null;
          if (pid) refreshPass(pid).catch(fail);
          scheduleLive();
        }
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, [refreshWeather, refreshPass, scheduleLive, fail]);

  useEffect(() => {
    const t = setInterval(() => {
      if (!wsOpen.current) refreshLive().catch(fail);
    }, POLL_MS);
    return () => clearInterval(t);
  }, [refreshLive, fail]);

  // Ускоренный просмотр: положение грузов меняется без событий — опрос /shipments раз в 2 с.
  useEffect(() => {
    if (!playback) return;
    const t = setInterval(() => {
      api.getShipments().then(setShipments, () => undefined);
    }, PLAYBACK_POLL_MS);
    return () => clearInterval(t);
  }, [playback]);

  const setPlayback = useCallback(
    async (speed: PlaybackSpeed) => {
      if (!api.setPlayback) return;
      try {
        const pb = await api.setPlayback(speed);
        setPlaybackState(pb.speed);
        setShipments(await api.getShipments());
      } catch (e) {
        fail(e);
      }
    },
    [fail],
  );

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
      passCache.current.clear();
      await reload();
    } catch (e) {
      fail(e);
    }
  }, [reload, fail]);

  const createShipment = useCallback(
    async (body: ShipmentCreate) => {
      const sh = await api.createShipment(body);
      await refreshLive().catch(fail);
      return sh;
    },
    [refreshLive, fail],
  );

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
    sailings,
    ledger,
    resetSeq,
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
    createShipment,
    playback,
    setPlayback,
  };
}
