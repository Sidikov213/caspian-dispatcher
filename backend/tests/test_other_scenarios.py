"""Устаревшее предложение (409 superseded), алерт без предложения, storm_full, congestion_astrakhan."""
import asyncio

import pytest

from app.errors import ApiError

FERRY_M = "sl-mkh-anz-1115"


def run(st, key):
    return asyncio.run(st.run_scenario(key))["alert"]


# ---------------- тест 4: места уже нет → superseded и пересчёт ----------------

def test_accept_superseded_when_seat_taken(st):
    run(st, "storm_north")
    st.sailings[FERRY_M]["booked_t"] = 1150          # кто-то занял место: свободно 50 т из 120
    with pytest.raises(ApiError) as e:
        asyncio.run(st.accept("alert-001", "web"))
    assert e.value.status == 409 and e.value.code == "superseded"
    assert st.alerts["alert-001"]["status"] == "superseded"
    assert not st.decisions and st.sailings[FERRY_M]["booked_t"] == 1150   # ничего не зарезервировано
    new = st.alerts["alert-002"]
    assert new["status"] == "new"
    used_m = sum(st.shipments[i["shipment_id"]]["weight_t"] for i in new["items"] if i["sailing_id"] == FERRY_M)
    assert used_m <= 50
    assert {i["to_route"]["branch"] for i in new["items"] if i["sailing_id"] != FERRY_M} == {"west"}
    out = asyncio.run(st.accept("alert-002", "web"))
    assert len(st.decisions) == 1 and st.sailings[FERRY_M]["booked_t"] == 1150 + used_m
    assert out["decision"]["alert_id"] == "alert-002"


def test_superseded_over_http(client):
    client.post("/api/scenarios", json={"preset": "storm_north"})
    from app import main
    main.state.sailings[FERRY_M]["booked_t"] = 1190
    r = client.post("/api/alerts/alert-001/accept", json={"via": "web"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "superseded"
    assert [a["status"] for a in client.get("/api/alerts").json()] == ["superseded", "new"]


# ---------------- тест 5: допустимого маршрута нет → алерт без предложения ----------------

def test_no_feasible_route_gives_wait_alert(st):
    for s in st.sailings.values():                   # паромы из Махачкалы отменены
        if s["from"] == "makhachkala":
            s["status"] = "cancelled"
    st.graph.G.remove_edge("samur", "baku")          # и западная ветка недоступна
    a = run(st, "storm_north")
    assert [i["action"] for i in a["items"]] == ["wait"] * 3
    assert all(i["to_route"] is None and i["sailing_id"] == "sl-ast-anz-1116" for i in a["items"])
    assert all(i["delay_vs_plan_h"] == 48 and i["saved_rub"] == 0 for i in a["items"])
    assert a["totals"]["saved_rub"] == 0 and a["port_load"] is None
    assert "Обхода нет" in a["text"] and "ждать рейс Б" in a["text"]
    out = asyncio.run(st.accept(a["id"], "web"))
    assert out["decision"]["items"] == [] and st.stats()["saved_rub"] == 0


# ---------------- остальные пресеты ----------------

def test_storm_full_goes_west(st):
    a = run(st, "storm_full")
    assert [i["to_route"]["id"] for i in a["items"]] == ["r-sh-01-west", "r-sh-02-west", "r-sh-03-west"]
    assert all(i["delay_vs_plan_h"] == 13 and i["saved_hours"] == 35 for i in a["items"])
    assert "По западной ветке через Самур и Астару" in a["text"]
    out = asyncio.run(st.accept(a["id"], "telegram"))
    assert {b["checkpoint_node"] for b in out["blocks"]} == {"samur"}


def test_congestion_hits_only_late_cargo(st):
    a = run(st, "congestion_astrakhan")
    assert [i["shipment_id"] for i in a["items"]] == ["sh-01", "sh-02"]   # №03 успевает к приёму
    assert st.shipments["sh-03"]["risk"]["departure_shift_h"] == 0
    assert all(i["sailing_id"] == FERRY_M for i in a["items"])
    assert a["totals"]["saved_rub"] == 298320 + 198880


def test_same_preset_twice_returns_same_alert(client):
    a = client.post("/api/scenarios", json={"preset": "storm_north"}).json()
    b = client.post("/api/scenarios", json={"preset": "storm_north"}).json()
    assert a == b and len(client.get("/api/alerts").json()) == 1


def test_stacked_scenarios_extrapolate_schedule(st):
    """Затор поверх шторма: рейса Б не хватает — расписание продлевается, обход по суше выигрывает."""
    run(st, "storm_full")
    a = run(st, "congestion_astrakhan")
    assert all(i["action"] == "reroute" and i["to_route"]["branch"] == "west" for i in a["items"])
    assert a["do_nothing"]["delay_hours"] > 48
    assert all(i["saved_hours"] > 0 and i["saved_rub"] > 0 for i in a["items"])


# ---------------- варианты решения: Alert.options и option_id ----------------

def test_alert_options_and_accept_other_option(client):
    a = client.post("/api/scenarios", json={"preset": "storm_north"}).json()["alert"]
    assert [(o["id"], o["recommended"]) for o in a["options"]] == [("mkh", True), ("west", False), ("wait", False)]
    assert a["options"][0]["saved_rub"] == a["totals"]["saved_rub"] == 596640
    assert a["options"][2]["title"] == "Ждать рейс Б" and a["options"][2]["delay_vs_plan_h"] == 48
    r = client.post("/api/alerts/alert-001/accept", json={"via": "web", "option_id": "wait"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "use_reject"
    r = client.post("/api/alerts/alert-001/accept", json={"via": "web", "option_id": "nope"})
    assert r.status_code == 404
    out = client.post("/api/alerts/alert-001/accept", json={"via": "web", "option_id": "west"}).json()
    assert {s["route"]["id"].rsplit("-", 1)[-1] for s in out["shipments"]} == {"west"}
    assert out["alert"]["totals"]["saved_rub"] == sum(i["saved_rub"] for i in out["decision"]["items"])
    assert [o["id"] for o in out["alert"]["options"] if o["recommended"]] == ["west"]
    assert {b["checkpoint_node"] for b in out["blocks"]} == {"samur"}
    sail = {s["id"]: s for s in client.get("/api/sailings").json()}
    assert sail[FERRY_M]["booked_t"] == 760                    # паром М не бронировали
    assert client.get("/api/stats").json()["saved_rub"] == out["alert"]["totals"]["saved_rub"]


def test_accept_without_option_is_recommended(client):
    client.post("/api/scenarios", json={"preset": "storm_north"})
    out = client.post("/api/alerts/alert-001/accept", json={"via": "telegram"}).json()
    assert out["alert"]["totals"]["saved_rub"] == 596640
