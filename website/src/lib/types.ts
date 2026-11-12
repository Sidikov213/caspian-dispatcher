// Модель данных — CLAUDE.md, раздел 4. Имена полей совпадают с контрактом API.

export type Mode = "rail" | "sea" | "road";
export type Branch = "west" | "transcaspian" | "east";
export type NodeType = "port" | "station" | "border" | "city";

export interface GraphNode {
  id: string;
  name: string;
  country: string;
  type: NodeType;
  lat: number;
  lon: number;
  congestion: number;
  /** Проверенные факты о порте; у остальных узлов нет. */
  facts?: string[] | null;
  /** Ссылки на источники фактов. */
  sources?: string[] | null;
}

export interface Edge {
  id: string;
  from: string;
  to: string;
  mode: Mode;
  branch: Branch;
  distance_km: number;
  base_hours: number;
  cost_rub_per_t: number;
  co2_g_per_tkm: number;
  /** Необязательно: промежуточные точки [lat, lon] для карты (без самих узлов). */
  path?: [number, number][] | null;
}

export interface Graph {
  nodes: GraphNode[];
  edges: Edge[];
}

export type LegStatus = "done" | "active" | "pending" | "blocked";

export interface Leg {
  index: number;
  edge_id: string;
  from: string;
  to: string;
  mode: Mode;
  sailing_id: string | null;
  planned_start: string;
  planned_end: string;
  predicted_delay_h: number;
  status: LegStatus;
}

export interface Route {
  id: string;
  legs: Leg[];
  total_hours: number;
  total_cost_rub: number;
  total_co2_kg: number;
  branch: Branch;
}

export type RiskLevel = "low" | "medium" | "high";

export interface RiskFactor {
  name: string;
  label: string;
  impact_hours: number;
}

export interface ProbabilityDriver {
  name: string;
  label: string;
  impact_pp: number;
}

export interface Risk {
  miss_probability: number;
  level: RiskLevel;
  departure_shift_h: number;
  arrival_delay_h: number;
  factors: RiskFactor[];
  /** Три главных признака CatBoost (SHAP). У формулы и сухопутных маршрутов — null. Сайт их не рисует. */
  probability_drivers?: ProbabilityDriver[] | null;
}

export type Stage = "planned" | "in_transit" | "delivered";
export type DisplayStatus = "planned" | "in_transit" | "at_risk" | "rerouted" | "delivered";
export type PassState = "none" | "active" | "reissue_pending";

export interface ShipmentPosition {
  lat: number;
  lon: number;
  edge_id: string;
  mode: Mode;
  /** Доля пройденного пути ребра; в ожидании — 0. */
  progress: number;
  heading_deg: number;
  from_node: string;
  to_node: string;
  eta_next_node: string;
  waiting: boolean;
  waiting_reason?: "sailing" | "border" | "transfer" | "blocked" | null;
  waiting_label?: string | null;
}

export interface Shipment {
  id: string;
  title: string;
  cargo_type: string;
  weight_t: number;
  owner_tg_id: number | null;
  origin: string;
  destination: string;
  stage: Stage;
  risk_level: RiskLevel;
  rerouted: boolean;
  display_status: DisplayStatus;
  /** Где груз на карте; считает сервер. null — ещё не выехал или доставлен. */
  position: ShipmentPosition | null;
  current_leg: number | null;
  route: Route;
  planned_eta: string;
  eta: string;
  risk: Risk | null;
  pass_id: string | null;
  pass_state: PassState;
}

export interface Pass {
  id: string;
  shipment_id: string;
  checkpoint_node: string;
  token: string;
  doc_hash: string;
  block_hash: string;
  valid_until: string;
  status: "active" | "reissued" | "revoked";
}

export interface WeatherPoint {
  node_id: string;
  wave_height_m: number;
  wind_ms: number;
  forecast: { ts: string; wave_height_m: number }[];
}

export interface Weather {
  updated_at: string;
  stale: boolean;
  source: "open-meteo" | "cache";
  points: WeatherPoint[];
}

export interface Stats {
  saved_hours: number;
  saved_rub: number;
  co2_saved_kg: number;
  /** На сколько % ниже CO₂ к исходным маршрутам. 6.9 → показывать «−6,9%». Считает бэкенд. */
  co2_saved_pct: number;
  decisions: number;
  shipments_total: number;
  at_risk: number;
}

export type Hazard = "ice" | "storm" | "congestion" | "customs";

export interface Scenario {
  id: string;
  type: Hazard;
  /** Тип угрозы; у старых сценариев может не быть — тогда по type. */
  hazard?: Hazard | null;
  /** У шторма — «Стресс-тест: …». */
  note?: string | null;
  title: string;
  blocked_edges: string[];
  affected_nodes: string[];
  start: string;
  end: string;
  /** Через сколько часов от sim_now начинается угроза. Не считать от created_at. */
  starts_in_h: number;
  params: { wave_height_m?: number; wind_ms?: number };
  /** Необязательно: зона угрозы для карты, полигон [lat, lon]. Сайт её не угадывает. */
  zone?: [number, number][] | null;
}

export interface ScenarioPreset {
  key: string;
  title: string;
  hazard?: Hazard | null;
  /** Главный сценарий демо (ice_north). */
  main?: boolean;
  note?: string | null;
}

export interface AlertItem {
  shipment_id: string;
  action: "reroute" | "wait";
  from_route: Route | null;
  to_route: Route | null;
  sailing_id: string | null;
  delay_vs_plan_h: number;
  saved_hours: number;
  saved_rub: number;
  co2_delta_kg: number;
}

export interface AlertOption {
  id: string;
  title: string;
  route: Route | null;
  delay_vs_plan_h: number;
  saved_hours: number;
  saved_rub: number;
  co2_delta_kg: number;
  recommended: boolean;
}

export interface Alert {
  id: string;
  scenario_id: string;
  created_at: string;
  /** Через сколько часов от sim_now начинается угроза — копия из сценария. */
  starts_in_h: number;
  severity: string;
  title: string;
  text: string;
  items: AlertItem[];
  totals: { saved_hours: number; saved_rub: number; co2_delta_kg: number; co2_delta_pct: number };
  do_nothing: { delay_hours: number; loss_rub: number };
  port_load: { node_id: string; before: number; after: number } | null;
  options: AlertOption[];
  status: "new" | "accepted" | "rejected" | "superseded";
  accepted_at: string | null;
  accepted_via: "web" | "telegram" | null;
  /** Кто принял; нет — показываем «через сайт / через Telegram». */
  accepted_by?: AcceptedBy | null;
  /** Откуда угроза: наблюдатель нашёл в прогнозе или сценарий демо. */
  source?: "forecast" | "scenario" | null;
  /** Почему алерт закрыт: «угроза снята», «заменён алертом …», «по этим грузам решение уже принято». */
  status_note?: string | null;
  hazard?: Hazard | null;
  /** Компактная карточка: готовые строки с сервера, рисуем как есть. */
  card?: AlertCard | null;
}

export interface AlertCard {
  kind: Hazard;
  headline: string;
  subtitle: string;
  period: string | null;
  metrics: { key: string; label: string; value: string }[];
  route: { sailing_label: string; from: string; to: string; departure: string } | null;
  impact: { shipments: number; weight_t: number; max_risk_pct: number };
  note: string | null;
  decision: {
    status: "accepted" | "rejected";
    title: string;
    detail: string;
    via: "web" | "telegram" | null;
    via_label: string | null;
    accepted_by_name: string | null;
  } | null;
}

export interface AcceptedBy {
  name: string;
  role: AuthRole;
}

export interface ApiErrorBody {
  error: { code: string; message: string; fields?: string[] };
}

export interface Alternative {
  route: Route;
  risk: Risk;
  delta: { hours: number; rub: number; co2_kg: number };
  recommended: boolean;
}

export interface DecisionItem {
  shipment_id: string;
  saved_hours: number;
  saved_rub: number;
  co2_delta_kg: number;
  sailing_id: string | null;
}

export interface Decision {
  id: string;
  alert_id: string;
  ts: string;
  accepted_via: "web" | "telegram";
  accepted_by?: AcceptedBy | null;
  items: DecisionItem[];
}

export interface AcceptResult {
  alert: Alert;
  shipments: Shipment[];
  blocks: Block[];
  decision: Decision;
  already_accepted?: boolean;
}

export interface Block {
  index: number;
  ts: string;
  event: "issued" | "reissued" | "verified";
  shipment_id: string;
  checkpoint_node: string;
  doc_hash: string;
  prev_hash: string;
  hash: string;
}

export interface LedgerVerify {
  valid: boolean;
  broken_at: number | null;
}

/** POST /api/passes/verify */
export interface PassVerify {
  valid: boolean;
  shipment_id: string | null;
  checkpoint_node: string | null;
  reason: string | null;
}

/** Аккаунты — POST /api/auth/register|login, GET /api/auth/me. */
export type AuthRole = "logist" | "expeditor";

export type Permission = "run_scenario" | "reset_demo" | "decide_alert";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: AuthRole;
  /** Права из /api/auth/me. Логист: run_scenario, reset_demo, decide_alert; экспедитор — пусто. */
  permissions?: Permission[];
}

export interface AuthOut {
  token: string;
  user: AuthUser;
}

/** GET /api/sailings */
export interface Sailing {
  id: string;
  from: string;
  to: string;
  departure: string;
  cutoff: string;
  duration_h: number;
  capacity_t: number;
  booked_t: number;
  status: "scheduled" | "cancelled" | "departed";
  cancel_reason: string | null;
}

/** POST /api/shipments */
export interface ShipmentCreate {
  title: string;
  cargo_type: string;
  weight_t: number;
  origin: string;
  destination: string;
}

/** GET /api/model */
export interface ModelInfo {
  summary: string;
  active: "catboost" | "formula";
  requested: string;
  fallback_reason: string | null;
  synthetic: boolean;
  note: string;
  used_at_runtime?: Record<string, string> | null;
  trained_at: string | null;
  seed: number | null;
  classifier: { auc: number; brier: number; n_train: number; n_test: number } | null;
  regressor: { mae_h: number; n_train: number; n_test: number } | null;
  feature_importance: { name: string; label: string; importance: number }[];
}

/** GET /api/data-sources */
export type DataSourceType = "real" | "modeled" | "synthetic";

export interface DataSource {
  id: string;
  title: string;
  provides: string;
  type: DataSourceType;
  url: string | null;
  urls?: string[] | null;
  updated_at: string | null;
  note: string | null;
}

export interface BacktestPort {
  grid_point: [number, number];
  hours_total: number;
  hours_no_data: number;
  windows: number;
  closed_hours: number;
  longest_window_h: number;
  max_wave_m: number | null;
  hours_over: Record<string, number>;
  by_month: Record<string, { closed_h: number; no_data_h: number; max_wave_m: number }>;
}

export interface Backtest {
  title: string;
  note: string;
  source: string;
  fetched_at: string;
  period: { start: string; end: string };
  wave_limit_m: number;
  schedule: Record<string, number | string>;
  ports: Record<string, BacktestPort>;
  sailings: {
    departures: number;
    closed: number;
    saved_by_makhachkala: number;
    no_data: number;
    no_data_makhachkala_open: number;
  };
  chart: string;
}

export interface DataSources {
  sources: DataSource[];
  corridor_facts: { text: string; source: string }[];
  backtest: Backtest | null;
  /** Почему главный сценарий — лёд: факты, честная пометка об источнике, вывод ретроспективы. */
  ice?: { title: string; facts: { text: string; source: string | null }[]; note: string; conclusion: string | null } | null;
}
