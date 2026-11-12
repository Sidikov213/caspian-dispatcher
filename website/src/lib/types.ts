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
  position: { lat: number; lon: number } | null;
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

export interface Scenario {
  id: string;
  type: "storm" | "congestion" | "customs";
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
}

export interface ApiErrorBody {
  error: { code: string; message: string };
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

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: AuthRole;
}

export interface AuthOut {
  token: string;
  user: AuthUser;
}
