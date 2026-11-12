"""Pydantic-модели. Строго по разделу 4 CLAUDE.md; запросы и ответы — по разделу 5.

Поле `from` в Python зарезервировано, поэтому в коде оно `from_`, а в JSON — `from`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


# ---------- Справочники ----------

NodeType = Literal["port", "station", "border", "city"]
Mode = Literal["rail", "sea", "road"]
Branch = Literal["west", "transcaspian", "east"]
Stage = Literal["planned", "in_transit", "delivered"]
RiskLevel = Literal["low", "medium", "high"]
DisplayStatus = Literal["planned", "in_transit", "at_risk", "rerouted", "delivered"]
PassState = Literal["none", "active", "reissue_pending"]
LegStatus = Literal["done", "active", "pending", "blocked"]
SailingStatus = Literal["scheduled", "cancelled", "departed"]
Via = Literal["web", "telegram"]
AlertStatus = Literal["new", "accepted", "rejected", "superseded"]
AlertAction = Literal["reroute", "wait"]
ScenarioType = Literal["storm", "congestion", "customs"]
ScenarioPreset = Literal["storm_north", "storm_full", "congestion_astrakhan"]
DocType = Literal["invoice", "cmr", "packing_list"]
DocStatus = Literal["draft", "confirmed"]
PassStatus = Literal["active", "reissued", "revoked"]
BlockEvent = Literal["issued", "reissued", "verified"]


def display_status_of(stage: str, risk_level: str, rerouted: bool) -> str:
    """Приоритет: delivered → at_risk (risk_level=high) → rerouted → in_transit → planned."""
    if stage == "delivered":
        return "delivered"
    if risk_level == "high":
        return "at_risk"
    if rerouted:
        return "rerouted"
    return "in_transit" if stage == "in_transit" else "planned"


# ---------- Сущности (раздел 4) ----------

class Node(Model):
    id: str
    name: str
    country: str
    type: NodeType
    lat: float
    lon: float
    congestion: float = Field(ge=0, le=1)


class Edge(Model):
    id: str
    from_: str = Field(alias="from")
    to: str
    mode: Mode
    branch: Branch
    distance_km: float
    base_hours: float
    cost_rub_per_t: float
    co2_g_per_tkm: float


class Position(Model):
    lat: float
    lon: float


class Leg(Model):
    index: int
    edge_id: str
    from_: str = Field(alias="from")
    to: str
    mode: Mode
    sailing_id: str | None = None
    planned_start: datetime
    planned_end: datetime
    predicted_delay_h: float = 0
    status: LegStatus


class Route(Model):
    id: str
    legs: list[Leg]
    total_hours: float
    total_cost_rub: float
    total_co2_kg: float
    branch: Branch


class RiskFactor(Model):
    name: str
    label: str
    impact_hours: float


class Risk(Model):
    miss_probability: float = Field(ge=0, le=1)
    level: RiskLevel
    departure_shift_h: float = Field(description="На сколько позже планового рейса возможно отправление")
    arrival_delay_h: float = Field(description="Задержка прибытия, если рейс отменят")
    factors: list[RiskFactor]


class Shipment(Model):
    id: str
    title: str
    cargo_type: str
    weight_t: float
    owner_tg_id: int | None = None
    origin: str
    destination: str
    stage: Stage
    risk_level: RiskLevel
    rerouted: bool
    display_status: DisplayStatus = Field(description="Считает бэкенд, клиенты сами не выводят")
    position: Position
    current_leg: int | None = None
    route: Route
    planned_eta: datetime
    eta: datetime
    risk: Risk
    pass_id: str | None = None
    pass_state: PassState


class Sailing(Model):
    id: str
    from_: str = Field(alias="from")
    to: str
    departure: datetime
    cutoff: datetime
    duration_h: float
    capacity_t: float
    booked_t: float
    status: SailingStatus
    cancel_reason: str | None = None


class DecisionItem(Model):
    shipment_id: str
    saved_hours: float
    saved_rub: float
    co2_delta_kg: float
    sailing_id: str | None = None


class Decision(Model):
    id: str
    alert_id: str
    ts: datetime
    accepted_via: Via
    items: list[DecisionItem]


class ScenarioParams(Model):
    wave_height_m: float | None = None
    wind_ms: float | None = None


class Scenario(Model):
    id: str
    type: ScenarioType
    title: str
    blocked_edges: list[str]
    affected_nodes: list[str]
    start: datetime
    end: datetime
    params: ScenarioParams


class AlertItem(Model):
    shipment_id: str
    action: AlertAction
    from_route: Route
    to_route: Route | None = None
    sailing_id: str | None = None
    delay_vs_plan_h: float
    saved_hours: float
    saved_rub: float
    co2_delta_kg: float


class AlertTotals(Model):
    saved_hours: float
    saved_rub: float
    co2_delta_kg: float
    co2_delta_pct: float


class DoNothing(Model):
    delay_hours: float
    loss_rub: float


class PortLoad(Model):
    node_id: str
    before: float
    after: float


class AlertOption(Model):
    """Вариант решения по алерту. id: тег маршрута (mkh, west…), best — лучший для каждого груза,
    wait — ждать следующего рейса (принимается через /reject). Числа — сумма по грузам алерта."""
    id: str
    title: str
    route: Route | None = None
    delay_vs_plan_h: float
    saved_hours: float
    saved_rub: float
    co2_delta_kg: float
    recommended: bool


class Alert(Model):
    """Все деньги и часы до наступления события — расчётные."""
    id: str
    scenario_id: str
    created_at: datetime
    severity: str
    title: str
    text: str
    items: list[AlertItem]
    totals: AlertTotals
    do_nothing: DoNothing
    port_load: PortLoad | None = None
    options: list[AlertOption] = Field(default_factory=list, description="До трёх вариантов, рекомендованный первый")
    status: AlertStatus
    accepted_at: datetime | None = None
    accepted_via: Via | None = None


class DocumentFields(Model):
    seller: str | None = None
    buyer: str | None = None
    goods: str | None = None
    hs_code: str | None = None
    weight_kg: float | None = None
    value: float | None = None
    currency: str | None = None
    origin_country: str | None = None


class DocumentCheck(Model):
    name: str
    ok: bool
    note: str | None = None


class Document(Model):
    id: str
    shipment_id: str
    type: DocType
    source_lang: str
    image_url: str | None = None
    fields: DocumentFields
    checks: list[DocumentCheck]
    status: DocStatus
    hash: str | None = None


class Pass(Model):
    id: str
    shipment_id: str
    checkpoint_node: str
    token: str = Field(description="JWT HS256, внутри doc_hash и block_hash")
    doc_hash: str
    block_hash: str
    valid_until: datetime
    status: PassStatus


class Block(Model):
    index: int
    ts: datetime
    event: BlockEvent
    shipment_id: str
    checkpoint_node: str
    doc_hash: str
    prev_hash: str
    hash: str


# ---------- Запросы ----------

class ShipmentCreate(Model):
    title: str
    cargo_type: str
    weight_t: float
    origin: str
    destination: str


class RerouteIn(Model):
    route_id: str


class ScenarioIn(Model):
    preset: ScenarioPreset


class AcceptIn(Model):
    via: Via
    option_id: str | None = Field(None, description="id из Alert.options; без него — рекомендованный")


class DocumentConfirmIn(Model):
    fields: DocumentFields


class PassVerifyIn(Model):
    token: str


class TamperIn(Model):
    index: int


class UserLinkIn(Model):
    telegram_id: int
    name: str


# ---------- Ответы ----------

class GraphOut(Model):
    nodes: list[Node]
    edges: list[Edge]


class Delta(Model):
    hours: float = Field(description="Задержка прибытия к плану по прогнозу, ч")
    rub: float = Field(description="Доплата за перевозку к плановому маршруту, ₽")
    co2_kg: float = Field(description="Разница CO₂ к плановому маршруту, кг")


class AlternativeOut(Model):
    route: Route
    risk: Risk
    delta: Delta
    recommended: bool


class ForecastPoint(Model):
    ts: datetime
    wave_height_m: float


class WeatherPoint(Model):
    node_id: str
    wave_height_m: float
    wind_ms: float
    forecast: list[ForecastPoint]


class WeatherOut(Model):
    updated_at: datetime
    stale: bool
    source: Literal["open-meteo", "cache"]
    points: list[WeatherPoint]


class PresetOut(Model):
    key: ScenarioPreset
    title: str


class ScenarioCreateOut(Model):
    scenario: Scenario
    alert: Alert


class AcceptOut(Model):
    alert: Alert
    shipments: list[Shipment]
    blocks: list[Block]
    decision: Decision
    already_accepted: bool = False


class PassRetryOut(Model):
    shipment: Shipment
    pass_: Pass = Field(alias="pass")


class DocumentConfirmOut(Model):
    document: Document
    pass_: Pass = Field(alias="pass")
    block: Block


class PassVerifyOut(Model):
    valid: bool
    shipment_id: str | None = None
    checkpoint_node: str | None = None
    reason: str | None = None


class LedgerVerifyOut(Model):
    valid: bool
    broken_at: int | None = None


class StatsOut(Model):
    saved_hours: float = Field(description="Груз-часы, сумма по Decision")
    saved_rub: float
    co2_saved_kg: float
    decisions: int
    shipments_total: int
    at_risk: int


class OkOut(Model):
    ok: bool = True


class ErrorBody(Model):
    code: str
    message: str


class ErrorOut(Model):
    error: ErrorBody


# ---------------- GET /api/demo/check (только демо) ----------------

class DemoCheckItem(Model):
    name: str
    label: str
    expected: float | str
    actual: float | str | None
    ok: bool


class DemoCheckWeather(Model):
    source: str
    stale: bool
    updated_at: str


class DemoCheckOut(Model):
    ok: bool
    sim_now: str
    weather: DemoCheckWeather
    checks: list[DemoCheckItem]
    problems: list[str]

