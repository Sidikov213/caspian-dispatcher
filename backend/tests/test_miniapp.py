"""Telegram Mini App: проверка initData, сессионный токен как второй способ авторизации, ручной груз
в сценарии без переполнения парома, статика /tg/, кнопки и тексты бота."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import config, main
from app import tgauth as TG
from app.bot import keyboards as K
from app.bot import texts as T
from app.errors import ApiError

BOT = "123456:TEST-TOKEN"
USER = {"id": 100000001, "first_name": "Анна", "username": "anna"}
FERRY_A, FERRY_M = "sl-ast-anz-1114", "sl-mkh-anz-1115"


def init_data(auth_date=None, user=USER, token=BOT) -> str:
    return TG.sign_init_data({"auth_date": str(int(auth_date or time.time())), "query_id": "AAH",
                              "user": json.dumps(user, ensure_ascii=False)}, token)


@pytest.fixture
def bot_token(monkeypatch):
    monkeypatch.setattr(TG, "BOT_TOKEN", BOT)


# ---------------- initData ----------------

def test_valid_init_data(bot_token):
    assert TG.verify_init_data(init_data())["id"] == USER["id"]


def test_forged_init_data(bot_token):
    with pytest.raises(ApiError) as e:
        TG.verify_init_data(init_data(token="999:OTHER"))          # подписано чужим токеном
    assert e.value.status == 401 and e.value.code == "invalid_init_data"
    good = init_data()
    with pytest.raises(ApiError) as e:
        TG.verify_init_data(good.replace("100000001", "100000002"))   # подменили пользователя
    assert e.value.code == "invalid_init_data"


def test_expired_init_data(bot_token):
    with pytest.raises(ApiError) as e:
        TG.verify_init_data(init_data(auth_date=time.time() - 25 * 3600))
    assert e.value.status == 401 and e.value.code == "init_data_expired"
    assert TG.verify_init_data(init_data(auth_date=time.time() - 23 * 3600))["id"] == USER["id"]


def test_no_bot_token_means_unavailable(monkeypatch):
    monkeypatch.setattr(TG, "BOT_TOKEN", "")
    with pytest.raises(ApiError) as e:
        TG.verify_init_data(init_data())
    assert e.value.status == 503


# ---------------- сессия как второй способ авторизации ----------------

def session(client) -> dict:
    r = client.post("/api/tg/auth", json={"init_data": init_data()}, headers={"X-API-Key": ""})
    assert r.status_code == 200, r.text
    return r.json()


def test_tg_auth_and_session_token(client, bot_token):
    out = session(client)
    assert out["user"] == {"id": USER["id"], "name": "Анна", "username": "anna"}
    assert out["company"] == config.DEMO_COMPANY
    bearer = {"X-API-Key": "", "Authorization": f"Bearer {out['token']}"}
    assert client.get("/api/shipments", headers=bearer).status_code == 200
    assert client.post("/api/scenarios", headers=bearer, json={"preset": "storm_north"}).status_code == 200
    assert client.get("/api/shipments", headers={"X-API-Key": ""}).status_code == 401
    assert client.get("/api/shipments", headers={"X-API-Key": "", "Authorization": "Bearer garbage"}).status_code == 401
    bad = client.post("/api/tg/auth", json={"init_data": init_data(token="999:OTHER")}, headers={"X-API-Key": ""})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_init_data"


def test_site_login_token_does_not_open_api(client, bot_token, tmp_path, monkeypatch):
    from app import auth as A
    monkeypatch.setattr(main, "accounts", A.Accounts(tmp_path / "acc.json"))
    tok = client.post("/api/auth/login", json={"email": "logist@demo.ru", "password": "demo123"}).json()["token"]
    assert client.get("/api/shipments", headers={"X-API-Key": "", "Authorization": f"Bearer {tok}"}).status_code == 401


def test_websocket_accepts_session_token(client, bot_token):
    from starlette.websockets import WebSocketDisconnect
    from app.main import hub
    tok = session(client)["token"]
    with client.websocket_connect(f"/ws?token={tok}", headers={"X-API-Key": ""}):
        assert len(hub.clients) == 1                     # соединение принято и зарегистрировано
    with pytest.raises(WebSocketDisconnect):             # чужой токен — сервер закрывает до accept
        with client.websocket_connect("/ws?token=garbage", headers={"X-API-Key": ""}) as ws:
            ws.receive_text()


def test_miniapp_static_and_gate(client):
    assert client.get("/tg", follow_redirects=False).status_code in (301, 302, 307, 308)
    r = client.get("/tg/", headers={"X-API-Key": ""})
    assert r.status_code == 200 and "Откройте через бота" in r.text and "telegram-web-app.js" in r.text
    js = client.get("/tg/app.js").text
    assert "X-API-Key" not in js and "caspian-dev-key" not in js        # ключа API в мини-приложении нет


# ---------------- ручной груз ----------------

def test_manual_shipment_joins_storm_without_overbooking(client):
    a_before = client.get("/api/sailings").json()
    booked = {s["id"]: s["booked_t"] for s in a_before}
    r = client.post("/api/shipments", json={"title": "Пшеница", "cargo_type": "grain", "weight_t": 400,
                                            "origin": "astrakhan", "destination": "anzali"})
    assert r.status_code == 200
    sh = r.json()
    assert sh["manual"] is True and sh["display_status"] == "planned"
    ferry = next(l["sailing_id"] for l in sh["route"]["legs"] if l["sailing_id"])
    assert ferry == FERRY_A
    after = {s["id"]: s for s in client.get("/api/sailings").json()}
    assert after[FERRY_A]["booked_t"] == booked[FERRY_A] + 400          # место забронировано сразу
    assert all(s["manual"] is False for s in client.get("/api/shipments").json() if s["id"] != sh["id"])

    alert = client.post("/api/scenarios", json={"preset": "storm_north"}).json()["alert"]
    ids = [i["shipment_id"] for i in alert["items"]]
    assert sh["id"] in ids and {"sh-01", "sh-02", "sh-03"} <= set(ids)
    weights = {s["id"]: s["weight_t"] for s in client.get("/api/shipments").json()}
    to_m = sum(weights[i["shipment_id"]] for i in alert["items"] if i["sailing_id"] == FERRY_M)
    free_m = after[FERRY_M]["capacity_t"] - after[FERRY_M]["booked_t"]
    assert to_m <= free_m                                               # паром М не переполнен
    client.post(f"/api/alerts/{alert['id']}/accept", json={"via": "telegram"})
    m = next(s for s in client.get("/api/sailings").json() if s["id"] == FERRY_M)
    assert m["booked_t"] <= m["capacity_t"]

    client.post("/api/demo/reset")
    assert sh["id"] not in {s["id"] for s in client.get("/api/shipments").json()}   # reset убирает ручной груз


# ---------------- бот ----------------

def test_alert_keyboard_has_pult_button(monkeypatch, st):
    alert = asyncio.run(st.run_scenario("storm_north"))["alert"]
    assert all(b.web_app is None for row in K.alert_kb(1, alert).inline_keyboard for b in row)   # без PUBLIC_URL нет
    monkeypatch.setattr(config, "PUBLIC_URL", "https://example.test")
    rows = K.alert_kb(1, alert).inline_keyboard
    pult = [b for row in rows for b in row if b.web_app]
    assert len(pult) == 1 and pult[0].text == "📱 Открыть пульт"
    assert pult[0].web_app.url == "https://example.test/tg/?tab=decisions"


def test_welcome_has_demo_company():
    assert f"Демо-кабинет компании „{config.DEMO_COMPANY}“" in T.welcome("Анна")


def test_weather_says_wave_is_falling(st, monkeypatch):
    w = st.weather_out()
    pt = w["points"][0]
    pt["wave_height_m"] = 1.9
    pt["forecast"] = [{"ts": f["ts"], "wave_height_m": 1.9 - i * 0.01} for i, f in enumerate(pt["forecast"])]
    w["points"] = [pt]
    monkeypatch.setattr(st, "weather_out", lambda: w)
    msg = T.weather_message(st)
    assert "сейчас 1,9 м, волна спадает" in msg and "за 48 ч до 1,9" not in msg
