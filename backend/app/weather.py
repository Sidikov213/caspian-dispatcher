"""Погода: почасовой прогноз волны на 7 суток по портам Каспия + наложение сценария.

Сейчас базовый прогноз — синтетический «кэш» (та же формула, что строила моки). Настоящий
Open-Meteo Marine (forecast_days=7, раз в 30 мин, кэш в файл) подключается заменой `baseline`,
остальной код этого не заметит. Алерты строятся по ближайшим 48 ч; 7 суток нужны, чтобы проверить
обходной рейс, уходящий через 64 ч.

Сценарий не выдумывает погоду с нуля, а меняет прогноз в окне шторма: в портах шторма волна выше
предела ровно в [start, end), до и после — 6-часовой разгон и спад; у соседних портов — горб.
"""
import math
from datetime import datetime, timedelta

from .util import H, hours, iso

HORIZON_H = 168

# средняя волна, м, и ветер, м/с — синтетический базовый прогноз
WEATHER_BASE = {"astrakhan": 0.7, "olya": 0.8, "makhachkala": 1.0, "baku": 1.1,
                "aktau": 1.0, "anzali": 0.8, "amirabad": 0.7}
WIND = {"astrakhan": 6.5, "olya": 7.0, "makhachkala": 7.5, "baku": 8.0,
        "aktau": 7.0, "anzali": 5.5, "amirabad": 5.0}
STORM_FLOOR = 2.6   # минимум волны в окне шторма (выше предела 2,5 м)
RAMP_TOP = 2.45     # волна на границе окна (ниже предела)
RAMP_H = 6


def baseline(node: str, h: int) -> float:
    i = list(WEATHER_BASE).index(node)
    return round(WEATHER_BASE[node] + 0.25 * math.sin(2 * math.pi * h / 24 + i), 2)


def overlay_wave(calm: float, node: str, h: int, ov: dict, hs: float, he: float) -> float:
    if node in ov.get("storm_nodes", ()):
        peak = ov["peak"]
        if hs <= h < he:
            return round(STORM_FLOOR + (peak - STORM_FLOOR) * math.sin(math.pi * (h - hs) / (he - hs)), 2)
        if hs - RAMP_H <= h < hs:
            return round(calm + (RAMP_TOP - calm) * (h - (hs - RAMP_H)) / RAMP_H, 2)
        if he <= h <= he + RAMP_H:
            return round(RAMP_TOP - (RAMP_TOP - calm) * (h - he) / RAMP_H, 2)
    bump = ov.get("bumps", {}).get(node)
    if bump:
        amp, center_h, width_h = bump
        return round(calm + amp * math.exp(-(((h - center_h) / width_h) ** 2)), 2)
    return calm


class Weather:
    """Прогноз на момент sim_now с учётом активных сценариев."""

    def __init__(self, sim_now: datetime, scenarios: list[dict] | None = None):
        self.sim_now = sim_now
        self.series: dict[str, list[float]] = {}
        for node in WEATHER_BASE:
            row = []
            for h in range(HORIZON_H):
                w = baseline(node, h)
                for sc in scenarios or ():
                    ov = sc.get("_overlay")
                    if ov:
                        w = overlay_wave(w, node, h, ov, hours(sim_now, sc["start"]), hours(sim_now, sc["end"]))
                row.append(w)
            self.series[node] = row

    def wave(self, node: str, ts) -> float:
        """Волна в порту на час ts; для узлов без моря — 0."""
        row = self.series.get(node)
        if row is None:
            return 0.0
        h = int(math.floor(hours(self.sim_now, ts)))
        return row[min(max(h, 0), HORIZON_H - 1)]

    def max_wave(self, node: str, a, b) -> float:
        row = self.series.get(node)
        if row is None:
            return 0.0
        ha = max(int(math.floor(hours(self.sim_now, a))), 0)
        hb = min(int(math.floor(hours(self.sim_now, b))), HORIZON_H - 1)
        return max(row[ha:hb + 1] or [self.wave(node, a)])

    def first_calm(self, node: str, ts, limit: float):
        """Первый час ≥ ts, когда волна ниже предела (порт открыт). None — не открылся в горизонте."""
        t = ts
        end = self.sim_now + H(HORIZON_H)
        while t < end:
            if self.wave(node, t) < limit:
                return t
            t = t + timedelta(hours=1)
        return None

    def to_api(self) -> dict:
        pts = []
        for node, row in self.series.items():
            fc = [{"ts": iso(self.sim_now + H(h)), "wave_height_m": w} for h, w in enumerate(row)]
            pts.append({"node_id": node, "wave_height_m": row[0], "wind_ms": WIND[node], "forecast": fc})
        return {"updated_at": iso(self.sim_now - timedelta(minutes=12)), "stale": False,
                "source": "cache", "points": pts}
