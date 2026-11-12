"""Предиктор срыва стыковки с паромом.

Интерфейс: `get_predictor().predict(PredictContext) -> PredictorResult`. Диспетчер знает только его.
Выбор — PREDICTOR в .env:
  catboost (по умолчанию) — вероятность срыва даёт классификатор CatBoost (data/model.cbm), обученный
             на синтетической истории (scripts/gen_history.py, scripts/train.py);
  formula  — логистическая формула без ML (на защите так и называем).
Если модели нет или catboost не импортируется — откат на формулу с записью в лог (причина видна
в GET /api/model).

Два шага прогноза (CLAUDE.md, раздел 3):
1. здесь — вероятность срыва и самое раннее возможное отправление с факторами в часах;
2. в dispatcher — первый рейс по расписанию после самого раннего отправления → задержка прибытия.

Самое раннее отправление и факторы в часах (`Risk.factors`) у обоих предикторов считает один и тот же
код по прогнозу погоды и расписанию (`timing`): открытие порта + очередь судов + таможня, и не раньше,
чем груз успевает пройти очередь и таможню до окончания приёма. Модель меняет только вероятность и
добавляет объяснение — `Risk.probability_drivers`: три главных признака по SHAP классификатора с
вкладом в процентных пунктах. Регрессор сдвига (data/model_shift.cbm) на сервере не используется —
он только проверка в отчёте и на графике.
"""
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .util import MSK, H, hours, ru
from .weather import Weather

log = logging.getLogger("caspian")

# Логистическая формула: logit = A0 + B·превышение волны + Q·(очередь+таможня, ч) − C·ln(запас + K).
# Подобрана так, чтобы на шторме у №01–03 (запас 2/8/18 ч, волна 3,4 м) выходило 82/74/68%.
A0, B_WAVE, Q_DELAY, C_SLACK, K_SLACK = -2.569, 2.56, 0.3, 0.3709, 0.35
QUEUE_H_PER_LOAD = 20      # очередь судов: 20 ч на каждые 100% загрузки сверх 60%
QUEUE_FREE_LOAD = 0.6
LAND_SLACK_H = 24          # для сухопутного маршрута «запас» — сутки

# Признаки модели — те же колонки, что в data/history.csv (scripts/gen_history.py).
FEATURES = ["wave_height_m", "wind_ms", "port_congestion", "customs_queue_h", "buffer_hours",
            "month", "weekday", "cargo_type", "port_id", "ice"]
CAT_FEATURES = ["cargo_type", "port_id"]
# Лёд: в прототипе по календарю — Астрахань и Оля, декабрь–март. Махачкала не замерзает.
ICE_PORTS = {"astrakhan", "olya"}
ICE_MONTHS = {12, 1, 2, 3}

MONTHS_RU = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь",
             "октябрь", "ноябрь", "декабрь")
WEEKDAYS_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
CARGO_RU = {"grain": "зерно", "metal": "металл", "equipment": "оборудование", "textile": "текстиль",
            "fertilizer": "удобрения"}
PORTS_RU = {"astrakhan": "Астрахань", "olya": "Оля", "makhachkala": "Махачкала", "aktau": "Актау",
            "baku": "Баку"}


def queue_hours(congestion: float) -> float:
    return float(round(max(0.0, congestion - QUEUE_FREE_LOAD) * QUEUE_H_PER_LOAD))


def level_of(p: float) -> str:
    return "high" if p >= 0.6 else "medium" if p >= 0.3 else "low"


@dataclass
class PredictContext:
    shipment_id: str
    cargo_type: str
    weight_t: float
    weather: Weather
    wave_limit: float
    customs_h: float                 # очередь на таможне в порту, ч (с учётом сценария)
    congestion: float                # загрузка порта 0..1 (с учётом сценария)
    port: str | None = None          # порт отправления парома; None — маршрут без парома
    ready_at: datetime | None = None  # груз готов в порту (после обработки)
    departure: datetime | None = None
    cutoff: datetime | None = None
    borders: list[str] = field(default_factory=list)  # названия погранпереходов (для суши)

    def features(self) -> dict:
        """Признаки модели в том виде, в каком они лежат в истории. Для маршрута без парома — пусто."""
        if self.port is None:
            return {}
        local = self.departure.astimezone(MSK)
        return {"wave_height_m": self.weather.max_wave(self.port, self.ready_at, self.departure),
                "wind_ms": float(self.weather.wind(self.port, self.departure)),
                "port_congestion": float(self.congestion),
                "customs_queue_h": float(self.customs_h),
                "buffer_hours": max(hours(self.ready_at, self.cutoff), 0.0),
                "month": local.month, "weekday": local.weekday(),
                "cargo_type": self.cargo_type, "port_id": self.port,
                "ice": int(self.port in ICE_PORTS and local.month in ICE_MONTHS)}


@dataclass
class PredictorResult:
    miss_probability: float
    earliest_departure: datetime | None
    factors: list[dict]
    features: dict
    probability_drivers: list[dict] | None = None

    @property
    def level(self) -> str:
        return level_of(self.miss_probability)


class Predictor(Protocol):
    name: str

    def predict(self, ctx: PredictContext) -> PredictorResult: ...


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z))


@dataclass
class Timing:
    earliest: datetime
    factors: list[dict]
    queue_h: float
    delay_h: float          # очередь судов + таможня
    wave_max: float
    slack_h: float


def timing(ctx: PredictContext) -> Timing:
    """Самое раннее отправление и факторы в часах — по прогнозу погоды и расписанию рейса."""
    q = queue_hours(ctx.congestion)
    delay = q + ctx.customs_h
    w = ctx.weather
    dep = ctx.departure
    closed = w.wave(ctx.port, dep) >= ctx.wave_limit
    port_open = (w.first_calm(ctx.port, dep, ctx.wave_limit) or dep + H(168)) if closed else dep
    wave_delay = hours(dep, port_open)
    handling_buffer = hours(ctx.cutoff, dep)       # окончание приёма → отправление
    earliest = max(dep, ctx.ready_at + H(delay + handling_buffer))
    if closed:
        earliest = max(earliest, port_open + H(delay))
    wave_max = w.max_wave(ctx.port, ctx.ready_at, port_open)
    factors = [
        {"name": "wave_height", "label": f"Волна {ru(wave_max)} м", "impact_hours": wave_delay},
        {"name": "port_congestion", "label": f"Загрузка порта {round(ctx.congestion * 100)}%",
         "impact_hours": q},
        {"name": "customs_queue", "label": "Очередь на таможне", "impact_hours": ctx.customs_h},
    ]
    return Timing(earliest, factors, q, delay, wave_max, max(hours(ctx.ready_at, ctx.cutoff), 0.0))


def land_result(ctx: PredictContext) -> PredictorResult:
    """Маршрут без парома: стыковки нет, модель неприменима — формула от очереди на границе."""
    p = _sigmoid(A0 + Q_DELAY * ctx.customs_h - C_SLACK * math.log(LAND_SLACK_H + K_SLACK))
    names = " и ".join(ctx.borders) or "границе"
    factors = [{"name": "border_queue", "label": f"Очередь на погранпереходах {names}", "impact_hours": 0},
               {"name": "customs_queue", "label": "Очередь на таможне", "impact_hours": ctx.customs_h}]
    return PredictorResult(round(p, 2), None, factors, ctx.features())


class FormulaPredictor:
    name = "formula"
    fallback_reason: str | None = None   # заполнен, если формула включилась вместо CatBoost

    def predict(self, ctx: PredictContext) -> PredictorResult:
        if ctx.port is None:
            return land_result(ctx)
        t = timing(ctx)
        z = (A0 + B_WAVE * max(0.0, t.wave_max - ctx.wave_limit) + Q_DELAY * t.delay_h
             - C_SLACK * math.log(t.slack_h + K_SLACK))
        return PredictorResult(round(_sigmoid(z), 2), t.earliest, t.factors, ctx.features())


def driver_label(name: str, v) -> str:
    if name == "wave_height_m":
        return f"Волна {ru(v)} м"
    if name == "wind_ms":
        return f"Ветер {ru(v, 0)} м/с"
    if name == "port_congestion":
        return f"Загрузка порта {round(v * 100)}%"
    if name == "customs_queue_h":
        return f"Очередь на таможне {ru(v, 0)} ч"
    if name == "buffer_hours":
        return f"Запас до окончания приёма {ru(v, 0)} ч"
    if name == "month":
        return f"Месяц: {MONTHS_RU[int(v) - 1]}"
    if name == "weekday":
        return f"День недели: {WEEKDAYS_RU[int(v)]}"
    if name == "cargo_type":
        return f"Тип груза: {CARGO_RU.get(v, v)}"
    if name == "port_id":
        return f"Порт {PORTS_RU.get(v, v)}"
    if name == "ice":
        return "Лёд в порту" if v else "Без льда"
    return name


class CatBoostPredictor:
    """Вероятность срыва — классификатор CatBoost; отправление и факторы в часах — `timing`.

    probability_drivers: три признака с наибольшим |вкладом| по SHAP. SHAP CatBoost считает в логитах;
    вклад признака в п. п. = p − σ(logit − SHAP признака), то есть насколько вероятность была бы ниже
    (или выше) без его вклада при прочих равных. Ни к чему не приводится: сумма вкладов не обязана
    равняться p.
    """
    name = "catboost"
    fallback_reason = None

    def __init__(self, model_path: Path | None = None):
        from catboost import CatBoostClassifier, Pool   # ImportError → откат в get_predictor
        from .config import MODEL_PATH
        path = Path(model_path or MODEL_PATH)
        if not path.exists():
            raise FileNotFoundError(f"нет файла модели {path.name} (запустите scripts/train.py)")
        self._Pool = Pool
        self.model = CatBoostClassifier()
        self.model.load_model(str(path))
        if list(self.model.feature_names_) != FEATURES:
            raise ValueError(f"признаки модели {self.model.feature_names_} не совпадают с {FEATURES}")
        self.path = path

    def _pool(self, f: dict):
        return self._Pool([[f[k] for k in FEATURES]], feature_names=FEATURES, cat_features=CAT_FEATURES)

    def probability(self, f: dict) -> float:
        return float(self.model.predict_proba(self._pool(f))[0][1])

    def predict(self, ctx: PredictContext) -> PredictorResult:
        if ctx.port is None:
            return land_result(ctx)
        t = timing(ctx)
        f = ctx.features()
        pool = self._pool(f)
        p = float(self.model.predict_proba(pool)[0][1])
        shap = self.model.get_feature_importance(pool, type="ShapValues")[0]
        z = float(sum(shap))                       # логит = ожидание + сумма вкладов
        drivers = [{"name": k, "label": driver_label(k, f[k]),
                    "impact_pp": round(100 * (_sigmoid(z) - _sigmoid(z - float(shap[i]))), 1)}
                   for i, k in enumerate(FEATURES)]
        drivers.sort(key=lambda d: -abs(d["impact_pp"]))
        return PredictorResult(round(p, 2), t.earliest, t.factors, f, drivers[:3])


def get_predictor(kind: str | None = None) -> Predictor:
    """PREDICTOR=catboost|formula. Модели нет или catboost не импортируется → формула и запись в лог."""
    if kind is None:
        from .config import PREDICTOR
        kind = PREDICTOR
    kind = (kind or "catboost").strip().lower()
    if kind == "formula":
        return FormulaPredictor()
    if kind != "catboost":
        reason = f"неизвестный PREDICTOR={kind!r}"
    else:
        try:
            return CatBoostPredictor()
        except ImportError as e:
            reason = f"catboost не импортируется: {e}"
        except Exception as e:     # нет файла, файл битый, другие признаки
            reason = f"модель не загрузилась: {e}"
    log.warning("Предиктор CatBoost недоступен (%s) — откат на логистическую формулу", reason)
    fp = FormulaPredictor()
    fp.fallback_reason = reason
    return fp
