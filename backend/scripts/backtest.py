"""Ретроспективная симуляция на исторической погоде: погода настоящая, рейсы условные.

1. Скачивает почасовую высоту волны Open-Meteo Marine за прошлые 12 месяцев в тех же точках моря,
   что и живой прогноз (app/weather.py, MARINE_POINTS): подход к Астрахани, Оля, Махачкала.
   Архив сохраняется в data/wave_history.json — повторный запуск без сети берёт его (--offline).
2. По каждому порту: окна, когда волна не ниже предела парома (meta.wave_limit_m из сида, 2,5 м),
   их число, суммарные часы, самое длинное окно, распределение часов по месяцам. Часы, где модель
   волны не дала значения (null), считаются отдельно: это не шторм, а «нет данных» (зимой — обычно
   ледовый покров на мелководном Северном Каспии; сам Open-Meteo причину не сообщает).
3. Условный рейс Астрахань → Энзели раз в 48 ч по расписанию сида (07:00 UTC, в пути 48 ч) и
   условный рейс Махачкала → Энзели через 20 ч после него (в пути 34 ч), тоже раз в 48 ч.
   Правило закрытия — как у наблюдателя угроз (dispatcher.threats): волна в порту в момент
   отправления не ниже предела. «Ничего не делать» — первый открытый рейс из Астрахани;
   обход — первый открытый рейс из Махачкалы; обход спасает, если прибывает раньше ожидания.

Результат: data/backtest.json, график docs/pitch/backtest.png.
Запуск из backend/:  python scripts/backtest.py [--offline]
"""
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.weather import MARINE_POINTS, MARINE_URL  # noqa: E402

PORTS = ["astrakhan", "olya", "makhachkala"]
NAMES = {"astrakhan": "Астрахань", "olya": "Оля", "makhachkala": "Махачкала"}
RAW = ROOT / "data" / "wave_history.json"
OUT = ROOT / "data" / "backtest.json"
PNG = ROOT.parent / "docs" / "pitch" / "backtest.png"
SEED = json.loads((ROOT / "data" / "seed.json").read_text(encoding="utf-8"))
LIMIT = SEED["meta"]["wave_limit_m"]

# условное расписание — тот же ритм, что в сиде: паром А раз в 48 ч, паром М через 20 ч после него
SAIL = {s["id"]: s for s in SEED["sailings"]}
A_DUR = SAIL["sl-ast-anz-1114"]["duration_h"]                       # 48
M_DUR = SAIL["sl-mkh-anz-1115"]["duration_h"]                       # 34
A_DEP_HOUR = int(SAIL["sl-ast-anz-1114"]["departure"][11:13])       # 07 UTC
M_OFFSET_H = 20                                                      # паром М — через 20 ч после А
PERIOD_H = 48


def fetch(start: str, end: str) -> dict:
    lat = ",".join(str(MARINE_POINTS[p][0]) for p in PORTS)
    lon = ",".join(str(MARINE_POINTS[p][1]) for p in PORTS)
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "hourly": "wave_height",
                                "start_date": start, "end_date": end, "timezone": "UTC"})
    req = urllib.request.Request(f"{MARINE_URL}?{q}", headers={"User-Agent": "caspian-dispatcher/0.2"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    data = data if isinstance(data, list) else [data]
    out = {"source": MARINE_URL, "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "start_date": start, "end_date": end, "points": {}}
    for port, d in zip(PORTS, data):
        if "hourly" not in d:
            raise SystemExit(f"Open-Meteo не отдал историю для {port}: {d}")
        out["points"][port] = {"requested": MARINE_POINTS[port], "grid": [d["latitude"], d["longitude"]],
                               "t0": d["hourly"]["time"][0] + ":00Z", "wave": d["hourly"]["wave_height"]}
    return out


def windows(wave: list, t0: datetime) -> list[dict]:
    """Непрерывные окна, где волна не ниже предела."""
    out, start = [], None
    for i, w in enumerate(wave + [None]):
        hit = w is not None and w >= LIMIT
        if hit and start is None:
            start = i
        elif not hit and start is not None:
            out.append({"start": (t0 + timedelta(hours=start)).isoformat(), "hours": i - start,
                        "peak_m": max(wave[start:i])})
            start = None
    return out


def port_stats(p: dict) -> dict:
    t0 = datetime.fromisoformat(p["t0"].replace("Z", "+00:00"))
    wave = p["wave"]
    win = windows(wave, t0)
    by_month = defaultdict(lambda: {"closed_h": 0, "no_data_h": 0, "max_wave_m": 0.0})
    for i, w in enumerate(wave):
        m = (t0 + timedelta(hours=i)).strftime("%Y-%m")
        if w is None:
            by_month[m]["no_data_h"] += 1
        else:
            by_month[m]["max_wave_m"] = max(by_month[m]["max_wave_m"], w)
            if w >= LIMIT:
                by_month[m]["closed_h"] += 1
    known = [w for w in wave if w is not None]
    return {
        "grid_point": p["grid"], "hours_total": len(wave), "hours_no_data": len(wave) - len(known),
        "windows": len(win), "closed_hours": sum(w["hours"] for w in win),
        "longest_window_h": max((w["hours"] for w in win), default=0),
        "max_wave_m": round(max(known), 2) if known else None,
        "hours_over": {f"{x:g}": sum(w >= x for w in known) for x in (1.0, 1.5, 2.0, LIMIT)},
        "by_month": {m: {**v, "max_wave_m": round(v["max_wave_m"], 2)} for m, v in sorted(by_month.items())},
        "window_list": win,
    }


def sailings(raw: dict) -> dict:
    """Условные рейсы раз в 48 ч: сколько отправлений из Астрахани попало в закрытое окно и сколько
    из них спас обход через Махачкалу (раньше прибытие в Энзели, чем ожидание следующего рейса А)."""
    pa, pm = raw["points"]["astrakhan"], raw["points"]["makhachkala"]
    t0 = datetime.fromisoformat(pa["t0"].replace("Z", "+00:00"))
    n = len(pa["wave"])

    def wave(p, t):
        i = int((t - t0).total_seconds() // 3600)
        return p["wave"][i] if 0 <= i < n else None

    def state(p, t):
        w = wave(p, t)
        return "no_data" if w is None else "closed" if w >= LIMIT else "open"

    first = t0.replace(hour=A_DEP_HOUR)
    deps = []
    t = first
    while t + timedelta(hours=PERIOD_H * 3) < t0 + timedelta(hours=n):   # запас на ожидание
        deps.append(t)
        t += timedelta(hours=PERIOD_H)

    res = {"departures": len(deps), "closed": 0, "saved_by_makhachkala": 0, "no_data": 0,
           "no_data_makhachkala_open": 0, "closed_list": []}
    for d in deps:
        st = state(pa, d)
        if st == "open":
            continue
        # первый открытый рейс А и первый открытый рейс М
        wait = next((d + timedelta(hours=PERIOD_H * k) for k in range(1, 30)
                     if state(pa, d + timedelta(hours=PERIOD_H * k)) == "open"), None)
        alt = next((d + timedelta(hours=M_OFFSET_H + PERIOD_H * k) for k in range(0, 30)
                    if state(pm, d + timedelta(hours=M_OFFSET_H + PERIOD_H * k)) == "open"), None)
        arr_wait = wait + timedelta(hours=A_DUR) if wait else None
        arr_alt = alt + timedelta(hours=M_DUR) if alt else None
        saved = arr_alt is not None and (arr_wait is None or arr_alt < arr_wait)
        if st == "closed":
            res["closed"] += 1
            res["saved_by_makhachkala"] += saved
            res["closed_list"].append({"departure": d.isoformat(), "wave_m": wave(pa, d),
                                       "wait_until": wait.isoformat() if wait else None,
                                       "makhachkala": alt.isoformat() if alt else None, "saved": saved})
        else:
            res["no_data"] += 1
            res["no_data_makhachkala_open"] += state(pm, d + timedelta(hours=M_OFFSET_H)) == "open"
    return res


def plot(raw: dict, stats: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(12, 7.5), sharex=True, dpi=140)
    for ax, port in zip(axes, PORTS):
        p = raw["points"][port]
        t0 = datetime.fromisoformat(p["t0"].replace("Z", "+00:00"))
        ts = [t0 + timedelta(hours=i) for i in range(len(p["wave"]))]
        ys = [float("nan") if w is None else w for w in p["wave"]]
        ax.plot(ts, ys, lw=0.6, color="#2F80ED")
        ax.axhline(LIMIT, color="#EF4444", lw=1, ls="--")
        nod = [t for t, w in zip(ts, p["wave"]) if w is None]
        for t in nod:
            ax.axvspan(t, t + timedelta(hours=1), color="#94A3B8", alpha=0.25, lw=0)
        s = stats[port]
        ax.set_ylim(0, max(LIMIT + 0.5, (s["max_wave_m"] or 0) + 0.3))
        ax.set_ylabel("волна, м")
        ax.set_title(f"{NAMES[port]}: максимум {s['max_wave_m']} м, часов ≥ {LIMIT:g} м — {s['closed_hours']}, "
                     f"нет данных — {s['hours_no_data']} ч", fontsize=10, loc="left")
        ax.grid(alpha=0.3)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m.%Y"))
    fig.suptitle("Ретроспективная симуляция на исторической погоде: волна Open-Meteo Marine за 12 месяцев\n"
                 f"красный пунктир — предел парома {LIMIT:g} м; серым — часы без данных о волне", fontsize=11)
    fig.tight_layout()
    PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PNG)
    print("график:", PNG)


def main():
    if "--offline" in sys.argv and RAW.exists():
        raw = json.loads(RAW.read_text(encoding="utf-8"))
    else:
        end = datetime.now(timezone.utc).date() - timedelta(days=1)
        start = end - timedelta(days=364)
        raw = fetch(start.isoformat(), end.isoformat())
        RAW.write_text(json.dumps(raw, separators=(",", ":")), encoding="utf-8")
    stats = {p: port_stats(raw["points"][p]) for p in PORTS}
    out = {
        "title": "Ретроспективная симуляция на исторической погоде",
        "note": "Погода настоящая (архив Open-Meteo Marine), рейсы условные: раз в 48 ч по ритму расписания "
                "демо. Правило закрытия — как у наблюдателя угроз: волна в порту в момент отправления не ниже "
                f"предела {LIMIT:g} м. Часы без данных о волне — не шторм; причину Open-Meteo не сообщает "
                "(зимой на мелководном Северном Каспии — обычно лёд).",
        "source": raw["source"], "fetched_at": raw["fetched_at"],
        "period": {"start": raw["start_date"], "end": raw["end_date"]},
        "wave_limit_m": LIMIT,
        "schedule": {"period_h": PERIOD_H, "astrakhan_departure_utc": f"{A_DEP_HOUR:02d}:00",
                     "astrakhan_duration_h": A_DUR, "makhachkala_offset_h": M_OFFSET_H,
                     "makhachkala_duration_h": M_DUR},
        "ports": {p: {k: v for k, v in s.items()} for p, s in stats.items()},
        "sailings": sailings(raw),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("результат:", OUT)
    for p in PORTS:
        s = stats[p]
        print(f"  {NAMES[p]:10s} окон {s['windows']}, часов закрытия {s['closed_hours']}, самое длинное "
              f"{s['longest_window_h']} ч, максимум {s['max_wave_m']} м, без данных {s['hours_no_data']} ч")
    sv = out["sailings"]
    print(f"  рейсов {sv['departures']}, в закрытое окно {sv['closed']}, спас обход {sv['saved_by_makhachkala']}; "
          f"без данных о волне у Астрахани {sv['no_data']} (Махачкала открыта в {sv['no_data_makhachkala_open']})")
    plot(raw, stats)


if __name__ == "__main__":
    main()
