"""ice_north — главный сценарий: лёд на Волго-Каспийском канале. Замороженные числа, тексты без
«волна»/«шторм», hazard и Alert.card у каждого пресета, demo/check и четыре условия готовности."""
import asyncio
import json
import re

import pytest

from app import democheck
from app.bot import texts as T
from app.card import build_card
from app.clock import FixedClock
from app.config import SCENARIO_ANCHOR
from app.predictor import CatBoostPredictor
from app.scenarios import PRESETS
from app.state import State

AFFECTED = ("sh-01", "sh-02", "sh-03")
FERRY_M = "sl-mkh-anz-1115"
BANNED = re.compile(r"волн|шторм", re.IGNORECASE)


def ice(st):
    return asyncio.run(st.run_scenario("ice_north"))["alert"]


# ---------------- замороженные числа ----------------

def test_ice_frozen_numbers_formula(st):
    a = ice(st)
    assert a["hazard"] == "ice" and a["source"] == "scenario" and a["id"] == "alert-001"   # создал наблюдатель
    for sid, p in zip(AFFECTED, (0.82, 0.74, 0.68)):   # формула: «порт закрыт» +2,3 к логиту, как шторм 3,4 м
        r = st.shipments[sid]["risk"]
        assert r["miss_probability"] == p and r["level"] == "high"
        assert r["departure_shift_h"] == 18 and r["arrival_delay_h"] == 48
        assert [f["impact_hours"] for f in r["factors"]] == [11, 5, 2]          # закрытие + очередь + таможня
        assert r["factors"][0]["name"] == "ice" and r["factors"][0]["label"] == "Лёд: канал закрыт для проводки"
    assert a["do_nothing"] == {"delay_hours": 48, "loss_rub": 720000}
    mkh = next(o for o in a["options"] if o["id"] == "mkh")
    assert mkh["recommended"] and mkh["delay_vs_plan_h"] == 6
    assert a["totals"] == {"saved_hours": 126, "saved_rub": 596640, "co2_delta_kg": -1824, "co2_delta_pct": -6.9}
    assert sum(st.shipments[s]["weight_t"] for s in AFFECTED) == 120
    assert "123 тыс ₽" in a["text"]                                              # Махачкала: остаточная + доплата


def test_ice_catboost_probabilities():
    st = State(clock=FixedClock(SCENARIO_ANCHOR), predictor=CatBoostPredictor())
    ice(st)
    p = [st.shipments[s]["risk"]["miss_probability"] for s in AFFECTED]
    assert p == [0.99, 0.9, 0.64] and p[0] > p[1] > p[2]                        # лёд: ice=1 от сценария
    assert all(st.shipments[s]["risk"]["departure_shift_h"] == 18 for s in AFFECTED)
    storm_st = State(clock=FixedClock(SCENARIO_ANCHOR), predictor=CatBoostPredictor())
    asyncio.run(storm_st.run_scenario("storm_north"))
    assert [storm_st.shipments[s]["risk"]["miss_probability"] for s in AFFECTED] == [0.82, 0.77, 0.68]


def test_ice_feature_comes_from_scenario_not_calendar(st):
    from app.dispatcher import predict_route
    sh = st.shipments["sh-01"]
    res, _ = predict_route(st, sh, sh["route"])
    assert res.features["ice"] == 0                                               # до сценария льда нет
    ice(st)
    res, _ = predict_route(st, sh, st.alert_internal["alert-001"]["sh-01"]["route_before"])
    assert res.features["ice"] == 1 and res.features["wave_height_m"] < 2.5       # волна реальная


# ---------------- тексты ----------------

def test_ice_texts_have_no_wave_or_storm(st):
    a = ice(st)
    assert a["title"] == "Лёд на Северном Каспии: 3 груза под риском"
    assert a["text"].startswith("⚠️ Лёд на Северном Каспии: 14 ноя 02:00–21:00, лёд на Волго-Каспийском канале, "
                                "раннее ледообразование: канал закрыт для проводки")
    bot = T.alert_message(st, a)
    assert bot.startswith("<b>🧊 Лёд на Северном Каспии: 3 груза под риском</b>")
    labels = [f["label"] for s in AFFECTED for f in st.shipments[s]["risk"]["factors"]]
    for text in (a["title"], a["text"], bot, json.dumps(a["card"], ensure_ascii=False), *labels):
        assert not BANNED.search(text), text


def test_early_ice_only_before_december():
    st = State(clock=FixedClock("2026-12-12T11:00:00Z"))
    a = ice(st)
    assert "раннее ледообразование" not in a["text"] and "лёд на Волго-Каспийском канале:" in a["text"]


def test_storm_is_stress_test(client):
    presets = {p["key"]: p for p in client.get("/api/scenarios/presets").json()}
    assert list(presets)[0] == "ice_north" and presets["ice_north"]["main"] is True
    assert presets["storm_north"]["note"].startswith("Стресс-тест: за 12 месяцев волна у Астрахани не превышала 1,44")
    a = client.post("/api/scenarios", json={"preset": "storm_north"}).json()
    assert a["scenario"]["hazard"] == "storm" and a["alert"]["card"]["note"] == presets["storm_north"]["note"]
    assert client.get("/api/scenarios").json()[0]["hazard"] == "storm"


# ---------------- hazard и card у каждого пресета ----------------

@pytest.mark.parametrize("preset", list(PRESETS))
def test_every_preset_has_hazard_and_card(client, preset):
    out = client.post("/api/scenarios", json={"preset": preset}).json()
    a, sc = out["alert"], out["scenario"]
    assert sc["hazard"] == PRESETS[preset]["hazard"] == a["hazard"]
    c = a["card"]
    assert c["kind"] == a["hazard"] and c["headline"] == sc["title"] and c["decision"] is None
    n = len(a["items"])
    assert c["impact"]["shipments"] == n
    assert c["subtitle"] == (f"{n} груза под риском" if n in (2, 3, 4) else c["subtitle"])
    if n:
        assert f"до {c['impact']['max_risk_pct']}%" in a["text"]
        assert c["route"]["departure"] in a["text"] and c["route"]["from"] in a["text"]
        assert c["impact"]["weight_t"] == sum(client.get(f"/api/shipments/{i['shipment_id']}").json()["weight_t"]
                                              for i in a["items"])
    keys = [m["key"] for m in c["metrics"]]
    assert keys[:1] == {"ice": ["channel"], "storm": ["wave"], "congestion": ["port_load"]}[a["hazard"]]
    rec = next((o for o in a["options"] if o["recommended"] and o["id"] != "wait"), None)
    if rec:
        r = client.post(f"/api/alerts/{a['id']}/accept", json={"via": "telegram"}).json()
        d = r["alert"]["card"]["decision"]
        assert d["status"] == "accepted" and d["title"] == rec["title"].split(" (")[0]
        assert d["detail"] == f"+{int(rec['delay_vs_plan_h'])} ч к плану" and d["via_label"] == "Telegram"
        assert r["alert"]["card"]["impact"] == c["impact"]                       # описание угрозы не меняется


def test_card_decision_on_reject(st):
    a = ice(st)
    out = asyncio.run(st.reject(a["id"]))
    assert out["card"]["decision"] == {"status": "rejected", "title": "Ждать следующий рейс",
                                       "detail": "+48 ч к плану", "via": None, "via_label": None,
                                       "accepted_by_name": None}
    assert build_card(st, st.alerts[a["id"]])["decision"]["status"] == "rejected"


def test_card_example_ice(st):
    a = ice(st)
    c = a["card"]
    assert c["period"] == "14 ноя, 02:00–21:00"
    assert c["metrics"] == [{"key": "channel", "label": "Волго-Каспийский канал", "value": "закрыт для проводки"},
                            {"key": "closure_h", "label": "Закрытие порта", "value": "11 ч"}]
    assert c["route"] == {"sailing_label": "Паром А", "from": "Астрахань", "to": "Энзели",
                          "departure": "14 ноя, 10:00"}
    assert c["impact"] == {"shipments": 3, "weight_t": 120, "max_risk_pct": 82}


# ---------------- demo/check и условия готовности на ice_north ----------------

def test_demo_check_green_on_ice(client):
    out = client.get("/api/demo/check").json()
    assert out["ok"], out["problems"]
    risks = [c["actual"] for c in out["checks"] if c["name"].startswith("risk_sh")]
    assert risks == [82, 74, 68]                                                  # тесты — на формуле


def test_demo_check_green_on_ice_catboost():
    st = State(clock=FixedClock(SCENARIO_ANCHOR), predictor=CatBoostPredictor())
    out = democheck.run_check(st)
    assert out["ok"], out["problems"]
    assert [c["actual"] for c in out["checks"] if c["name"].startswith("risk_sh")] == [99, 90, 64]


def test_ready_one_route_pass_saving_everywhere(client):
    a = client.post("/api/scenarios", json={"preset": "ice_north"}).json()["alert"]
    r = client.post(f"/api/alerts/{a['id']}/accept", json={"via": "web"}).json()
    sh = client.get("/api/shipments/sh-01").json()
    assert sh["route"]["id"] == "r-sh-01-mkh" and sh["pass_id"] == "pass-01-r1"
    assert client.get("/api/stats").json()["saved_rub"] == 596640 == r["alert"]["totals"]["saved_rub"]
    assert client.get("/api/passes", params={"shipment_id": "sh-01"}).json()[0]["id"] == sh["pass_id"]


def test_ready_concurrent_accept_one_decision(st):
    a = ice(st)

    async def both():
        return await asyncio.gather(st.accept(a["id"], "web"), st.accept(a["id"], "telegram"))

    x, y = asyncio.run(both())
    assert sorted([x["already_accepted"], y["already_accepted"]]) == [False, True]
    assert len(st.decisions) == 1 and st.sailings[FERRY_M]["booked_t"] == 760 + 120


def test_ready_pass_failure_visible_retry_idempotent(client):
    client.post("/api/scenarios", json={"preset": "ice_north"})
    client.post("/api/demo/fail_next_pass")
    out = client.post("/api/alerts/alert-001/accept", json={"via": "web"}).json()
    assert {s["id"]: s for s in out["shipments"]}["sh-01"]["pass_state"] == "reissue_pending"
    r1 = client.post("/api/shipments/sh-01/pass/retry").json()
    r2 = client.post("/api/shipments/sh-01/pass/retry").json()
    assert r1["pass"] == r2["pass"] and r1["pass"]["id"] == "pass-01-r1"
    assert client.get("/api/stats").json()["saved_rub"] == 596640 and client.get("/api/stats").json()["decisions"] == 1


def test_ready_reset_reruns_same_numbers(client):
    def run():
        a = client.post("/api/scenarios", json={"preset": "ice_north"}).json()["alert"]
        client.post(f"/api/alerts/{a['id']}/accept", json={"via": "web"})
        return a["totals"], a["card"], client.get("/api/stats").json()

    first = run()
    client.post("/api/demo/reset")
    assert client.get("/api/alerts").json() == [] and client.get("/api/scenarios").json() == []
    assert run() == first


def test_data_sources_ice_block(client):
    out = client.get("/api/data-sources").json()
    ice_src = next(s for s in out["sources"] if s["id"] == "ice")
    assert ice_src["type"] == "modeled" and "живого источника ледовой обстановки нет" in ice_src["note"]
    assert "1,44 м" in out["ice"]["conclusion"] and len(out["ice"]["facts"]) == 4
