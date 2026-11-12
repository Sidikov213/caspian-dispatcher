"""Пуши в приложение: /api/devices, подписчик шины событий, запрос в FCM HTTP v1."""
import io
import json

import jwt
import pytest

from app import auth as A
from app import events, main, push


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    acc = A.Accounts(tmp_path / "accounts.json")
    monkeypatch.setattr(main, "accounts", acc)
    return acc


@pytest.fixture
def devices(tmp_path, monkeypatch):
    d = push.Devices(tmp_path / "devices.json")
    monkeypatch.setattr(main, "devices", d)
    return d


def login(client, email):
    return {"Authorization": "Bearer " + client.post("/api/auth/login", json={"email": email, "password": "demo123"}).json()["token"]}


def test_devices_need_login(client, accounts, devices):
    assert client.post("/api/devices", json={"token": "t1", "platform": "android"}).status_code == 401
    r = client.post("/api/devices", json={"token": "t1", "platform": "android"}, headers=login(client, "expeditor@demo.ru"))
    assert r.status_code == 200 and r.json() == {"ok": True, "push_enabled": False}
    assert client.post("/api/devices", json={"token": "t1", "platform": "web"},
                       headers=login(client, "expeditor@demo.ru")).status_code == 422
    assert devices.tokens() == ["t1"]


def test_token_moves_between_accounts_and_survives_reload(client, accounts, devices, tmp_path):
    exp, log = login(client, "expeditor@demo.ru"), login(client, "logist@demo.ru")
    client.post("/api/devices", json={"token": "phone", "platform": "ios"}, headers=exp)
    client.post("/api/devices", json={"token": "phone", "platform": "ios"}, headers=log)
    client.post("/api/devices", json={"token": "tablet", "platform": "android"}, headers=log)
    assert sorted(devices.tokens()) == ["phone", "tablet"] and len(devices.by_user) == 1
    assert push.Devices(tmp_path / "devices.json").count() == 2            # файл переживает перезапуск
    client.post("/api/demo/reset")
    assert devices.count() == 2                                             # и reset
    r = client.request("DELETE", "/api/devices", json={"token": "phone"}, headers=log)
    assert r.status_code == 200 and devices.tokens() == ["tablet"]


class FakeFcm:
    def __init__(self, dead=()):
        self.sent, self.dead = [], set(dead)

    def send(self, token, title, body, data):
        self.sent.append((token, title, body, data))
        return "dead" if token in self.dead else "ok"


@pytest.fixture
def fcm(devices):
    fake = FakeFcm(dead={"old"})
    notifier = push.PushNotifier(devices, fake)
    events.subscribe(notifier)
    yield fake
    events.unsubscribe(notifier)


def test_alert_created_and_accepted_push(client, devices, fcm):
    devices.register("u1", "phone", "android")
    devices.register("u2", "old", "ios")
    alert = client.post("/api/scenarios", json={"preset": "storm_north"}).json()["alert"]
    created = [s for s in fcm.sent if s[3]["type"] == "alert.created"]
    assert {s[0] for s in created} == {"phone", "old"}
    token, title, body, data = created[0]
    assert title == alert["title"] and body and len(body) <= push.BODY_MAX
    assert data == {"type": "alert.created", "alert_id": alert["id"], "status": "new"}
    assert devices.tokens() == ["phone"]                                    # мёртвый токен удалён

    client.post(f"/api/alerts/{alert['id']}/accept", json={"via": "web"})
    client.post(f"/api/alerts/{alert['id']}/accept", json={"via": "telegram"})   # повтор — без второго пуша
    accepted = [s for s in fcm.sent if s[3]["type"] == "alert.updated"]
    assert len(accepted) == 1 and accepted[0][1] == "Решение принято" and "Махачкал" in accepted[0][2]
    assert accepted[0][3]["status"] == "accepted"


def test_no_push_without_items_or_devices(client, fcm, devices):
    client.post("/api/scenarios", json={"preset": "storm_north"})
    assert fcm.sent == []                                                   # устройств нет — тишина


def test_fcm_http_v1_request(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    creds = {"project_id": "demo-proj", "client_email": "sa@demo-proj.iam.gserviceaccount.com",
             "private_key": pem, "private_key_id": "k1", "token_uri": "https://oauth2.example/token"}
    calls = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        calls.append(req)
        if req.full_url == creds["token_uri"]:
            return Resp(json.dumps({"access_token": "ya29.x", "expires_in": 3600}).encode())
        return Resp(b"{}")

    monkeypatch.setattr(push.urllib.request, "urlopen", fake_urlopen)
    c = push.FcmClient(creds)
    assert c.send("tok", "Заголовок", "Текст", {"type": "alert.created", "alert_id": "alert-001"}) == "ok"
    assert c.send("tok2", "З", "Т", {}) == "ok"
    token_reqs = [r for r in calls if r.full_url == creds["token_uri"]]
    assert len(token_reqs) == 1                                             # OAuth-токен кэшируется
    assertion = dict(x.split("=") for x in token_reqs[0].data.decode().split("&"))["assertion"]
    claims = jwt.decode(assertion, key.public_key(), algorithms=["RS256"], audience=creds["token_uri"])
    assert claims["iss"] == creds["client_email"] and claims["scope"] == push.SCOPE
    msg_req = calls[1]
    assert msg_req.full_url == "https://fcm.googleapis.com/v1/projects/demo-proj/messages:send"
    assert msg_req.get_header("Authorization") == "Bearer ya29.x"
    msg = json.loads(msg_req.data)["message"]
    assert msg["token"] == "tok" and msg["notification"] == {"title": "Заголовок", "body": "Текст"}
    assert msg["data"]["alert_id"] == "alert-001" and msg["android"]["priority"] == "high"
