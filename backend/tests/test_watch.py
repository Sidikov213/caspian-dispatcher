"""Наблюдатель угроз (алерт без сценария, без дублей, снятие угрозы) и снятие брони при смене рейса."""
import asyncio

import pytest

from app import dispatcher as D
from app.bot import texts as T
from app.clock import FixedClock
from app.config import SCENARIO_ANCHOR
from app.democheck import run_check
from app.predictor import FormulaPredictor
from app.state import State
from app.weather import HORIZON_H, SyntheticForecast, baseline

FERRY_A, FERRY_M = "sl-ast-anz-1114", "sl-mkh-anz-1115"   # паром А: +44 ч из Астрахани
AFFECTED = ("sh-01", "sh-02", "sh-03")


class StormForecast(SyntheticForecast):
    """Синтетический прогноз с настоящим штормом у Астрахани в часы [start, end): волна `peak`."""
    def __init__(self, start=38, end=50, peak=3.0):
        self.storm = (start, end, peak)

    def series(self, node, sim_now):
        row = [baseline(node, h) for h in range(HORIZON_H)]
        if self.storm and node == "astrakhan":
            s, e, peak = self.storm
            for h in range(s, e):
                row[h] = peak
        return row


def make(forecast=None) -> State:
    return State(clock=FixedClock(SCENARIO_ANCHOR), predictor=FormulaPredictor(),
                 forecast=forecast or SyntheticForecast())


def new_alerts(st):
    return [a for a in st.alerts.values() if a["status"] == "new"]


# ---------------- 1. бронь снимается всегда, когда груз уходит с рейса ----------------

def test_manual_reroute_to_land_releases_old_booking():
    st = make()
    assert st.sailings[FERRY_A]["booked_t"] == 1310
    west = next(a["route"]["id"] for a in st.alternatives("sh-01") if a["route"]["id"].endswith("-west"))
    asyncio.run(st.reroute("sh-01", west))           # 60 т уходят на западную ветку, парома нет
    assert D.first_ferry(st, st.shipments["sh-01"]["route"]) is None
    assert st.sailings[FERRY_A]["booked_t"] == 1250
    assert st.sailings[FERRY_M]["booked_t"] == 760    # чужие рейсы не тронуты


def test_accept_west_and_reject_bookings():
    st = make()
    asyncio.run(st.run_scenario("storm_north"))
    asyncio.run(st.accept("alert-001", "web", "west"))   # 120 т по суше
    assert st.sailings[FERRY_A]["booked_t"] == 1310 - 120 and st.sailings[FERRY_M]["booked_t"] == 760

    st = make()
    asyncio.run(st.run_scenario("storm_north"))
    asyncio.run(st.reject("alert-001"))                  # «ждать»: грузы остаются на рейсе А
    assert st.sailings[FERRY_A]["booked_t"] == 1310 and st.sailings[FERRY_M]["booked_t"] == 760


# ---------------- 2. наблюдатель ----------------

def test_alert_from_forecast_without_scenario():
    st = make(StormForecast())                           # шторм в прогнозе уже при старте
    alerts = list(st.alerts.values())
    assert len(alerts) == 1 and not st.scenarios
    a = alerts[0]
    assert a["source"] == "forecast" and a["status"] == "new"
    assert a["scenario_id"] == f"fc-astrakhan-{FERRY_A}" and a["title"].startswith("Шторм у порта Астрахань")
    assert a["starts_in_h"] == 38
    assert [i["shipment_id"] for i in a["items"]] == list(AFFECTED)
    assert a["text"].startswith("⚠️ Шторм у порта Астрахань") and "волна до 3,0 м" in a["text"]
    # без затора и таможни сценария сдвиг меньше (+7 ч), но при отмене рейса А — те же +48 ч
    assert all(st.shipments[s]["risk"]["departure_shift_h"] == 7 for s in AFFECTED)
    assert all(st.shipments[s]["risk"]["arrival_delay_h"] == 48 for s in AFFECTED)
    assert asyncio.run(st.accept(a["id"], "web"))["decision"]["alert_id"] == a["id"]


def test_no_duplicates_and_significant_change():
    fc = StormForecast()
    st = make(fc)
    st.on_forecast_updated()
    st.on_forecast_updated()
    fc.storm = (38, 50, 3.2)                           # пик +0,2 м — несущественно
    st.on_forecast_updated()
    assert len(st.alerts) == 1 and len(new_alerts(st)) == 1

    fc.storm = (33, 50, 3.0)                           # шторм начнётся на 5 ч раньше — существенно
    st.on_forecast_updated()
    old, new = st.alerts["alert-001"], st.alerts["alert-002"]
    assert old["status"] == "superseded" and "прогноз изменился" in old["status_note"]
    assert new["status"] == "new" and new["starts_in_h"] == 33 and len(new_alerts(st)) == 1


def test_threat_gone_closes_alert():
    fc = StormForecast()
    st = make(fc)
    fc.storm = None                                    # прогноз успокоился до решения
    st.on_forecast_updated()
    a = st.alerts["alert-001"]
    assert a["status"] == "superseded" and a["status_note"] == "угроза снята"
    assert len(st.alerts) == 1
    assert all(st.shipments[s]["display_status"] == "in_transit" for s in AFFECTED)
    assert all(st.shipments[s]["risk"]["departure_shift_h"] == 0 for s in AFFECTED)   # прогноз снова спокойный
    assert all(not any(l["status"] == "blocked" for l in st.shipments[s]["route"]["legs"]) for s in AFFECTED)
    assert T.alert_suffix(a) == "✅ Угроза снята — решение не нужно"
    with pytest.raises(Exception):
        asyncio.run(st.accept("alert-001", "web"))


def test_decided_threat_is_not_realerted():
    st = make(StormForecast())
    asyncio.run(st.reject("alert-001"))
    st.on_forecast_updated()
    assert len(st.alerts) == 1                         # та же угроза — решение уже принято


def test_scenario_over_forecast_threat_keeps_numbers():
    st = make(StormForecast())
    out = asyncio.run(st.run_scenario("storm_north"))
    old = st.alerts["alert-001"]
    assert old["source"] == "forecast" and old["status"] == "superseded"
    a = out["alert"]
    assert a["source"] == "scenario" and a["status"] == "new" and a["starts_in_h"] == 36
    assert a["totals"]["saved_hours"] == 126 and a["totals"]["saved_rub"] == 596640
    assert [i["shipment_id"] for i in a["items"]] == list(AFFECTED)


def test_scenario_alert_marked_scenario_and_same_numbers():
    st = make()
    a = asyncio.run(st.run_scenario("storm_north"))["alert"]
    assert a["id"] == "alert-001" and a["source"] == "scenario" and a["status_note"] is None
    assert a["totals"]["saved_rub"] == 596640
    st.on_forecast_updated()                           # обновление погоды при активном сценарии — без дублей
    assert len(st.alerts) == 1


# ---------------- 3. проверка демо ----------------

def test_demo_check_reports_forecast_alert():
    quiet = next(c for c in run_check(make())["checks"] if c["name"] == "forecast_quiet")
    assert quiet["ok"] and quiet["actual"] == "0 алертов по прогнозу"
    res = run_check(make(StormForecast()))
    quiet = next(c for c in res["checks"] if c["name"] == "forecast_quiet")
    assert quiet["ok"] and quiet["actual"].startswith("1 по прогнозу: Астрахань: волна до 3,0 м")
    assert "рейс А" in quiet["actual"] or "Паром А" in quiet["actual"] or "А (" in quiet["actual"]
