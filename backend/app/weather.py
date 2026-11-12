"""Погода: почасовой прогноз волны на 7 суток по портам Каспия + наложение сценария.

Базовый прогноз (без сценария) даёт источник:
  LiveForecast      — Open-Meteo Marine (волна) и Open-Meteo Forecast (ветер 10 м), forecast_days=7,
                      обновление раз в 30 мин (main.py), кэш в data/weather_cache.json. Источник
                      недоступен — работаем по кэшу: source "cache", stale — если кэшу больше часа.
  SyntheticForecast — синтетический прогноз, сеть не трогаем (WEATHER_MODE=synthetic, тесты, моки).
Алерты строятся по ближайшим 48 ч; 7 суток нужны, чтобы проверить обходной рейс через 64 ч.

Сценарий не выдумывает погоду с нуля, а поднимает прогноз в окне шторма: в портах шторма волна
не ниже значений сценария ровно в [start, end), до и после — 6-часовой разгон и спад от реальной волны;
у соседних портов — горб поверх прогноза. Вне окна волна остаётся реальной.
"""
import asyncio
import json
import logging
import math
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .util import H, hours, iso, parse

log = logging.getLogger("caspian.weather")

HORIZON_H = 168
FORECAST_DAYS = 7
REFRESH_S = 30 * 60
STALE_AFTER_MIN = 60

# средняя волна, м, и ветер, м/с — синтетический прогноз
WEATHER_BASE = {"astrakhan": 0.7, "olya": 0.8, "makhachkala": 1.0, "baku": 1.1,
                "aktau": 1.0, "anzali": 0.8, "amirabad": 0.7}
WIND = {"astrakhan": 6.5, "olya": 7.0, "makhachkala": 7.5, "baku": 8.0,
        "aktau": 7.0, "anzali": 5.5, "amirabad": 5.0}

# Точки моря для портов. Астрахань и Оля стоят на суше (Open-Meteo отдаёт null) — берём ближайшее
# открытое море на подходе к Волго-Каспийскому каналу. Остальные — координаты порта.
MARINE_POINTS = {"astrakhan": (45.45, 49.0), "olya": (45.2, 48.45), "makhachkala": (42.98, 47.5),
                 "baku": (39.95, 49.41), "aktau": (43.65, 51.16), "anzali": (37.47, 49.46),
                 "amirabad": (36.85, 53.37)}
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

STORM_FLOOR = 2.6   # минимум волны в окне шторма (выше предела 2,5 м)
RAMP_TOP = 2.45     # волна на границе окна (ниже предела)
RAMP_H = 6


def baseline(node: str, h: int) -> float:
    i = list(WEATHER_BASE).index(node)
    return round(WEATHER_BASE[node] + 0.25 * math.sin(2 * math.pi * h / 24 + i), 2)


# ---------------- источники ----------------

class SyntheticForecast:
    """Синтетический прогноз от sim_now. Сеть не трогает."""
    synthetic = True

    def series(self, node: str, sim_now: datetime) -> list[float]:
        return [baseline(node, h) for h in range(HORIZON_H)]

    def wind(self, node: str, sim_now: datetime) -> float:
        return WIND[node]

    def meta(self, sim_now: datetime, now: datetime) -> dict:
        return {"updated_at": iso(sim_now - timedelta(minutes=12)), "stale": False, "source": "cache"}

    async def refresh(self) -> bool:
        return False


class LiveForecast:
    """Open-Meteo с кэшем в файл. data = {fetched_at, points: {node: {t0, wave: [..], wind: [..]}}}."""
    synthetic = False

    def __init__(self, cache_path: Path, fetch=None):
        self.cache_path = Path(cache_path)
        self.fetch = fetch or fetch_open_meteo
        self.data: dict | None = None
        self.source = "cache"
        self.fallback = SyntheticForecast()
        try:
            self.data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = None

    async def refresh(self) -> bool:
        try:
            data = await asyncio.to_thread(self.fetch)
        except Exception as e:
            log.warning("Open-Meteo недоступен (%s) — работаем по кэшу", e)
            self.source = "cache"
            return False
        self.data, self.source = data, "open-meteo"
        try:
            self.cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.exception("не записал кэш погоды")
        return True

    def _point(self, node: str) -> dict | None:
        return (self.data or {}).get("points", {}).get(node)

    @staticmethod
    def _at(pt: dict, key: str, ts: datetime) -> float | None:
        vals = pt.get(key) or []
        known = [(i, v) for i, v in enumerate(vals) if v is not None]
        if not known:
            return None
        i = int(math.floor(hours(pt["t0"], ts)))
        exact = vals[i] if 0 <= i < len(vals) else None
        if exact is not None:
            return exact
        return min(known, key=lambda kv: abs(kv[0] - i))[1]   # за краем прогноза — ближайший час

    def series(self, node: str, sim_now: datetime) -> list[float]:
        pt = self._point(node)
        if pt is None or self._at(pt, "wave", sim_now) is None:
            return self.fallback.series(node, sim_now)
        return [round(self._at(pt, "wave", sim_now + H(h)), 2) for h in range(HORIZON_H)]

    def wind(self, node: str, sim_now: datetime) -> float:
        pt = self._point(node)
        v = self._at(pt, "wind", sim_now) if pt else None
        return round(v, 1) if v is not None else WIND[node]

    def meta(self, sim_now: datetime, now: datetime) -> dict:
        if not self.data:
            return {"updated_at": iso(sim_now), "stale": True, "source": "cache"}
        fetched = self.data["fetched_at"]
        stale = hours(fetched, now) * 60 > STALE_AFTER_MIN
        return {"updated_at": fetched, "stale": stale, "source": self.source}


def _get_json(url: str, params: dict) -> object:
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{q}", headers={"User-Agent": "caspian-dispatcher/0.2"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_open_meteo(marine: object, wind: object, fetched_at: datetime) -> dict:
    """Ответы Open-Meteo (несколько точек — список) → формат кэша."""
    marine = marine if isinstance(marine, list) else [marine]
    wind = wind if isinstance(wind, list) else [wind]
    points = {}
    for node, m, w in zip(MARINE_POINTS, marine, wind):
        times = m["hourly"]["time"]
        t0 = iso(datetime.fromisoformat(times[0]).replace(tzinfo=timezone.utc))
        points[node] = {"t0": t0, "wave": m["hourly"]["wave_height"],
                        "wind": w.get("hourly", {}).get("wind_speed_10m", [])}
    if not any(v is not None for p in points.values() for v in p["wave"]):
        raise ValueError("в ответе нет ни одного значения волны")
    return {"fetched_at": iso(fetched_at), "points": points}


def fetch_open_meteo() -> dict:
    lat = ",".join(str(p[0]) for p in MARINE_POINTS.values())
    lon = ",".join(str(p[1]) for p in MARINE_POINTS.values())
    base = {"latitude": lat, "longitude": lon, "forecast_days": FORECAST_DAYS, "timezone": "UTC"}
    marine = _get_json(MARINE_URL, {**base, "hourly": "wave_height"})
    wind = _get_json(FORECAST_URL, {**base, "hourly": "wind_speed_10m", "wind_speed_unit": "ms"})
    return parse_open_meteo(marine, wind, datetime.now(timezone.utc).replace(microsecond=0))


def make_forecast(mode: str, cache_path: Path):
    if mode == "synthetic":
        return SyntheticForecast()
    return LiveForecast(cache_path)


# ---------------- сценарий поверх прогноза ----------------

def overlay_wave(calm: float, node: str, h: int, ov: dict, hs: float, he: float) -> float:
    if node in ov.get("storm_nodes", ()):
        peak = ov["peak"]
        if hs <= h < he:
            return max(calm, round(STORM_FLOOR + (peak - STORM_FLOOR) * math.sin(math.pi * (h - hs) / (he - hs)), 2))
        if hs - RAMP_H <= h < hs:
            return max(calm, round(calm + (RAMP_TOP - calm) * (h - (hs - RAMP_H)) / RAMP_H, 2))
        if he <= h <= he + RAMP_H:
            return max(calm, round(RAMP_TOP - (RAMP_TOP - calm) * (h - he) / RAMP_H, 2))
    bump = ov.get("bumps", {}).get(node)
    if bump:
        amp, center_h, width_h = bump
        return round(calm + amp * math.exp(-(((h - center_h) / width_h) ** 2)), 2)
    return calm


class Weather:
    """Прогноз на момент sim_now с учётом активных сценариев."""

    def __init__(self, sim_now: datetime, scenarios: list[dict] | None = None, forecast=None):
        self.sim_now = sim_now
        self.forecast = forecast or SyntheticForecast()
        self.series: dict[str, list[float]] = {}
        self.base: dict[str, list[float]] = {}
        for node in WEATHER_BASE:
            base = self.forecast.series(node, sim_now)
            row = []
            for h in range(HORIZON_H):
                w = base[h]
                for sc in scenarios or ():
                    ov = sc.get("_overlay")
                    if ov:
                        w = overlay_wave(w, node, h, ov, hours(sim_now, sc["start"]), hours(sim_now, sc["end"]))
                row.append(w)
            self.base[node] = base
            self.series[node] = row

    def wave(self, node: str, ts) -> float:
        """Волна в порту на час ts; для узлов без моря — 0."""
        row = self.series.get(node)
        if row is None:
            return 0.0
        h = int(math.floor(hours(self.sim_now, ts)))
        return row[min(max(h, 0), HORIZON_H - 1)]

    def base_wave(self, node: str, ts) -> float:
        """Волна без сценария — для объяснения в /demo/check."""
        row = self.base.get(node)
        if row is None:
            return 0.0
        return row[min(max(int(math.floor(hours(self.sim_now, ts))), 0), HORIZON_H - 1)]

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

    def to_api(self, now: datetime | None = None) -> dict:
        pts = []
        for node, row in self.series.items():
            fc = [{"ts": iso(self.sim_now + H(h)), "wave_height_m": w} for h, w in enumerate(row)]
            pts.append({"node_id": node, "wave_height_m": row[0],
                        "wind_ms": self.forecast.wind(node, self.sim_now), "forecast": fc})
        return {**self.forecast.meta(self.sim_now, parse(now) if now else self.sim_now), "points": pts}
