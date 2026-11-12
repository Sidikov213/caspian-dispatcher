"""Предиктор срыва стыковки с паромом.

Интерфейс: `get_predictor().predict(PredictContext) -> PredictorResult`. Диспетчер знает только его.
Сейчас — FormulaPredictor (без ML, на защите так и называем: «логистическая формула»).
CatBoostPredictor подключается в get_predictor() по наличию data/model.cbm и берёт признаки из
PredictContext.features(); dispatcher.py при этом не меняется.

Два шага прогноза (CLAUDE.md, раздел 3):
1. здесь — вероятность срыва и самое раннее возможное отправление с факторами в часах;
2. в dispatcher — первый рейс по расписанию после самого раннего отправления → задержка прибытия.

Самое раннее отправление = открытие порта + очередь судов + таможня (если порт закрыт штормом),
и не раньше, чем груз успевает пройти очередь и таможню до окончания приёма.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .util import H, hours, ru
from .weather import Weather

# Логистическая формула: logit = A0 + B·превышение волны + Q·(очередь+таможня, ч) − C·ln(запас + K).
# Подобрана так, чтобы на шторме у №01–03 (запас 2/8/18 ч, волна 3,4 м) выходило 82/74/68%.
A0, B_WAVE, Q_DELAY, C_SLACK, K_SLACK = -2.569, 2.56, 0.3, 0.3709, 0.35
QUEUE_H_PER_LOAD = 20      # очередь судов: 20 ч на каждые 100% загрузки сверх 60%
QUEUE_FREE_LOAD = 0.6
LAND_SLACK_H = 24          # для сухопутного маршрута «запас» — сутки


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
        """Признаки для ML-модели — те же, на которых будет обучен CatBoost."""
        if self.port is None:
            return {"wave_m": 0.0, "slack_h": LAND_SLACK_H, "congestion": self.congestion,
                    "customs_h": self.customs_h, "cargo_type": self.cargo_type,
                    "month": 11, "has_ferry": 0}
        return {"wave_m": self.weather.max_wave(self.port, self.ready_at, self.departure),
                "slack_h": hours(self.ready_at, self.cutoff), "congestion": self.congestion,
                "customs_h": self.customs_h, "cargo_type": self.cargo_type,
                "month": self.departure.month, "has_ferry": 1}


@dataclass
class PredictorResult:
    miss_probability: float
    earliest_departure: datetime | None
    factors: list[dict]
    features: dict

    @property
    def level(self) -> str:
        return level_of(self.miss_probability)


class Predictor(Protocol):
    def predict(self, ctx: PredictContext) -> PredictorResult: ...


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z))


class FormulaPredictor:
    name = "formula"

    def predict(self, ctx: PredictContext) -> PredictorResult:
        q = queue_hours(ctx.congestion)
        delay = q + ctx.customs_h
        if ctx.port is None:
            p = _sigmoid(A0 + Q_DELAY * ctx.customs_h - C_SLACK * math.log(LAND_SLACK_H + K_SLACK))
            names = " и ".join(ctx.borders) or "границе"
            factors = [{"name": "border_queue", "label": f"Очередь на погранпереходах {names}",
                        "impact_hours": 0},
                       {"name": "customs_queue", "label": "Очередь на таможне", "impact_hours": ctx.customs_h}]
            return PredictorResult(round(p, 2), None, factors, ctx.features())

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
        slack = max(hours(ctx.ready_at, ctx.cutoff), 0.0)
        z = (A0 + B_WAVE * max(0.0, wave_max - ctx.wave_limit) + Q_DELAY * delay
             - C_SLACK * math.log(slack + K_SLACK))
        factors = [
            {"name": "wave_height", "label": f"Волна {ru(wave_max)} м", "impact_hours": wave_delay},
            {"name": "port_congestion", "label": f"Загрузка порта {round(ctx.congestion * 100)}%",
             "impact_hours": q},
            {"name": "customs_queue", "label": "Очередь на таможне", "impact_hours": ctx.customs_h},
        ]
        return PredictorResult(round(_sigmoid(z), 2), earliest, factors, ctx.features())


def get_predictor() -> Predictor:
    # TODO(ML): если есть data/model.cbm и установлен catboost — вернуть CatBoostPredictor().
    return FormulaPredictor()
