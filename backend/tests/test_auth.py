"""Регистрация и вход. Доступ к /api/* по-прежнему по X-API-Key; Bearer — только для /auth/me."""
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import auth as A
from app import main


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    acc = A.Accounts(tmp_path / "accounts.json")
    monkeypatch.setattr(main, "accounts", acc)
    return acc


def register(client, **kw):
    body = {"name": "Анна", "email": "anna@example.ru", "password": "secret1", "role": "logist", **kw}
    return client.post("/api/auth/register", json=body)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me(client, accounts):
    r = register(client, email="  Anna@Example.RU ")
    assert r.status_code == 200
    out = r.json()
    assert out["user"] == {"id": out["user"]["id"], "name": "Анна", "email": "anna@example.ru", "role": "logist",
                           "permissions": ["run_scenario", "reset_demo", "decide_alert"]}
    assert client.get("/api/auth/me", headers=bearer(out["token"])).json() == out["user"]

    r = client.post("/api/auth/login", json={"email": "anna@example.ru", "password": "secret1"})
    assert r.status_code == 200 and r.json()["user"] == out["user"]
    assert client.get("/api/auth/me", headers=bearer(r.json()["token"])).json()["role"] == "logist"

    claims = jwt.decode(out["token"], options={"verify_signature": False})
    assert timedelta(days=6, hours=23) < timedelta(seconds=claims["exp"] - claims["iat"]) <= timedelta(days=7)


def test_password_stored_only_as_salted_hash(client, accounts):
    register(client)
    register(client, email="boris@example.ru", password="secret1")
    raw = accounts.path.read_text(encoding="utf-8")
    assert "secret1" not in raw
    stored = [a["password_hash"] for a in json.loads(raw)["accounts"] if a["email"].endswith("example.ru")]
    assert all(h.startswith("scrypt$") for h in stored) and stored[0] != stored[1]   # соль разная


def test_errors(client, accounts):
    assert register(client).status_code == 200
    r = register(client, email="ANNA@example.ru", name="Другая")
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"

    r = client.post("/api/auth/login", json={"email": "anna@example.ru", "password": "wrong12"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    r = client.post("/api/auth/login", json={"email": "nobody@example.ru", "password": "secret1"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"

    r = register(client, email="c@example.ru", password="12345")
    assert r.status_code == 422 and r.json()["error"]["code"] == "weak_password"
    r = register(client, email="not-an-email")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_email"
    r = register(client, email="d@example.ru", role="admin")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_me_rejects_bad_tokens(client, accounts):
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"
    assert client.get("/api/auth/me", headers=bearer("garbage")).status_code == 401
    user = register(client).json()["user"]
    expired = jwt.encode({"sub": user["id"], "email": user["email"], "typ": "auth",
                          "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, A.AUTH_KEY, algorithm="HS256")
    r = client.get("/api/auth/me", headers=bearer(expired))
    assert r.status_code == 401 and "истёк" in r.json()["error"]["message"]
    # QR-пропуск подписан другим ключом и как токен входа не годится
    pass_token = client.get("/api/passes/pass-01").json()["token"]
    assert client.get("/api/auth/me", headers=bearer(pass_token)).status_code == 401


def test_demo_accounts(client, accounts):
    for email, role in (("logist@demo.ru", "logist"), ("expeditor@demo.ru", "expeditor")):
        r = client.post("/api/auth/login", json={"email": email, "password": "demo123"})
        assert r.status_code == 200 and r.json()["user"]["role"] == role


def test_accounts_survive_reset_and_restart(client, accounts):
    register(client)
    assert client.post("/api/demo/reset").status_code == 200
    assert client.post("/api/auth/login", json={"email": "anna@example.ru", "password": "secret1"}).status_code == 200
    again = A.Accounts(accounts.path)                       # «перезапуск сервера»
    assert again.login("anna@example.ru", "secret1")["user"]["name"] == "Анна"
    assert len(again.by_email) == 3                          # демо-аккаунты не задвоились


def test_api_key_rules_unchanged(client, accounts):
    """Bearer не заменяет X-API-Key и не нужен для остальных эндпоинтов."""
    token = register(client).json()["token"]
    no_key = {"X-API-Key": ""}
    assert client.get("/api/shipments", headers=no_key).status_code == 401
    assert client.get("/api/shipments", headers={**no_key, **bearer(token)}).status_code == 401
    assert client.post("/api/auth/login", headers=no_key,
                       json={"email": "anna@example.ru", "password": "secret1"}).status_code == 401
    assert client.get("/api/shipments").status_code == 200   # только ключ, без токена — как раньше
    assert client.post("/api/scenarios", json={"preset": "storm_north"}).status_code == 200
