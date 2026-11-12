import type {
  AcceptResult,
  Alert,
  Alternative,
  ApiErrorBody,
  AuthOut,
  AuthRole,
  AuthUser,
  Block,
  Graph,
  LedgerVerify,
  Pass,
  Scenario,
  ScenarioPreset,
  Shipment,
  Stats,
  Weather,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

/** Без NEXT_PUBLIC_API_URL сайт работает на моках из backend/data/mock (копия в src/mocks). */
export const USE_MOCKS = API_URL === "";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

export interface Api {
  getGraph(): Promise<Graph>;
  getShipments(): Promise<Shipment[]>;
  getWeather(): Promise<Weather>;
  getStats(): Promise<Stats>;
  getAlerts(status?: Alert["status"]): Promise<Alert[]>;
  getPass(id: string): Promise<Pass>;
  getScenarioPresets(): Promise<ScenarioPreset[]>;
  getAlternatives(shipmentId: string): Promise<Alternative[]>;
  acceptAlert(id: string, body: { via: "web" | "telegram"; option_id?: string }): Promise<AcceptResult>;
  rejectAlert(id: string): Promise<Alert>;
  getLedger(): Promise<Block[]>;
  verifyLedger(): Promise<LedgerVerify>;
  /** Только для демо. */
  tamperLedger(index: number): Promise<void>;
  createScenario(preset: string): Promise<{ scenario: Scenario; alert: Alert }>;
  /** Только моки: в контракте нет GET сценария, на бэкенде сценарий приходит из POST /scenarios. */
  getScenario?(id: string): Promise<Scenario | null>;
  resetDemo(): Promise<void>;
  register(body: { name: string; email: string; password: string; role: AuthRole }): Promise<AuthOut>;
  login(body: { email: string; password: string }): Promise<AuthOut>;
  me(token: string): Promise<AuthUser>;
  /** URL WebSocket `/ws` или null, если его нет (моки). */
  wsUrl(): string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      res.status,
      body?.error.code ?? "http_error",
      body?.error.message ?? res.statusText,
    );
  }
  return (await res.json()) as T;
}

const httpApi: Api = {
  getGraph: () => request("/graph"),
  getShipments: () => request("/shipments"),
  getWeather: () => request("/weather"),
  getStats: () => request("/stats"),
  getAlerts: (status) => request(`/alerts${status ? `?status=${status}` : ""}`),
  getPass: (id) => request(`/passes/${encodeURIComponent(id)}`),
  getScenarioPresets: () => request("/scenarios/presets"),
  createScenario: (preset) => request("/scenarios", { method: "POST", body: JSON.stringify({ preset }) }),
  getAlternatives: (id) => request(`/shipments/${encodeURIComponent(id)}/alternatives`),
  acceptAlert: (id, body) =>
    request(`/alerts/${encodeURIComponent(id)}/accept`, { method: "POST", body: JSON.stringify(body) }),
  rejectAlert: (id) => request(`/alerts/${encodeURIComponent(id)}/reject`, { method: "POST" }),
  getLedger: () => request("/ledger"),
  verifyLedger: () => request("/ledger/verify"),
  tamperLedger: async (index) => {
    await request("/ledger/tamper", { method: "POST", body: JSON.stringify({ index }) });
  },
  resetDemo: async () => {
    await request("/demo/reset", { method: "POST" });
  },
  register: (body) => request("/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: (body) => request("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  me: (token) =>
    request("/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    }),
  wsUrl: () => {
    const base = new URL(API_URL || window.location.origin);
    base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
    base.pathname = "/ws";
    base.search = "";
    base.hash = "";
    // Браузер не умеет слать заголовки в WebSocket: ключ идёт query-параметром.
    if (API_KEY) base.searchParams.set("api_key", API_KEY);
    return base.toString();
  },
};

// ---------- моки ----------

export type MockState = "base" | "storm" | "accepted" | "storm_full" | "accepted_full";

const MOCK_STATES: readonly MockState[] = ["base", "storm", "accepted", "storm_full", "accepted_full"];

/** Сценарии, которые умеют моки: остальные пресеты бэкенда в меню не показываем. */
const MOCK_PRESETS: Record<string, { title?: string; state: MockState; file: () => Promise<{ default: unknown }> }> = {
  storm_north: { state: "storm", file: () => import("@/mocks/scenario_storm_north.json") },
  storm_full: { title: "Шторм на всём море", state: "storm_full", file: () => import("@/mocks/scenario_storm_full.json") },
};

const mockFiles = {
  base: {
    shipments: () => import("@/mocks/shipments.json"),
    weather: () => import("@/mocks/weather.json"),
    stats: () => import("@/mocks/stats.json"),
    passes: () => import("@/mocks/passes.json"),
    alerts: () => import("@/mocks/alerts.json"),
    alternatives: () => import("@/mocks/alternatives.json"),
    ledger: () => import("@/mocks/ledger.json"),
  },
  storm: {
    shipments: () => import("@/mocks/shipments.storm.json"),
    weather: () => import("@/mocks/weather.storm.json"),
    stats: () => import("@/mocks/stats.storm.json"),
    passes: () => import("@/mocks/passes.storm.json"),
    alerts: () => import("@/mocks/alerts.storm.json"),
    alternatives: () => import("@/mocks/alternatives.storm.json"),
    ledger: () => import("@/mocks/ledger.storm.json"),
  },
  accepted: {
    shipments: () => import("@/mocks/shipments.accepted.json"),
    weather: () => import("@/mocks/weather.storm.json"),
    stats: () => import("@/mocks/stats.accepted.json"),
    passes: () => import("@/mocks/passes.accepted.json"),
    alerts: () => import("@/mocks/alerts.accepted.json"),
    alternatives: () => import("@/mocks/alternatives.accepted.json"),
    ledger: () => import("@/mocks/ledger.accepted.json"),
  },
  // Шторм на всём море: груз остаётся в тех же состояниях до решения, потом идёт по западной ветке.
  storm_full: {
    shipments: () => import("@/mocks/shipments.storm.json"),
    weather: () => import("@/mocks/weather.storm_full.json"),
    stats: () => import("@/mocks/stats.storm.json"),
    passes: () => import("@/mocks/passes.storm.json"),
    alerts: () => import("@/mocks/alerts.storm_full.json"),
    alternatives: () => import("@/mocks/alternatives.storm_full.json"),
    ledger: () => import("@/mocks/ledger.storm.json"),
  },
  accepted_full: {
    shipments: () => import("@/mocks/shipments.accepted_full.json"),
    weather: () => import("@/mocks/weather.storm_full.json"),
    stats: () => import("@/mocks/stats.accepted_full.json"),
    passes: () => import("@/mocks/passes.accepted_full.json"),
    alerts: () => import("@/mocks/alerts.accepted_full.json"),
    alternatives: () => import("@/mocks/alternatives.accepted_full.json"),
    ledger: () => import("@/mocks/ledger.accepted_full.json"),
  },
} as const;

/** Что делает «Принять» в каждом состоянии штормового сценария. */
const ACCEPT_FILE = {
  storm: () => import("@/mocks/accept.json"),
  storm_full: () => import("@/mocks/accept_full.json"),
} as const;

function initialMockState(): MockState {
  if (typeof window !== "undefined") {
    const s = new URLSearchParams(window.location.search).get("state");
    if (MOCK_STATES.includes(s as MockState)) return s as MockState;
  }
  return "base";
}

let mockState: MockState | null = null;
const state = () => (mockState ??= initialMockState());
const isStorm = (s: MockState): s is "storm" | "storm_full" => s === "storm" || s === "storm_full";
const isAccepted = (s: MockState) => s === "accepted" || s === "accepted_full";
const isFull = (s: MockState) => s === "storm_full" || s === "accepted_full";
/** Алерт отклонён («Ждать рейс Б»): в моках это только флаг поверх состояния storm. */
let mockRejected = false;
/** Подделанная запись реестра (индекс блока) — для проверки целостности в моках. */
let mockTampered: number | null = null;

type MockAccount = AuthUser & { password: string };
const mockAccounts: MockAccount[] = [
  { id: "u-logist", name: "Демо логист", email: "logist@demo.ru", role: "logist", password: "demo123" },
  { id: "u-expeditor", name: "Демо экспедитор", email: "expeditor@demo.ru", role: "expeditor", password: "demo123" },
];

async function load<T>(kind: keyof (typeof mockFiles)["base"]): Promise<T> {
  const mod = await mockFiles[state()][kind]();
  return structuredClone(mod.default) as T;
}

const mockApi: Api = {
  getGraph: async () => structuredClone((await import("@/mocks/graph.json")).default) as Graph,
  getShipments: () => load("shipments"),
  getWeather: () => load("weather"),
  getStats: () => load("stats"),
  getAlerts: async (status) => {
    let alerts = await load<Alert[]>("alerts");
    if (mockRejected && isStorm(state())) alerts = alerts.map((a) => ({ ...a, status: "rejected" as const }));
    return status ? alerts.filter((a) => a.status === status) : alerts;
  },
  getPass: async (id) => {
    const pass = (await load<Pass[]>("passes")).find((p) => p.id === id);
    if (!pass) throw new ApiError(404, "not_found", "Пропуск не найден");
    return pass;
  },
  getScenarioPresets: async () => {
    const all = (await import("@/mocks/scenario_presets.json")).default as ScenarioPreset[];
    return all
      .filter((p) => p.key in MOCK_PRESETS)
      .map((p) => ({ ...p, title: MOCK_PRESETS[p.key].title ?? p.title }));
  },
  createScenario: async (preset) => {
    const def = MOCK_PRESETS[preset];
    if (!def) throw new ApiError(501, "not_mocked", "В моках есть только штормовые сценарии");
    mockState = def.state;
    mockRejected = false;
    return structuredClone((await def.file()).default) as { scenario: Scenario; alert: Alert };
  },
  getScenario: async (id) => {
    for (const def of Object.values(MOCK_PRESETS)) {
      const { scenario } = (await def.file()).default as { scenario: Scenario };
      if (scenario.id === id) return structuredClone(scenario);
    }
    return null;
  },
  getAlternatives: async (id) => {
    const all = await load<Record<string, Alternative[]>>("alternatives");
    return all[id] ?? [];
  },
  acceptAlert: async (id, body) => {
    if (body.option_id === "wait") {
      throw new ApiError(422, "use_reject", "Вариант «ждать» оформляется через «Отклонить»");
    }
    const full = isFull(state());
    const accepted = structuredClone(
      (await ACCEPT_FILE[full ? "storm_full" : "storm"]()).default,
    ) as unknown as AcceptResult;
    if (accepted.alert.id !== id) throw new ApiError(404, "not_found", "Алерт не найден");
    if (body.option_id && !accepted.alert.options.some((o) => o.id === body.option_id)) {
      throw new ApiError(404, "option_not_found", "Такого варианта нет");
    }
    accepted.decision.accepted_via = body.via;
    accepted.alert.accepted_via = body.via;
    if (isAccepted(state())) return { ...accepted, already_accepted: true };
    if (!isStorm(state()) || mockRejected) throw new ApiError(409, "superseded", "Предложение устарело");
    mockState = full ? "accepted_full" : "accepted";
    return { ...accepted, already_accepted: false };
  },
  rejectAlert: async (id) => {
    const alerts = await load<Alert[]>("alerts");
    const alert = alerts.find((a) => a.id === id);
    if (!alert) throw new ApiError(404, "not_found", "Алерт не найден");
    if (isStorm(state())) mockRejected = true;
    return { ...alert, status: "rejected" };
  },
  getLedger: () => load("ledger"),
  verifyLedger: async () => {
    const blocks = await load<Block[]>("ledger");
    return mockTampered !== null && blocks.some((b) => b.index === mockTampered)
      ? { valid: false, broken_at: mockTampered }
      : { valid: true, broken_at: null };
  },
  tamperLedger: async (index) => {
    mockTampered = index;
  },
  resetDemo: async () => {
    mockState = "base";
    mockRejected = false;
    mockTampered = null;
  },

  register: async (body) => {
    const email = body.email.trim().toLowerCase();
    if (!email.includes("@")) throw new ApiError(422, "invalid_email", "Некорректный email");
    if (body.password.length < 6) throw new ApiError(422, "weak_password", "Пароль короче 6 символов");
    if (mockAccounts.some((a) => a.email === email)) throw new ApiError(409, "email_taken", "Email уже занят");
    const user: AuthUser = { id: `u-${mockAccounts.length + 1}`, name: body.name.trim(), email, role: body.role };
    mockAccounts.push({ ...user, password: body.password });
    return { token: `mock-${user.id}`, user };
  },
  login: async (body) => {
    const email = body.email.trim().toLowerCase();
    const acc = mockAccounts.find((a) => a.email === email && a.password === body.password);
    if (!acc) throw new ApiError(401, "invalid_credentials", "Неверный email или пароль");
    const user = { id: acc.id, name: acc.name, email: acc.email, role: acc.role };
    return { token: `mock-${user.id}`, user };
  },
  me: async (token) => {
    const id = token.startsWith("mock-") ? token.slice(5) : "";
    const acc = mockAccounts.find((a) => a.id === id);
    if (!acc) throw new ApiError(401, "invalid_token", "Сессия недействительна");
    return { id: acc.id, name: acc.name, email: acc.email, role: acc.role };
  },
  wsUrl: () => null,
};

export const api: Api = USE_MOCKS ? mockApi : httpApi;
