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
  DataSources,
  ModelInfo,
  Pass,
  PassVerify,
  Scenario,
  Sailing,
  ScenarioPreset,
  Shipment,
  ShipmentCreate,
  Stats,
  Weather,
} from "./types";
import { mockApi } from "./mockApi";
import { getToken } from "./session";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

/**
 * Без NEXT_PUBLIC_API_URL сайт работает на моках из backend/data/mock (копия в src/mocks).
 * Условие написано прямо по process.env: в сборке для сервера Next подставляет адрес, ветка моков
 * становится мёртвым кодом.
 */
export const USE_MOCKS = !process.env.NEXT_PUBLIC_API_URL;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields: string[] = [],
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
  getSailings(): Promise<Sailing[]>;
  /** Все пропуска, включая переоформленные; новые сверху. */
  getPasses(shipmentId?: string): Promise<Pass[]>;
  getModel(): Promise<ModelInfo>;
  getDataSources(): Promise<DataSources>;
  createShipment(body: ShipmentCreate): Promise<Shipment>;
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
  /** Сценарий по id: моки — из файлов, бэкенд — из GET /scenarios (активные сценарии с зоной). */
  getScenario?(id: string): Promise<Scenario | null>;
  /** Проверка пропуска: POST /passes/verify. */
  verifyPass(token: string): Promise<PassVerify>;
  resetDemo(): Promise<void>;
  register(body: { name: string; email: string; password: string; role: AuthRole }): Promise<AuthOut>;
  login(body: { email: string; password: string }): Promise<AuthOut>;
  me(token: string): Promise<AuthUser>;
  /** URL WebSocket `/ws` или null, если его нет (моки). */
  wsUrl(): string | null;
}

/** После входа все запросы идут с X-API-Key и Authorization: Bearer — сервер проверяет права роли. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_URL}/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
      body?.error.fields ?? [],
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
  getSailings: () => request("/sailings"),
  getPasses: (id) => request(`/passes${id ? `?shipment_id=${encodeURIComponent(id)}` : ""}`),
  getModel: () => request("/model"),
  getDataSources: () => request("/data-sources"),
  createShipment: (body) => request("/shipments", { method: "POST", body: JSON.stringify(body) }),
  getPass: (id) => request(`/passes/${encodeURIComponent(id)}`),
  getScenarioPresets: () => request("/scenarios/presets"),
  createScenario: (preset) => request("/scenarios", { method: "POST", body: JSON.stringify({ preset }) }),
  getScenario: async (id) => (await request<Scenario[]>("/scenarios")).find((s) => s.id === id) ?? null,
  verifyPass: (token) => request("/passes/verify", { method: "POST", body: JSON.stringify({ token }) }),
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

export const api: Api = USE_MOCKS && mockApi ? mockApi : httpApi;
