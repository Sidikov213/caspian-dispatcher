"""Вход в Telegram Mini App: проверка initData и сессионный токен.

Мини-приложение не знает API_KEY. Telegram передаёт ему initData — строку с данными пользователя и
подписью. POST /api/tg/auth проверяет подпись по токену бота (документация Telegram, «Validating data
received via the Mini App»): secret = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN),
hash = HMAC_SHA256(key=secret, msg=data_check_string). initData старше 24 ч не принимается.
В ответ — сессионный JWT на 24 ч (свой ключ, выведенный из JWT_SECRET): его принимает require_key
как второй способ авторизации рядом с X-API-Key, а WebSocket — в параметре ?token=.
"""
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import jwt

from .config import BOT_TOKEN, DEMO_COMPANY, JWT_SECRET, MOCK_JWT_SECRET
from .errors import ApiError

INIT_DATA_TTL_S = 24 * 3600
SESSION_TTL = timedelta(hours=24)
SESSION_KEY = hashlib.sha256(b"caspian-tg:" + (JWT_SECRET or MOCK_JWT_SECRET).encode()).hexdigest()


def sign_init_data(fields: dict, bot_token: str) -> str:
    """Подписать initData так же, как Telegram (для тестов и локальной отладки)."""
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    from urllib.parse import urlencode
    return urlencode({**fields, "hash": h})


def verify_init_data(init_data: str, bot_token: str | None = None, now: float | None = None) -> dict:
    """Проверить подпись и срок. Возвращает пользователя Telegram {id, first_name, …}."""
    token = BOT_TOKEN if bot_token is None else bot_token
    if not token:
        raise ApiError(503, "tg_auth_unavailable", "Бот не настроен на сервере — вход через Telegram недоступен")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        raise ApiError(401, "invalid_init_data", "initData не разобрана") from None
    got = pairs.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    want = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not got or not hmac.compare_digest(got, want):
        raise ApiError(401, "invalid_init_data", "Подпись initData не совпала — откройте приложение через бота")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        auth_date = 0
    if (now if now is not None else time.time()) - auth_date > INIT_DATA_TTL_S:
        raise ApiError(401, "init_data_expired", "Сессия Telegram устарела — откройте приложение заново")
    try:
        user = json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError:
        user = {}
    if "id" not in user:
        raise ApiError(401, "invalid_init_data", "В initData нет пользователя")
    return user


def issue_session(user: dict) -> dict:
    now = datetime.now(timezone.utc)
    name = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x) or user.get("username") or "—"
    token = jwt.encode({"sub": str(user["id"]), "name": name, "typ": "tg", "iat": now, "exp": now + SESSION_TTL},
                       SESSION_KEY, algorithm="HS256")
    return {"token": token, "expires_at": (now + SESSION_TTL).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "user": {"id": int(user["id"]), "name": name, "username": user.get("username")},
            "company": DEMO_COMPANY}


def session_claims(token: str | None) -> dict | None:
    """Claims сессии мини-приложения или None."""
    if not token:
        return None
    try:
        claims = jwt.decode(token, SESSION_KEY, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == "tg" else None


def session_ok(token: str | None) -> bool:
    return session_claims(token) is not None
