"""Задача А: найденные ошибки и дополнения контракта. Каждый тест падал до правки.

А1 — двойное принятие по одним грузам; А2 — проверка тел запросов; А3 — проверка документа;
А4 — событие demo.reset; А5 — права по роли; А6 — список пропусков и accepted_by.
"""
import asyncio
import copy
import time

import pytest

from app import auth as A
from app import config
from app import dispatcher as D
from app import main
from app import tgauth as TG

FERRY_M = "sl-mkh-anz-1115"


def ferry(client, sid):
    return next(s for s in client.get("/api/sailings").json() if s["id"] == sid)


# ---------------- А1: груз входит только в один активный алерт ----------------

def test_storm_then_congestion_accept_both_gives_one_decision(client):
    m0 = ferry(client, FERRY_M)["booked_t"]
    a1 = client.post("/api/scenarios", json={"preset": "storm_north"}).json()["alert"]
    a2 = client.post("/api/scenarios", json={"preset": "congestion_astrakhan"}).json()["alert"]
    assert a1["id"] != a2["id"]
    alerts = {a["id"]: a for a in client.get("/api/alerts").json()}
    assert alerts[a1["id"]]["status"] == "superseded"
    assert a2["id"] in alerts[a1["id"]]["status_note"]
    assert [a["id"] for a in alerts.values() if a["status"] == "new"] == [a2["id"]]

    r1 = client.post(f"/api/alerts/{a1['id']}/accept", json={"via": "web"})
    r2 = client.post(f"/api/alerts/{a2['id']}/accept", json={"via": "telegram"})
    assert r1.status_code == 409 and r1.json()["error"]["code"] == "superseded"
    assert r2.status_code == 200
    stats = client.get("/api/stats").json()
    assert stats["decisions"] == 1 and stats["saved_rub"] == 596640 and stats["saved_hours"] == 126
    assert m0 == 760 and ferry(client, FERRY_M)["booked_t"] == 880


def test_accept_checks_from_route_matches_current(st):
    asyncio.run(st.run_scenario("storm_north"))
    other = copy.deepcopy(st.shipments["sh-01"]["route"])      # маршрут сменился в обход алерта
    other["id"] = "r-sh-01-other"
    st.shipments["sh-01"]["route"] = other
    with pytest.raises(D.ApiError) as e:
        asyncio.run(st.accept("alert-001", "web"))
    assert e.value.status == 409 and e.value.code == "superseded"
    assert st.alerts["alert-001"]["status"] == "superseded" and not st.decisions
    assert "sh-01" in st.alerts["alert-001"]["status_note"]
    assert "alert-002" in st.alerts                             # пересчёт


def test_accept_closes_other_open_alerts_with_same_cargo(st):
    asyncio.run(st.run_scenario("storm_north"))
    twin = copy.deepcopy(st.alerts["alert-001"])                # другой открытый алерт по тем же грузам
    twin["id"] = "alert-twin"
    st.alerts["alert-twin"] = twin
    asyncio.run(st.accept("alert-001", "web"))
    assert st.alerts["alert-twin"]["status"] == "superseded"
    assert st.alerts["alert-twin"]["status_note"] == "по этим грузам решение уже принято"


# ---------------- А2: проверка тел запросов ----------------

GOOD = {"title": "Пшеница", "cargo_type": "grain", "weight_t": 100, "origin": "astrakhan", "destination": "anzali"}


@pytest.mark.parametrize("patch", [
    {"weight_t": -100}, {"weight_t": 0}, {"weight_t": 5001}, {"weight_t": "много"},
    {"title": ""}, {"title": "   "}, {"title": "Я" * 121},
    {"origin": "atlantis"}, {"destination": "atlantis"}, {"destination": "astrakhan"},
    {"cargo_type": "banana"}, {"cargo_type": ""},
])
def test_create_shipment_rejects_bad_body(client, patch):
    n = len(client.get("/api/shipments").json())
    r = client.post("/api/shipments", json={**GOOD, **patch})
    assert r.status_code == 422, (patch, r.text)
    assert len(client.get("/api/shipments").json()) == n


def test_create_shipment_accepts_limits(client):
    assert client.post("/api/shipments", json={**GOOD, "weight_t": 5000, "title": "Я" * 120}).status_code in (200, 422)
    r = client.post("/api/shipments", json=GOOD)
    assert r.status_code == 200 and r.json()["weight_t"] == 100


@pytest.mark.parametrize("path, body", [
    ("/api/ledger/tamper", {"index": -1}),
    ("/api/users/link", {"telegram_id": 1, "name": ""}),
    ("/api/users/link", {"telegram_id": -5, "name": "Анна"}),
    ("/api/passes/verify", {"token": ""}),
    ("/api/shipments/sh-01/reroute", {"route_id": ""}),
    ("/api/auth/register", {"name": " ", "email": "a@b.ru", "password": "secret1", "role": "logist"}),
])
def test_other_bodies_are_checked(client, path, body):
    assert client.post(path, json=body).status_code == 422


def test_accept_rejects_empty_option(client):
    client.post("/api/scenarios", json={"preset": "storm_north"})
    assert client.post("/api/alerts/alert-001/accept", json={"via": "web", "option_id": ""}).status_code == 422


# ---------------- А3: проверка документа ----------------

def draft(client, sid="sh-05"):
    r = client.post("/api/documents", data={"shipment_id": sid}, files={"file": ("inv.jpg", b"x", "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("patch, bad", [
    ({"weight_kg": 0, "value": -1}, {"weight_kg", "value"}),
    ({"weight_kg": None}, {"weight_kg"}),
    ({"weight_kg": -30000}, {"weight_kg"}),
    ({"value": 0}, {"value"}),
    ({"currency": "XXX"}, {"currency"}),
    ({"currency": None}, {"currency"}),
    ({"hs_code": "12"}, {"hs_code"}),
    ({"hs_code": "31021012345"}, {"hs_code"}),
    ({"hs_code": "ABCDEF"}, {"hs_code"}),
    ({"goods": "  "}, {"goods"}),
    ({"origin_country": ""}, {"origin_country"}),
])
def test_confirm_rejects_invalid_document(client, patch, bad):
    doc = draft(client)
    r = client.post(f"/api/documents/{doc['id']}/confirm", json={"fields": {**doc["fields"], **patch}})
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "document_invalid" and bad <= set(err["fields"])
    assert client.get("/api/shipments/sh-05").json()["pass_id"] is None   # пропуск не выпущен


def test_confirm_valid_document_issues_pass(client):
    doc = draft(client)
    r = client.post(f"/api/documents/{doc['id']}/confirm", json={"fields": {**doc["fields"], "currency": "usd"}})
    assert r.status_code == 200, r.text
    assert r.json()["document"]["fields"]["currency"] == "USD" and r.json()["pass"]["status"] == "active"


# ---------------- А4: demo.reset первым событием ----------------

def test_reset_sends_demo_reset_first(client):
    with client.websocket_connect(f"/ws?api_key={main.API_KEY or 'caspian-dev-key'}") as ws:
        assert client.post("/api/demo/reset").status_code == 200
        first = ws.receive_json()
    assert first == {"type": "demo.reset", "payload": None}


def test_miniapp_handles_demo_reset(client):
    assert "demo.reset" in client.get("/tg/app.js").text


# ---------------- А5: права по роли ----------------

@pytest.fixture
def accounts(tmp_path, monkeypatch):
    acc = A.Accounts(tmp_path / "accounts.json")
    monkeypatch.setattr(main, "accounts", acc)
    return acc


def login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": "demo123"})
    assert r.status_code == 200
    return r.json()


def test_permissions_in_login_and_me(client, accounts):
    out = login(client, "expeditor@demo.ru")
    assert out["user"]["permissions"] == []
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {out['token']}"}).json()
    assert me["permissions"] == [] and me["role"] == "expeditor"
    assert login(client, "logist@demo.ru")["user"]["permissions"] == ["run_scenario", "reset_demo", "decide_alert"]


def test_expeditor_cannot_decide_logist_can(client, accounts):
    exp = {"Authorization": f"Bearer {login(client, 'expeditor@demo.ru')['token']}"}
    log = {"Authorization": f"Bearer {login(client, 'logist@demo.ru')['token']}"}
    assert client.post("/api/scenarios", json={"preset": "storm_north"}, headers=exp).json()["error"]["code"] \
        == "forbidden_role"
    client.post("/api/scenarios", json={"preset": "storm_north"}, headers=log)
    for path, body in [("/api/alerts/alert-001/accept", {"via": "web"}), ("/api/alerts/alert-001/reject", None),
                       ("/api/shipments/sh-01/reroute", {"route_id": "r-sh-01-plan"}),
                       ("/api/demo/reset", None), ("/api/demo/fail_next_pass", None)]:
        r = client.post(path, json=body, headers=exp)
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role", path
    assert client.get("/api/demo/check", headers=exp).status_code == 403
    assert client.get("/api/shipments", headers=exp).status_code == 200        # чтение экспедитору доступно
    assert client.get("/api/alerts").json()[0]["status"] == "new"

    r = client.post("/api/alerts/alert-001/accept", json={"via": "web"}, headers=log)
    assert r.status_code == 200
    assert r.json()["alert"]["accepted_by"] == {"name": "Логист (демо)", "role": "logist"}
    assert r.json()["decision"]["accepted_by"] == {"name": "Логист (демо)", "role": "logist"}


def test_key_only_and_bad_bearer(client, accounts):
    client.post("/api/scenarios", json={"preset": "storm_north"})
    r = client.post("/api/alerts/alert-001/accept", json={"via": "web"}, headers={"Authorization": "Bearer junk"})
    assert r.status_code == 401
    r = client.post("/api/alerts/alert-001/accept", json={"via": "web"})            # только X-API-Key
    assert r.status_code == 200 and r.json()["alert"]["accepted_by"] is None


def test_telegram_session_is_logist(client, monkeypatch):
    monkeypatch.setattr(TG, "BOT_TOKEN", "123:TEST")
    import json
    init = TG.sign_init_data({"auth_date": str(int(time.time())), "query_id": "AAH",
                              "user": json.dumps({"id": 42, "first_name": "Анна"})}, "123:TEST")
    tok = client.post("/api/tg/auth", json={"init_data": init}, headers={"X-API-Key": ""}).json()["token"]
    h = {"X-API-Key": "", "Authorization": f"Bearer {tok}"}
    client.post("/api/scenarios", json={"preset": "storm_north"}, headers=h)
    r = client.post("/api/alerts/alert-001/accept", json={"via": "telegram"}, headers=h)
    assert r.status_code == 200 and r.json()["alert"]["accepted_by"] == {"name": "Анна", "role": "logist"}


def test_bot_records_telegram_name(st):
    from app.bot.service import BotService

    async def flush():
        st.drain_events()
    svc = BotService(st, flush)
    asyncio.run(st.run_scenario("storm_north"))
    asyncio.run(svc.accept(st.epoch, "alert-001", by="Анна Петрова"))
    assert st.alerts["alert-001"]["accepted_by"] == {"name": "Анна Петрова", "role": "logist"}
    assert st.decisions[0]["accepted_by"] == {"name": "Анна Петрова", "role": "logist"}


# ---------------- А6: список пропусков ----------------

def test_passes_list_newest_first(client):
    client.post("/api/scenarios", json={"preset": "storm_north"})
    client.post("/api/alerts/alert-001/accept", json={"via": "web"})
    ps = client.get("/api/passes", params={"shipment_id": "sh-01"}).json()
    assert [p["status"] for p in ps] == ["active", "reissued"]
    assert ps[0]["id"] == client.get("/api/shipments/sh-01").json()["pass_id"]
    every = client.get("/api/passes").json()
    assert len(every) == len({p["id"] for p in every}) and {p["shipment_id"] for p in every} >= {"sh-01", "sh-04"}
    assert client.get("/api/passes", params={"shipment_id": "sh-99"}).json() == []
