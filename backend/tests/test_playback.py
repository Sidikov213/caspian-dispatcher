"""Ускоренный просмотр движения: view_now двигает только Shipment.position."""
import asyncio
import copy
import json

import pytest

from app import auth as A
from app import main
from app.clock import FixedClock
from app.config import SCENARIO_ANCHOR
from app.state import State


class FakeTime:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def play(st, speed=600):
    ft = FakeTime()
    st.monotonic = ft
    st.set_playback(speed)
    return ft


def strip(obj):
    """Всё, кроме положения грузов: статусы, риск, ETA, алерты, деньги."""
    obj = copy.deepcopy(obj)
    for sh in obj if isinstance(obj, list) else [obj]:
        if isinstance(sh, dict):
            sh.pop("position", None)
    return obj


def snapshot(st):
    return json.dumps({"shipments": strip(st.shipments_list()), "alerts": list(st.alerts.values()),
                       "stats": st.stats(), "sailings": st.sailings}, sort_keys=True, default=str)


def test_progress_grows_nothing_else_changes(st):
    before = snapshot(st)
    p0 = {s["id"]: s["position"] for s in st.shipments_list() if s["position"]}
    ft = play(st)
    ft.t += 30                                     # 30 с × 600 = 5 ч пути
    assert round(st.view_offset_s()) == 5 * 3600
    p1 = {s["id"]: s["position"] for s in st.shipments_list() if s["position"]}
    for sid in ("sh-01", "sh-02", "sh-03"):
        assert p1[sid]["edge_id"] == p0[sid]["edge_id"]
        assert p1[sid]["progress"] > p0[sid]["progress"], sid
    assert snapshot(st) == before
    assert st.shipments["sh-01"]["position"] == p0["sh-01"]   # хранимое состояние — от sim_now


def test_shipment_never_passes_status_node(st):
    ft = play(st)
    ft.t += 3600                                   # 600 ч пути — далеко за паромом
    by = {s["id"]: s for s in st.shipments_list()}
    ast = st.graph.nodes["astrakhan"]
    for sid in ("sh-01", "sh-02", "sh-03"):        # поезд до Астрахани, дальше — порт
        p = by[sid]["position"]
        assert p["waiting"] and (p["lat"], p["lon"]) == (ast["lat"], ast["lon"]), sid
        assert p["from_node"] == "astrakhan" and p["waiting_label"] == "Ждёт рейс"
        assert by[sid]["display_status"] == "in_transit"
    p4 = by["sh-04"]["position"]                   # Баку → Астара: погранпереход/узел — стоит там
    assert p4["waiting"] and p4["from_node"] == "astara"
    assert by["sh-05"]["position"] is None


def test_reset_turns_playback_off(st):
    ft = play(st)
    ft.t += 60
    assert st.view_offset_s() > 0
    st.reset()
    assert st.playback_out()["speed"] == 0 and st.view_offset_s() == 0


def test_pause_keeps_offset(st):
    ft = play(st)
    ft.t += 12
    st.set_playback(0)
    off = st.view_offset_s()
    ft.t += 100
    assert st.view_offset_s() == off == 7200


def test_ice_north_frozen_numbers_with_playback(st):
    plain = State(clock=FixedClock(SCENARIO_ANCHOR))
    ref = asyncio.run(plain.run_scenario("ice_north"))["alert"]
    ft = play(st)
    ft.t += 20
    a = asyncio.run(st.run_scenario("ice_north"))["alert"]
    ft.t += 20
    assert a["totals"] == ref["totals"] == {"saved_hours": 126, "saved_rub": 596640, "co2_delta_kg": -1824,
                                             "co2_delta_pct": -6.9}
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(ref, sort_keys=True, default=str)
    assert strip(st.shipments_list()) == strip(plain.shipments_list())
    # accept смещение не сбрасывает: значок дальше едет по новому маршруту
    off = st.view_offset_s()
    r = asyncio.run(st.accept(a["id"], "web"))
    assert st.view_offset_s() == off
    sh = st.shipment("sh-01")
    assert sh["position"]["edge_id"] in {leg["edge_id"] for leg in sh["route"]["legs"]}
    assert r["decision"]["items"][0]["saved_rub"] == 298320


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    acc = A.Accounts(tmp_path / "accounts.json")
    monkeypatch.setattr(main, "accounts", acc)
    return acc


def test_api_playback(client, accounts):
    assert client.get("/api/demo/playback").json()["speed"] == 0
    check0 = client.get("/api/demo/check").json()
    r = client.post("/api/demo/playback", json={"speed": 600})
    assert r.status_code == 200 and r.json()["speed"] == 600
    assert client.get("/api/demo/playback").json()["speed"] == 600
    check1 = client.get("/api/demo/check").json()
    assert check1["checks"] == check0["checks"] and check1["ok"] == check0["ok"]
    assert client.post("/api/demo/playback", json={"speed": 5}).status_code == 422
    tok = client.post("/api/auth/login", json={"email": "expeditor@demo.ru", "password": "demo123"}).json()["token"]
    r = client.post("/api/demo/playback", json={"speed": 60}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"
    tok = client.post("/api/auth/login", json={"email": "logist@demo.ru", "password": "demo123"}).json()["token"]
    assert client.post("/api/demo/playback", json={"speed": 60},
                       headers={"Authorization": f"Bearer {tok}"}).json()["speed"] == 60
    client.post("/api/demo/reset")
    assert client.get("/api/demo/playback").json() == {"speed": 0, "offset_h": 0.0,
                                                        "view_now": client.get("/api/demo/playback").json()["view_now"]}
    assert client.get("/api/demo/playback").json()["offset_h"] == 0
