"""Регистрация и вход: аккаунты логиста и экспедитора.

Только чтобы клиент знал имя и роль. Доступ к /api/* по-прежнему даёт X-API-Key; Bearer-токен нужен
лишь для GET /api/auth/me, ограничений по ролям нет.

- Хранение: data/accounts.json (не в git), отдельно от состояния демо — переживает demo/reset и
  перезапуск сервера.
- Пароль — только хэш scrypt (hashlib, стандартная библиотека) с солью 16 байт.
- Токен — JWT HS256 на 7 дней. Ключ выводится из JWT_SECRET отдельно от ключа пропусков, поэтому
  токен входа и QR-пропуск друг за друга не сойдут.
- Демо-аккаунты logist@demo.ru и expeditor@demo.ru (пароль demo123) создаются, если их нет.
"""
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

from .config import JWT_SECRET, MOCK_JWT_SECRET
from .errors import ApiError

log = logging.getLogger("caspian")

TOKEN_TTL = timedelta(days=7)
MIN_PASSWORD = 6
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}
DEMO_PASSWORD = "demo123"
DEMO_ACCOUNTS = [
    {"name": "Логист (демо)", "email": "logist@demo.ru", "role": "logist"},
    {"name": "Экспедитор (демо)", "email": "expeditor@demo.ru", "role": "expeditor"},
]

if not JWT_SECRET:
    log.warning("JWT_SECRET не задан в .env — токены входа подписаны публичным ключом моков, только для разработки")
AUTH_KEY = hashlib.sha256(b"caspian-auth:" + (JWT_SECRET or MOCK_JWT_SECRET).encode()).hexdigest()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${salt.hex()}${h.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), dklen=len(h) // 2,
                             n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(got.hex(), h)
    except ValueError:
        return False


def public(acc: dict) -> dict:
    return {k: acc[k] for k in ("id", "name", "email", "role")}


class Accounts:
    """Аккаунты в памяти + файл. path=None — только в памяти."""

    def __init__(self, path: Path | None, demo: bool = True):
        self.path = Path(path) if path else None
        self.lock = threading.Lock()
        self.by_email: dict[str, dict] = self._load()
        if demo:
            self.ensure_demo()

    # ---------- файл ----------

    def _load(self) -> dict[str, dict]:
        if self.path is None or not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return {a["email"]: a for a in raw["accounts"]}
        except Exception:
            log.exception("не прочитал %s — аккаунты пустые", self.path)
            return {}

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"accounts": list(self.by_email.values())}, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.path)

    def ensure_demo(self) -> None:
        added = [d["email"] for d in DEMO_ACCOUNTS if d["email"] not in self.by_email]
        for d in DEMO_ACCOUNTS:
            if d["email"] in added:
                self._add(d["name"], d["email"], DEMO_PASSWORD, d["role"], save=False)
        if added:
            self._save()
            log.info("Демо-аккаунты созданы: %s (пароль %s)", ", ".join(added), DEMO_PASSWORD)

    # ---------- операции ----------

    def _add(self, name: str, email: str, password: str, role: str, save: bool = True) -> dict:
        acc = {"id": f"u-{len(self.by_email) + 1:04d}", "name": name, "email": email, "role": role,
               "password_hash": hash_password(password),
               "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}
        while any(a["id"] == acc["id"] for a in self.by_email.values()):
            acc["id"] = f"u-{secrets.token_hex(3)}"
        self.by_email[email] = acc
        if save:
            self._save()
        return acc

    def register(self, name: str, email: str, password: str, role: str) -> dict:
        name, email = name.strip(), email.strip().lower()
        if not name:
            raise ApiError(422, "invalid_name", "Укажите имя")
        if not EMAIL_RE.match(email):
            raise ApiError(422, "invalid_email", "Неверный email")
        if len(password) < MIN_PASSWORD:
            raise ApiError(422, "weak_password", f"Пароль не короче {MIN_PASSWORD} символов")
        with self.lock:
            if email in self.by_email:
                raise ApiError(409, "email_taken", "Этот email уже зарегистрирован")
            acc = self._add(name, email, password, role)
        return self.session(acc)

    def login(self, email: str, password: str) -> dict:
        acc = self.by_email.get(email.strip().lower())
        if acc is None:
            hash_password(password)          # то же время ответа, что и при неверном пароле
            raise ApiError(401, "invalid_credentials", "Неверный email или пароль")
        if not check_password(password, acc["password_hash"]):
            raise ApiError(401, "invalid_credentials", "Неверный email или пароль")
        return self.session(acc)

    def session(self, acc: dict) -> dict:
        now = datetime.now(timezone.utc)
        token = jwt.encode({"sub": acc["id"], "email": acc["email"], "role": acc["role"], "typ": "auth",
                            "iat": now, "exp": now + TOKEN_TTL}, AUTH_KEY, algorithm="HS256")
        return {"token": token, "user": public(acc)}

    def me(self, token: str | None) -> dict:
        if not token:
            raise ApiError(401, "invalid_token", "Нужен заголовок Authorization: Bearer <token>")
        try:
            claims = jwt.decode(token, AUTH_KEY, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        except jwt.ExpiredSignatureError:
            raise ApiError(401, "invalid_token", "Токен истёк, войдите снова") from None
        except jwt.PyJWTError:
            raise ApiError(401, "invalid_token", "Неверный токен") from None
        acc = self.by_email.get(claims.get("email", ""))
        if claims.get("typ") != "auth" or acc is None or acc["id"] != claims["sub"]:
            raise ApiError(401, "invalid_token", "Неверный токен")
        return public(acc)
