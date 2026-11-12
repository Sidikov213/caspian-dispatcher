"""Сценарий от настоящего времени, погода Open-Meteo с кэшем, проверка демо, привязки бота в файле."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import gen_mocks as ref

from app.clock import Clock
from app.ledger import verify_chain
from app.state import State
from app.util import H, hours, parse
from app.weather import (HORIZON_H, LiveForecast, SyntheticForecast, Weather, make_forecast,
                         parse_open_meteo, MARINE_POINTS)
from app.scenarios import make_scenario

ANCHOR = parse("2026-11-12T11:00:00Z")
REAL = datetime(2026, 11, 13, 6, 37, 12, tzinfo=timezone.utc)   # 13 ноя 09:37 МСК — день защиты


def live_state(now=REAL, **kw) -> State:
    return State(clock=Clock(now=lambda: now), forecast=kw.pop("forecast", SyntheticForecast()), **kw)


# ---------------- часы ----------------

def test_clock_floors_to_hour_and_event_ts_is_real():
    c = Clock(now=lambda: REAL)
    assert c.sim_now == datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    assert c.event_ts() == REAL
    fixed = Clock("2026-11-12T11:00:00Z", now=lambda: REAL)        # DEMO_NOW — ручная фиксация
    assert fixed.sim_now == ANCHOR and fixed.event_ts() >= ANCHOR


def test_scenario_relative_to_real_now_same_17_numbers():
    st = live_state()
    now = st.sim_now
    assert now == parse("2026-11-13T06:00:00Z")
    a, b, m = st.sailings["sl-ast-anz-1114"], st.sailings["sl-ast-anz-1116"], st.sailings["sl-mkh-anz-1115"]
    assert hours(now, a["departure"]) == 44 and hours(now, b["departure"]) == 92
    assert hours(now, m["departure"]) == 64 and hours(now, m["cutoff"]) == 60
    assert hours(now, st.shipments["sh-01"]["route"]["legs"][0]["planned_end"]) == 30   # поезд в Астрахани
    assert hours(now, st.meta["pass_valid_until"]) == hours(ANCHOR, "2026-11-29T21:00:00Z")
    # реестр сида сдвинут и пересчитан, пропуска сида действительны
    assert verify_chain(st.ledger) is None
    assert all(st.verify_pass(p["token"])["valid"] for p in st.passes.values())

    out = asyncio.run(st.run_scenario("storm_north"))
    assert hours(now, out["scenario"]["start"]) == 36 and hours(now, out["scenario"]["end"]) == 55
    got = ref.engine_numbers(st, out["alert"])
    assert got == ref.SCENARIO_DOC
    assert [round(st.shipments[s]["risk"]["miss_probability"] * 100) for s in ("sh-01", "sh-02", "sh-03")] == [82, 74, 68]

    acc = asyncio.run(st.accept(out["alert"]["id"], "telegram"))
    assert acc["alert"]["accepted_at"] == "2026-11-13T06:37:12Z"         # «Принято в 09:37»
    assert st.stats()["saved_rub"] == 596640 and verify_chain(st.ledger) is None


def test_reset_moves_with_real_time():
    t = [REAL]
    st = State(clock=Clock(now=lambda: t[0]), forecast=SyntheticForecast())
    first = st.sailings["sl-ast-anz-1114"]["departure"]
    t[0] = REAL + timedelta(hours=5, minutes=50)
    st.reset()
    assert hours(first, st.sailings["sl-ast-anz-1114"]["departure"]) == 6   # 06:00 → 12:00 (12:27 вниз до часа), всё ещё +44 ч


# ---------------- погода ----------------

def om_payload(t0: datetime, wave=lambda node, h: 1.0, n=168):
    times = [(t0 + H(h)).strftime("%Y-%m-%dT%H:%M") for h in range(n)]
    marine = [{"hourly": {"time": times, "wave_height": [wave(node, h) for h in range(n)]}} for node in MARINE_POINTS]
    wind = [{"hourly": {"time": times, "wind_speed_10m": [9.5] * n}} for _ in MARINE_POINTS]
    return marine, wind


def test_live_forecast_cache_and_fallback(tmp_path):
    cache = tmp_path / "weather_cache.json"
    t0 = datetime(2026, 11, 13, 0, 0, tzinfo=timezone.utc)
    fetched = t0 + H(6) + timedelta(minutes=5)
    data = parse_open_meteo(*om_payload(t0, lambda node, h: round(0.5 + h / 100, 2)), fetched)
    fc = LiveForecast(cache, fetch=lambda: data)
    assert asyncio.run(fc.refresh()) is True and json.loads(cache.read_text(encoding="utf-8")) == data
    sim_now = t0 + H(6)
    row = fc.series("makhachkala", sim_now)
    assert len(row) == HORIZON_H and row[0] == 0.56 and row[1] == 0.57      # по времени, а не по индексу
    assert row[-1] == round(0.5 + 167 / 100, 2)                             # за краем — ближайший час
    assert fc.wind("baku", sim_now) == 9.5
    assert fc.meta(sim_now, fetched + timedelta(minutes=10)) == \
        {"updated_at": "2026-11-13T06:05:00Z", "stale": False, "source": "open-meteo"}

    def down():
        raise OSError("нет сети")
    fc2 = LiveForecast(cache, fetch=down)                                   # перезапуск без интернета
    assert asyncio.run(fc2.refresh()) is False
    assert fc2.series("makhachkala", sim_now) == row
    m = fc2.meta(sim_now, fetched + timedelta(minutes=90))
    assert m["source"] == "cache" and m["stale"] is True

    empty = LiveForecast(tmp_path / "none.json", fetch=down)               # ни сети, ни кэша
    assert empty.series("baku", sim_now) == SyntheticForecast().series("baku", sim_now)
    assert empty.meta(sim_now, sim_now)["stale"] is True


def test_land_points_null_fall_back_to_synthetic(tmp_path):
    t0 = datetime(2026, 11, 13, 0, tzinfo=timezone.utc)
    data = parse_open_meteo(*om_payload(t0, lambda node, h: None if node == "olya" else 1.2), t0)
    fc = LiveForecast(tmp_path / "c.json", fetch=lambda: data)
    asyncio.run(fc.refresh())
    assert fc.series("olya", t0) == SyntheticForecast().series("olya", t0)
    assert set(fc.series("baku", t0)) == {1.2}


def test_storm_overlay_on_real_forecast(tmp_path):
    t0 = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
    data = parse_open_meteo(*om_payload(t0, lambda node, h: 1.3), t0)
    fc = LiveForecast(tmp_path / "c.json", fetch=lambda: data)
    asyncio.run(fc.refresh())
    sc = make_scenario("storm_north", t0)
    w = Weather(t0, [sc], fc)
    ast = w.series["astrakhan"]
    assert ast[0] == 1.3 and ast[29] == 1.3                    # до разгона — реальная волна
    assert all(x >= 2.6 for x in ast[36:55]) and max(ast[36:55]) == 3.4
    assert ast[55] < 2.5 and ast[70] == 1.3                    # порт открывается в конце окна
    assert w.series["baku"] == [1.3] * HORIZON_H               # вне шторма — как в прогнозе
    assert w.series["makhachkala"][50] == 2.0                  # горб поверх реальной волны


def test_weather_mode_synthetic_never_touches_network(tmp_path):
    fc = make_forecast("synthetic", tmp_path / "c.json")
    assert isinstance(fc, SyntheticForecast) and asyncio.run(fc.refresh()) is False
    st = State(clock=Clock(now=lambda: REAL), forecast=fc)
    w = st.weather_out()
    assert w["source"] == "cache" and w["stale"] is False


# ---------------- проверка демо ----------------

def test_demo_check_ok_and_read_only(client):
    before = client.get("/api/alerts").json(), client.get("/api/stats").json()
    r = client.get("/api/demo/check").json()
    assert r["ok"] is True and r["problems"] == [] and len(r["checks"]) == 9
    assert all(c["ok"] for c in r["checks"])
    assert (client.get("/api/alerts").json(), client.get("/api/stats").json()) == before


class StormyMakhachkala(SyntheticForecast):
    def series(self, node, sim_now):
        return [2.8] * HORIZON_H if node == "makhachkala" else super().series(node, sim_now)


def test_demo_check_explains_why():
    from app.democheck import run_check
    st = live_state(forecast=StormyMakhachkala())
    r = run_check(st)
    assert r["ok"] is False
    bad = {c["name"] for c in r["checks"] if not c["ok"]}
    assert "recommended" in bad and "risk_sh-01" not in bad
    assert any(p.startswith("волна в Махачкале") and "вариант через Махачкалу отпал" in p for p in r["problems"])
    assert st.alerts == {} and st.scenarios == {}                # живое состояние не тронуто


# ---------------- привязки бота ----------------

def test_users_survive_restart(tmp_path):
    path = tmp_path / "users.json"
    st = live_state(users_path=path)
    st.link_user(555, "Логист")
    st.reset()
    again = live_state(users_path=path)                          # «перезапуск сервера»
    assert again.users == {555: "Логист"}
