"""Синтетическая история стыковок «груз → паром» для обучения модели (docs/PLAN.md, раздел «Данные»).

История сгенерирована по правилам ниже, это не данные порта. Модель на ней показывает работающий
конвейер; на настоящей истории она переобучается без изменения кода (те же колонки).

Одна строка — одна запланированная стыковка в порту Каспия. Признаки — то, что известно за 1–2 суток
до отправления (прогноз волны и ветра, загрузка порта, очередь на таможне, запас времени):
  wave_height_m, wind_ms, port_congestion, customs_queue_h, buffer_hours, month, weekday,
  cargo_type, port_id, ice
Цели:
  departure_shift_h  — на сколько позже планового рейса возможно отправление, ч (0 — успевает)
  missed_connection  — 1, если задержка в узле больше запаса (груз не уходит своим рейсом)

Закономерности:
- волна: сезонность (осень–зима выше), тяжёлый хвост, штормовые эпизоды. Прогноз шторма на 1–2 суток
  сбывается не всегда (PARAMS["storm_hit_p"]); если шторм прошёл стороной, волна ниже прогноза, а
  очередь судов после шторма не нарастает. Фактическая волна до 2 м не влияет, на 2–3,5 м задержка
  растёт (быстрее в начале диапазона), выше 3,5 м паром стоит до конца шторма, 32…48 ч
  (в PLAN.md «+12…48 ч»; взят верх диапазона, чтобы рост был непрерывным);
- загрузка порта: выше в начале недели и в сезон зерна (август–октябрь), растёт после шторма;
  задержка растёт нелинейно после 0,8;
- лёд: Астрахань и Оля, декабрь–март, +6…24 ч; Махачкала, Актау, Баку — без льда;
- таможня: логнормальная очередь, длиннее для «сложных» грузов (оборудование, удобрения); зерно
  (фитосанконтроль) и оборудование чаще уходят на досмотр; в задержку идёт только превышение
  планового окна оформления;
- шум (груз чаще приходит чуть раньше срока, разброс растёт с задержкой) и 2% выбросов (поломка,
  проверка груза, забастовка) +10…60 ч.

Воспроизводимо: одинаковые seed и PARAMS → одинаковый CSV.
Запуск (из backend/): .venv/Scripts/python scripts/gen_history.py [--rows 30000] [--seed 42]
"""
import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
HISTORY_PATH = DATA_DIR / "history.csv"

SEED = 42
ROWS = 30000

FEATURES = ["wave_height_m", "wind_ms", "port_congestion", "customs_queue_h", "buffer_hours",
            "month", "weekday", "cargo_type", "port_id", "ice"]
CAT_FEATURES = ["cargo_type", "port_id"]
TARGETS = ["departure_shift_h", "missed_connection"]

PORTS = {  # порт: (доля стыковок, базовая загрузка — как в seed.json)
    "astrakhan": (0.30, 0.62), "olya": (0.15, 0.50), "makhachkala": (0.25, 0.55),
    "aktau": (0.15, 0.50), "baku": (0.15, 0.50),
}
ICE_PORTS = {"astrakhan", "olya"}
ICE_MONTHS = {12: 0.30, 1: 0.55, 2: 0.55, 3: 0.30}   # месяц: доля дней со льдом
CARGO = {"grain": 0.30, "metal": 0.20, "equipment": 0.15, "textile": 0.15, "fertilizer": 0.20}
COMPLEX_CARGO = {"equipment", "fertilizer"}   # очередь на оформление длиннее
INSPECTED_CARGO = {"grain", "equipment"}       # чаще досмотр: фитосанконтроль зерна, сверка оборудования

# Параметры шума и закономерностей. Пишутся в data/model_report.json.
PARAMS = {
    "storm_p_cold": 0.30,        # доля штормовых эпизодов, октябрь–март
    "storm_p_warm": 0.08,        # апрель–сентябрь
    "storm_congestion_boost": 0.25,  # после шторма загрузка порта выше: + U(0, boost)
    "tight_buffer_p": 0.35,      # доля плотных стыковок (запас 0–8 ч), остальные — гамма, в среднем 14 ч
    "storm_hit_p": 0.58,         # прогноз шторма (≥ 2 м) сбывается
    "storm_miss_lo": 0.35, "storm_miss_hi": 0.70,  # шторм прошёл стороной: волна = прогноз · U(lo, hi)
    "storm_queue_load": 0.15,    # прирост загрузки порта из-за шторма (не случается, если шторм прошёл мимо)
    "wave_forecast_sigma": 0.10,  # ошибка прогноза волны, лог-нормальная
    "wave_free_m": 2.0,          # до этой волны влияния нет
    "wave_stop_m": 3.5,          # выше паром стоит
    "ramp_max_h": 32.0,          # задержка у верхней границы роста (3,5 м)
    "ramp_power": 0.4,           # форма роста на 2–3,5 м: 1 — линейный, < 1 — быстрый рост с начала
    "stop_min_h": 32.0, "stop_max_h": 48.0,  # паром стоит до конца шторма
    "congestion_knee": 0.8, "congestion_k": 120.0,   # нелинейный рост после 0,8: k·(c − 0,8)²
    "customs_sigma": 1.0,        # фактическая очередь на таможне = прогноз · LN(0, σ)
    "inspection_mult": 2.0,      # досматриваемые грузы: фактическая очередь × mult
    "customs_window_h": 1.0,     # плановое окно оформления: задержка — только сверх него
    "noise_mean_h": -1.0,        # среднее шума: < 0 — груз чаще приходит раньше срока
    "noise_sigma_h": 1.0,        # гауссов шум задержки, ч: σ = база + доля · задержка
    "noise_rel": 0.08,
    "outlier_p": 0.02,           # доля выбросов
    "outlier_min_h": 10.0, "outlier_max_h": 60.0,
}


def wave_part(w: np.ndarray, rng: np.random.Generator, p: dict) -> np.ndarray:
    """Задержка от фактической волны: 0 до 2 м, рост на 2–3,5 м, выше — паром стоит до конца шторма, 32…48 ч."""
    ramp = p["ramp_max_h"] * np.clip((w - p["wave_free_m"]) / (p["wave_stop_m"] - p["wave_free_m"]), 0, 1) ** p["ramp_power"]
    stop = p["stop_min_h"] + (p["stop_max_h"] - p["stop_min_h"]) * rng.beta(2, 3, len(w))
    return np.where(w < p["wave_free_m"], 0.0, np.where(w < p["wave_stop_m"], ramp, stop))


def node_delay(df: pd.DataFrame, rng: np.random.Generator, p: dict = PARAMS) -> np.ndarray:
    """Фактическая задержка в узле, ч, по признакам строки и случайности, которой признаки не видят."""
    n = len(df)
    wf = df["wave_height_m"].to_numpy()
    # прогноз шторма не сбылся: волна заметно ниже, а очередь судов и таможня после шторма не наросли
    missed_storm = (wf >= p["wave_free_m"]) & (rng.random(n) >= p["storm_hit_p"])
    realized = np.where(missed_storm, wf * rng.uniform(p["storm_miss_lo"], p["storm_miss_hi"], n),
                        wf * np.exp(rng.normal(0, p["wave_forecast_sigma"], n)))
    c = df["port_congestion"].to_numpy() - missed_storm * p["storm_queue_load"]
    congestion = p["congestion_k"] * np.maximum(0, c - p["congestion_knee"]) ** 2
    # таможня: в задержку идёт только превышение планового окна оформления
    inspected = np.isin(df["cargo_type"].to_numpy(), list(INSPECTED_CARGO))
    queue = (df["customs_queue_h"].to_numpy() / np.where(missed_storm, 1.5, 1.0)
             * np.where(inspected, p["inspection_mult"], 1.0)
             * np.exp(rng.normal(0, p["customs_sigma"], n)))
    customs = np.maximum(0.0, queue - p["customs_window_h"])
    ice = df["ice"].to_numpy() * rng.uniform(6, 24, n)
    base = wave_part(realized, rng, p) + congestion + customs + ice
    noise = p["noise_mean_h"] + rng.normal(0, 1, n) * (p["noise_sigma_h"] + p["noise_rel"] * base)
    outlier = (rng.random(n) < p["outlier_p"]) * rng.uniform(p["outlier_min_h"], p["outlier_max_h"], n)
    return np.maximum(0.0, base + noise + outlier)


def features(n: int, rng: np.random.Generator, p: dict = PARAMS) -> pd.DataFrame:
    day = rng.integers(0, 3 * 365, n)
    dates = pd.Timestamp("2023-01-01") + pd.to_timedelta(day, unit="D")
    month = dates.month.to_numpy()
    weekday = dates.day_of_week.to_numpy()
    cold = np.isin(month, [10, 11, 12, 1, 2, 3])

    season = 0.9 + 0.35 * np.cos(2 * math.pi * (month - 12) / 12)          # пик — декабрь
    wave = season * rng.gamma(2.2, 1 / 2.2, n)
    storm = rng.random(n) < np.where(cold, p["storm_p_cold"], p["storm_p_warm"])
    wave = np.where(storm, 2.3 + rng.gamma(2.0, 0.55, n), wave)
    wave = np.round(np.clip(wave, 0.1, 6.0), 2)
    wind = np.round(np.clip(3 + 4.2 * wave + rng.normal(0, 1.8, n), 0.5, 35), 1)

    ports = list(PORTS)
    port = rng.choice(ports, n, p=[PORTS[k][0] for k in ports])
    base = np.array([PORTS[k][1] for k in port])
    cong = (base + 0.06 * (weekday <= 1) + 0.08 * np.isin(month, [8, 9, 10])
            + p["storm_congestion_boost"] * (wave > 2.5) * rng.random(n) + rng.normal(0, 0.1, n))
    cong = np.round(np.clip(cong, 0, 1), 2)

    cargo_names = list(CARGO)
    cargo = rng.choice(cargo_names, n, p=[CARGO[k] for k in cargo_names])
    median = np.where(np.isin(cargo, list(COMPLEX_CARGO)), 1.6, 1.0) * (1 + 0.5 * (wave > 2.5))
    customs = np.round(median * np.exp(rng.normal(0, 0.6, n)), 1)

    tight = rng.random(n) < p["tight_buffer_p"]          # плотные стыковки: запас до 8 ч
    buffer = np.round(np.clip(np.where(tight, rng.uniform(0, 8, n), rng.gamma(2.0, 7.0, n)), 0, 48), 1)
    ice_p = np.array([ICE_MONTHS.get(m, 0.0) for m in month]) * np.isin(port, list(ICE_PORTS))
    ice = (rng.random(n) < ice_p).astype(int)
    return pd.DataFrame({"wave_height_m": wave, "wind_ms": wind, "port_congestion": cong,
                         "customs_queue_h": customs, "buffer_hours": buffer, "month": month,
                         "weekday": weekday, "cargo_type": cargo, "port_id": port, "ice": ice})


def generate(rows: int = ROWS, seed: int = SEED, params: dict = PARAMS) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = features(rows, rng, params)
    delay = node_delay(df, rng, params)
    df["departure_shift_h"] = np.round(np.maximum(0.0, delay - df["buffer_hours"].to_numpy()), 1)
    df["missed_connection"] = (delay > df["buffer_hours"].to_numpy()).astype(int)
    return df


def miss_rate(point: dict, samples: int = 200000, seed: int = 0, params: dict = PARAMS) -> float:
    """Истинная вероятность срыва для одной ситуации (Монте-Карло по правилам генератора)."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame([point] * samples)
    return float((node_delay(df, rng, params) > df["buffer_hours"].to_numpy()).mean())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=ROWS)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", type=Path, default=HISTORY_PATH)
    a = ap.parse_args()
    df = generate(a.rows, a.seed)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False, lineterminator="\n")
    print(f"{a.out}: {len(df)} строк, срыв стыковки в {df['missed_connection'].mean():.1%}, "
          f"seed {a.seed}")


if __name__ == "__main__":
    main()
