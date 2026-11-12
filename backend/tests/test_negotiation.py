"""Согласование перевозки и «окно спасения» — пресет ice_north_tight.

На пароме М из Махачкалы свободно 80 т, грузов на 120 т. Проверяется: кто получает место (правило
«максимум спасённых груз-часов при ограничении по весу»), шаги согласования с отказом и встречным
предложением, запись шагов в журнал, срок решения decide_by и 409 после него, а также то, что
главный сценарий ice_north и demo/check не изменились.
"""
import asyncio
import hashlib
import json

import pytest

from app import dispatcher as D
from app import negotiation as N
from app.ledger import verify_chain
from app.util import H, iso, parse
from conftest import DEMO_NOW as ANCHOR

DEMO_NOW = parse(ANCHOR)

SAILING_M = "sl-mkh-anz-1115"
TIGHT = "ice_north_tight"


def run(st, preset=TIGHT):
    return asyncio.run(st.run_scenario(preset))["alert"]


def by_ship(alert):
    return {i["shipment_id"]: i for i in alert["items"]}


# ---------------- выбор грузов при 80 т ----------------

def test_tight_leaves_80t_on_ferry_m(st):
    run(st)
    s = st.sailings[SAILING_M]
    assert s["capacity_t"] - s["booked_t"] == 80


def test_selection_at_80t(st):
    a = run(st)
    alloc = st.alert_alloc[a["id"]]
    assert alloc["selected"] == ["sh-01", "sh-03"] and alloc["left"] == ["sh-02"]
    assert (alloc["free_t"], alloc["requested_t"], alloc["selected_t"]) == (80, 120, 80)
    items = by_ship(a)
    assert items["sh-01"]["sailing_id"] == items["sh-03"]["sailing_id"] == SAILING_M
    assert items["sh-02"]["sailing_id"] != SAILING_M
    for sid in ("sh-01", "sh-03"):   # через Махачкалу — те же числа, что в главном сценарии
        assert items[sid]["delay_vs_plan_h"] == 6 and items[sid]["saved_hours"] == 42
    assert (items["sh-01"]["saved_rub"], items["sh-03"]["saved_rub"]) == (298320, 99440)
    on_ferry = sum(st.shipments[i["shipment_id"]]["weight_t"] for i in a["items"] if i["sailing_id"] == SAILING_M)
    assert on_ferry == 80


def test_recommended_plan_numbers(st):
    """№02 места не хватило — ему лучший из оставшихся обходов: западная ветка, +13 ч."""
    a = run(st)
    items = by_ship(a)
    assert items["sh-02"]["action"] == "reroute" and items["sh-02"]["to_route"]["branch"] == "west"
    assert items["sh-02"]["delay_vs_plan_h"] == 13 and items["sh-02"]["saved_hours"] == 35
    assert a["totals"]["saved_hours"] == 119 and a["totals"]["saved_rub"] == 532192
    assert a["do_nothing"] == {"delay_hours": 48, "loss_rub": 720000}
    rec = a["options"][0]
    assert rec["recommended"] and rec["id"] == "best"
    assert rec["title"] == "Через Махачкалу — №01 и №03, по западной ветке через Самур и Астару — №02"
    assert a["port_load"] == {"node_id": "makhachkala", "before": 0.64, "after": 0.68}   # только 80 т парома


def test_option_mkh_keeps_02_waiting(st):
    """Второй вариант — только Махачкала: №01 и №03 на пароме М, №02 ждёт рейс Б."""
    a = run(st)
    mkh = next(o for o in a["options"] if o["id"] == "mkh")
    assert mkh["title"] == "Через Махачкалу — №01 и №03, ждать рейс Б — №02"
    assert (mkh["saved_hours"], mkh["saved_rub"], mkh["delay_vs_plan_h"]) == (84, 397760, 48)
    items = {i["shipment_id"]: i for i in st.alert_options[a["id"]]["mkh"]["items"]}
    assert items["sh-02"]["action"] == "wait" and items["sh-02"]["sailing_id"] == "sl-ast-anz-1116"
    assert [o["id"] for o in a["options"]] == ["best", "mkh", "wait"]


def test_leftover_wait_setting(st, monkeypatch):
    """Настройка пресета leftover: wait — кому не хватило места, ждёт рейс Б и в рекомендованном варианте."""
    from app import scenarios
    monkeypatch.setitem(scenarios.PRESETS[TIGHT], "leftover", "wait")
    a = run(st)
    items = by_ship(a)
    assert items["sh-02"]["action"] == "wait" and items["sh-01"]["sailing_id"] == SAILING_M
    assert a["totals"]["saved_hours"] == 84 and a["totals"]["saved_rub"] == 397760


def test_rule_prefers_more_saved_hours(st):
    """Правило выбора: из наборов, что помещаются, — максимум спасённых груз-часов, затем ₽."""
    for s in st.sailings.values():
        if s["id"] == SAILING_M:
            s["booked_t"] = s["capacity_t"] - 60   # 60 т: №01 один или №02 + №03 — два груза спасают больше
    st.scenarios.clear()
    from app import scenarios
    sc = scenarios.make_scenario(TIGHT, st.sim_now)
    sc["_sailing_free_t"] = {}
    st.scenarios[TIGHT] = sc
    st.weather = st.make_weather()
    a = D.watch(st)[0]
    assert st.alert_alloc[a["id"]]["selected"] == ["sh-02", "sh-03"]


# ---------------- шаги согласования ----------------

def test_steps_reject_counter_ok(st):
    a = run(st)
    steps = a["negotiation"]
    assert [(s["actor"], s["result"]) for s in steps[:3]] == [("ferry", "reject"), ("ferry", "counter"), ("ferry", "ok")]
    assert "120 т" in steps[0]["action"] and "Свободно 80 т из нужных 120 т" in steps[0]["detail"]
    assert "80 т" in steps[1]["action"] and "№01 Зерно 60 т и №03 Оборудование 20 т" in steps[1]["detail"]
    assert steps[2]["action"] == "Бронь 80 т: №01 и №03"
    assert {s["actor"] for s in steps} == set(N.ACTORS)
    assert all(s["result"] == "ok" for s in steps[2:]) and N.agreed(steps)
    assert len(steps) == 7 and "за 7 шагов" in a["text"]
    # названия в шагах железной дороги — из графа, по реальному маршруту груза
    assert steps[5]["action"] == "Переадресация №01 и №03: Астрахань → Махачкала"
    assert steps[6]["action"] == "Переадресация №02 на западную ветку (Самур — Астара)"
    assert steps[6]["detail"] == ("Маршрут Астрахань → Махачкала → Самур → Баку → Астара: "
                                  "отправление 13 ноя, 20:00, прибытие +13 ч к плану")
    legs = {i["shipment_id"]: i["to_route"]["legs"] for i in a["items"]}
    assert [leg["edge_id"] for leg in legs["sh-01"][1:3]] == ["e-astrakhan-makhachkala", "e-makhachkala-anzali"]
    assert [leg["edge_id"] for leg in legs["sh-02"][1:6]] == [
        "e-astrakhan-makhachkala", "e-makhachkala-samur", "e-samur-baku", "e-baku-astara", "e-astara-rasht"]
    for s in steps:
        assert set(s) == {"actor", "action", "result", "detail", "ts", "block_index"} and s["detail"]


def test_steps_are_deterministic(st):
    first = run(st)["negotiation"]
    st.reset()
    assert run(st)["negotiation"] == first


def test_each_step_is_a_ledger_block(st):
    before = len(st.ledger)
    a = run(st)
    steps = a["negotiation"]
    blocks = st.ledger[before:]
    assert len(blocks) == len(steps) and verify_chain(st.ledger) is None
    for n, (s, b) in enumerate(zip(steps, blocks), 1):
        assert b["event"] == "negotiation" and b["index"] == s["block_index"]
        assert (b["alert_id"], b["actor"], b["result"]) == (a["id"], s["actor"], s["result"])
        payload = {"alert_id": a["id"], "n": n, **{k: s[k] for k in ("actor", "action", "result", "detail", "ts")}}
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        assert b["doc_hash"] == hashlib.sha256(raw.encode("utf-8")).hexdigest()   # содержимое шага под хэшем


def test_tampered_step_breaks_chain(st):
    a = run(st)
    idx = a["negotiation"][1]["block_index"]
    st.tamper(idx)
    assert st.ledger_verify() == {"valid": False, "broken_at": idx}


def test_customs_model_rejects_without_valid_pass(st):
    """Модель таможни — настоящая проверка: отозванный пропуск → отказ, согласование не завершено."""
    st.passes[st.shipments["sh-03"]["pass_id"]]["status"] = "revoked"
    a = run(st)
    customs = next(s for s in a["negotiation"] if s["actor"] == "customs")
    assert customs["result"] == "reject" and "№03" in customs["detail"]
    assert not N.agreed(a["negotiation"]) and "не завершено" in a["text"]


# ---------------- decide_by ----------------

def test_decide_by_is_last_train_to_makhachkala(st):
    a = run(st)
    # поезд Астрахань → Махачкала 13 ноя 20:00 МСК = sim_now + 30 ч: следующий к окончанию приёма не успевает
    assert a["decide_by"] == iso(DEMO_NOW + H(30)) == "2026-11-13T17:00:00Z"
    opts = {o["id"]: o for o in a["options"]}
    assert opts["best"]["decide_by"] == opts["mkh"]["decide_by"] == a["decide_by"]
    assert opts["wait"]["decide_by"] is None and all(o["available"] for o in a["options"])
    assert "Решение можно принять до 13 ноя, 20:00." in a["text"]


def test_accept_before_deadline(st):
    a = run(st)
    st.clock.set(DEMO_NOW + H(29))
    out = asyncio.run(st.accept(a["id"], "web"))
    assert out["alert"]["status"] == "accepted" and len(out["shipments"]) == 3
    s = st.sailings[SAILING_M]
    assert s["capacity_t"] - s["booked_t"] == 0
    assert st.stats()["saved_hours"] == 119 and st.stats()["saved_rub"] == 532192
    assert st.shipments["sh-02"]["route"]["branch"] == "west" and verify_chain(st.ledger) is None
    assert [b["event"] for b in out["blocks"]] == ["reissued"] * 3


def test_accept_after_deadline_409(st):
    a = run(st)
    st.clock.set(DEMO_NOW + H(30) + H(1 / 60))
    for option in (None, "mkh"):
        with pytest.raises(D.ApiError) as e:
            asyncio.run(st.accept(a["id"], "web", option))
        assert e.value.status == 409 and e.value.code == "decide_by_passed"
    alert = st.alerts_list()[0]
    assert alert["status"] == "new"
    assert {o["id"]: o["available"] for o in alert["options"]} == {"best": False, "mkh": False, "wait": True}
    assert not st.decisions and st.sailings[SAILING_M]["capacity_t"] - st.sailings[SAILING_M]["booked_t"] == 80
    assert asyncio.run(st.reject(a["id"]))["status"] == "rejected"   # «ждать» остаётся доступным


def test_api_tight_flow(client):
    presets = {p["key"]: p for p in client.get("/api/scenarios/presets").json()}
    assert presets[TIGHT]["title"] == "Лёд, мест мало" and presets[TIGHT]["main"] is False
    r = client.post("/api/scenarios", json={"preset": TIGHT})
    assert r.status_code == 200
    a = r.json()["alert"]
    assert len(a["negotiation"]) == 7 and a["decide_by"] == "2026-11-13T17:00:00Z"
    assert client.get("/api/ledger/verify").json() == {"valid": True, "broken_at": None}
    neg = [b for b in client.get("/api/ledger").json() if b["event"] == "negotiation"]
    assert len(neg) == 7 and neg[0]["actor"] == "ferry" and neg[0]["result"] == "reject"
    from app import main
    main.state.clock.set(DEMO_NOW + H(31))
    r = client.post(f"/api/alerts/{a['id']}/accept", json={"via": "web"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "decide_by_passed"
    assert client.get("/api/alerts").json()[0]["options"][0]["available"] is False
    main.state.clock.set(DEMO_NOW + H(1))
    client.post("/api/demo/reset")
    assert len(client.get("/api/ledger").json()) == 4 and client.get("/api/alerts").json() == []


# ---------------- главный сценарий не изменился ----------------

def test_ice_north_has_no_new_fields_and_same_numbers(client):
    a = client.post("/api/scenarios", json={"preset": "ice_north"}).json()["alert"]
    assert "negotiation" not in a and "decide_by" not in a
    assert all("available" not in o and "decide_by" not in o for o in a["options"])
    assert [o["id"] for o in a["options"]] == ["mkh", "west", "wait"]
    assert a["totals"] == {"saved_hours": 126, "saved_rub": 596640, "co2_delta_kg": -1824.0, "co2_delta_pct": -6.9}
    assert a["port_load"] == {"node_id": "makhachkala", "before": 0.64, "after": 0.7}
    assert a["options"][0]["title"] == "Через Махачкалу (паром М, 15 ноя, 06:00)"
    ledger = client.get("/api/ledger").json()
    assert len(ledger) == 4 and all(set(b) == {"index", "ts", "event", "shipment_id", "checkpoint_node",
                                               "doc_hash", "prev_hash", "hash"} for b in ledger)
    from app import main
    main.state.clock.set(DEMO_NOW + H(40))   # срока решения у главного сценария нет
    out = client.post(f"/api/alerts/{a['id']}/accept", json={"via": "web"}).json()
    assert out["alert"]["status"] == "accepted" and out["decision"]["items"][0]["saved_rub"] in (298320, 198880, 99440)
    assert client.get("/api/stats").json()["saved_rub"] == 596640
    assert len(client.get("/api/ledger").json()) == 4 + 3
    main.state.clock.set(DEMO_NOW)


def test_demo_check_unchanged(client):
    client.post("/api/scenarios", json={"preset": TIGHT})   # новый пресет на живом состоянии проверку не трогает
    res = client.get("/api/demo/check").json()
    assert res["ok"] and res["problems"] == []
    got = {c["name"]: c["actual"] for c in res["checks"]}
    assert (got["risk_sh-01"], got["risk_sh-02"], got["risk_sh-03"]) == (82, 74, 68)
    assert (got["departure_shift_h"], got["do_nothing_h"], got["mkh_delay_h"]) == (18, 48, 6)
    assert (got["saved_hours"], got["saved_rub"], got["recommended"]) == (126, 596640, "mkh")


def test_tight_after_ice_north_replaces_alert(st):
    """Пресет сменили, не сбрасывая: прежний алерт закрыт, новый — с согласованием."""
    old = run(st, "ice_north")
    new = run(st)
    assert st.alerts[old["id"]]["status"] == "superseded" and new["id"] != old["id"]
    assert new["status"] == "new" and len(new["negotiation"]) == 7


def test_tight_after_accepted_ice_north_does_not_break(st):
    """Порядок проверки на проде без сброса между пресетами: грузы уже перестроены — под риском никого."""
    old = run(st, "ice_north")
    asyncio.run(st.accept(old["id"], "web"))
    new = run(st)
    assert new["items"] == [] and "negotiation" not in new
    assert st.stats()["saved_rub"] == 596640 and verify_chain(st.ledger) is None
