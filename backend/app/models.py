"""Pydantic-модели. Строго по разделу 4 CLAUDE.md; запросы и ответы — по разделу 5.

Поле `from` в Python зарезервировано, поэтому в коде оно `from_`, а в JSON — `from`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


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
    path: list[list[float]] | None = Field(
        None, description="Необязательно: промежуточные точки [lat, lon] для карты (без самих узлов). "
                          "Только рисование: море по акватории, суша вдоль трасс")


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


class ProbabilityDriver(Model):
    name: str = Field(description="Признак модели, напр. wave_height_m")
    label: str = Field(description="Подпись, напр. «Волна 3,4 м»")
    impact_pp: float = Field(description="Вклад в вероятность срыва, п. п. (SHAP классификатора)")


class Risk(Model):
    miss_probability: float = Field(ge=0, le=1)
    level: RiskLevel
    departure_shift_h: float = Field(description="На сколько позже планового рейса возможно отправление")
    arrival_delay_h: float = Field(description="Задержка прибытия, если рейс отменят")
    factors: list[RiskFactor]
    probability_drivers: list[ProbabilityDriver] | None = Field(
        None, description="Необязательно: три главных признака по SHAP классификатора CatBoost "
                          "с вкладом в вероятность в п. п. У формулы и сухопутных маршрутов — null")


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
    manual: bool = Field(False, description="Груз создан вручную (POST /shipments); при demo/reset исчезает")


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


class AcceptedBy(Model):
    """Кто принял решение. Есть, если запрос пришёл с Bearer-токеном входа сайта, из мини-приложения
    или из бота (имя пользователя Telegram). Без него клиенты пишут «через сайт / через Telegram»."""
    name: str
    role: Literal["logist", "expeditor"]


class Decision(Model):
    id: str
    alert_id: str
    ts: datetime
    accepted_via: Via
    accepted_by: AcceptedBy | None = None
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
    starts_in_h: float = Field(description="Через сколько часов от sim_now начинается угроза (storm_north — 36)")
    params: ScenarioParams
    zone: list[list[float]] | None = Field(
        None, description="Необязательно: зона угрозы для карты — полигон из точек [lat, lon]")


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
    starts_in_h: float = Field(description="Через сколько часов от sim_now начинается угроза — из сценария")
    severity: str
    title: str
    text: str
    items: list[AlertItem]
    totals: AlertTotals
    do_nothing: DoNothing
    port_load: PortLoad | None = None
    options: list[AlertOption] = Field(default_factory=list, description="До трёх вариантов, рекомендованный первый")
    status: AlertStatus
    source: Literal["forecast", "scenario"] | None = Field(
        None, description="Откуда угроза: forecast — наблюдатель нашёл в прогнозе, scenario — сценарий демо")
    status_note: str | None = Field(None, description="Почему алерт закрыт: «угроза снята», «прогноз изменился…»")
    accepted_at: datetime | None = None
    accepted_via: Via | None = None
    accepted_by: AcceptedBy | None = None


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

CargoType = Literal["grain", "metal", "equipment", "textile", "fertilizer", "explosives"]
NodeId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Id = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
MAX_WEIGHT_T = 5000


class ShipmentCreate(Model):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    cargo_type: CargoType
    weight_t: float = Field(gt=0, le=MAX_WEIGHT_T, allow_inf_nan=False, description="Больше 0, не больше 5000 т")
    origin: NodeId
    destination: NodeId

    @model_validator(mode="after")
    def _different_points(self):
        if self.origin == self.destination:
            raise ValueError("пункт отправления и назначения совпадают")
        return self


class RerouteIn(Model):
    route_id: Id


class ScenarioIn(Model):
    preset: ScenarioPreset


class AcceptIn(Model):
    via: Via
    option_id: Annotated[str, StringConstraints(min_length=1, max_length=32)] | None = Field(None, description="id из Alert.options; без него — рекомендованный")


class DocumentConfirmIn(Model):
    fields: DocumentFields


class PassVerifyIn(Model):
    token: Annotated[str, StringConstraints(min_length=1, max_length=4096)]


class TamperIn(Model):
    index: int = Field(ge=0)


class UserLinkIn(Model):
    telegram_id: int = Field(gt=0)
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


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
    co2_saved_pct: float = Field(description="На сколько % ниже CO₂ по принятым решениям к исходным маршрутам "
                                             "этих грузов: 6.9 → показывать «−6,9% CO₂»")
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



# ---------- Модель предиктора (GET /api/model) ----------

class ModelUsage(Model):
    miss_probability: str = Field(description="Чем считается вероятность срыва стыковки")
    departure_shift_and_delays: str = Field(description="Чем считаются сдвиг отправления, задержки, деньги, CO₂")
    shift_regressor: str = Field(description="Роль регрессора сдвига (только проверка)")


class ClassifierMetrics(Model):
    auc: float
    brier: float
    n_train: int
    n_test: int


class RegressorMetrics(Model):
    mae_h: float
    n_train: int
    n_test: int


class FeatureImportance(Model):
    name: str
    label: str
    importance: float


class ModelInfoOut(Model):
    summary: str = Field(description="Одна строка: какой предиктор реально активен; при откате — причина")
    active: Literal["catboost", "formula"]
    requested: str = Field(description="PREDICTOR из .env")
    fallback_reason: str | None = Field(description="Почему включилась формула вместо CatBoost")
    synthetic: bool = Field(description="Модель обучена на синтетической истории")
    note: str
    used_at_runtime: ModelUsage
    trained_at: str | None
    seed: int | None
    classifier: ClassifierMetrics | None
    regressor: RegressorMetrics | None
    feature_importance: list[FeatureImportance]


# ---------- Аккаунты (POST /api/auth/register, /api/auth/login, GET /api/auth/me) ----------

Role = Literal["logist", "expeditor"]


Permission = Literal["run_scenario", "reset_demo", "decide_alert"]


class AuthRegisterIn(Model):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    email: Annotated[str, StringConstraints(max_length=254)]
    password: Annotated[str, StringConstraints(max_length=256)]
    role: Role


class AuthLoginIn(Model):
    email: Annotated[str, StringConstraints(max_length=254)]
    password: Annotated[str, StringConstraints(max_length=256)]


class AuthUser(Model):
    id: str
    name: str
    email: str
    role: Role
    permissions: list[Permission] = Field(
        default_factory=list, description="Логист: run_scenario, reset_demo, decide_alert; экспедитор — пусто")


class AuthOut(Model):
    token: str = Field(description="JWT на 7 дней: заголовок Authorization: Bearer <token> для /api/auth/me")
    user: AuthUser



# ---------- Telegram Mini App (POST /api/tg/auth) ----------

class TgAuthIn(Model):
    init_data: Annotated[str, StringConstraints(min_length=1, max_length=8192)] = Field(description="Telegram.WebApp.initData как есть")


class TgUser(Model):
    id: int
    name: str
    username: str | None = None


class TgAuthOut(Model):
    token: str = Field(description="Сессия на 24 ч: Authorization: Bearer на /api/*, ?token= на /ws")
    expires_at: str
    user: TgUser
    company: str = Field(description="Демо-кабинет, напр. «Каспий Логистик»")
