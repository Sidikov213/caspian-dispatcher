"""Пуш-уведомления в мобильное приложение через Firebase Cloud Messaging (HTTP v1).

Устройства: POST /api/devices (FCM-токен и платформа), DELETE /api/devices. Хранение — data/devices.json
(не в git, переживает demo/reset и перезапуск, как accounts.json и users.json): user_id → токены.

Отправка: подписчик на шину событий, как уведомитель Telegram-бота — один subscribe, без логики в роутах.
  alert.created                → пуш всем устройствам: заголовок и короткий текст алерта, data {type, alert_id}
  alert.updated (accepted)     → пуш «Решение принято», data {type, alert_id, status}

firebase-admin не нужен: сервисный аккаунт подписывает JWT (RS256, PyJWT + cryptography), обменивает его
на OAuth-токен и шлёт сообщения в https://fcm.googleapis.com/v1/projects/<project>/messages:send.
Без FIREBASE_CREDENTIALS сервер работает как раньше: токены принимаются и хранятся, пуши не уходят.
"""
import asyncio
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import jwt

log = logging.getLogger("caspian")

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
BODY_MAX = 180
# Ответы FCM, после которых токен больше не годится — удаляем его.
DEAD_TOKEN = ("UNREGISTERED", "NOT_FOUND")


class Devices:
    """user_id → [{token, platform, updated_at}]. path=None — только в памяти (тесты)."""

    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        self.lock = threading.Lock()
        self.by_user: dict[str, list[dict]] = self._load()

    def _load(self) -> dict:
        if self.path is None:
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            log.exception("не прочитал %s — устройств нет", self.path)
            return {}

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.by_user, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            log.exception("не записал %s", self.path)

    def register(self, user_id: str, token: str, platform: str) -> None:
        """Токен принадлежит одному пользователю: при входе другим аккаунтом на том же телефоне он переезжает."""
        with self.lock:
            for uid in list(self.by_user):
                self.by_user[uid] = [d for d in self.by_user[uid] if d["token"] != token]
                if not self.by_user[uid]:
                    del self.by_user[uid]
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            self.by_user.setdefault(user_id, []).append({"token": token, "platform": platform, "updated_at": now})
            self._save()

    def unregister(self, token: str) -> bool:
        with self.lock:
            found = False
            for uid in list(self.by_user):
                left = [d for d in self.by_user[uid] if d["token"] != token]
                found |= len(left) != len(self.by_user[uid])
                if left:
                    self.by_user[uid] = left
                else:
                    del self.by_user[uid]
            if found:
                self._save()
            return found

    def tokens(self) -> list[str]:
        with self.lock:
            return [d["token"] for ds in self.by_user.values() for d in ds]

    def count(self) -> int:
        return len(self.tokens())


class FcmClient:
    """Отправка через FCM HTTP v1 по ключу сервисного аккаунта (JSON из Firebase Console)."""

    def __init__(self, creds: dict):
        self.creds = creds
        self.project = creds["project_id"]
        self._token: str | None = None
        self._exp = 0.0
        self.lock = threading.Lock()

    @classmethod
    def from_file(cls, path: str | Path) -> "FcmClient":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def access_token(self) -> str:
        with self.lock:
            if self._token and time.time() < self._exp - 60:
                return self._token
            now = int(time.time())
            assertion = jwt.encode({"iss": self.creds["client_email"], "scope": SCOPE,
                                    "aud": self.creds["token_uri"], "iat": now, "exp": now + 3600},
                                   self.creds["private_key"], algorithm="RS256",
                                   headers={"kid": self.creds.get("private_key_id")})
            body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                           "assertion": assertion}).encode()
            with urllib.request.urlopen(urllib.request.Request(self.creds["token_uri"], data=body), timeout=20) as r:
                out = json.loads(r.read())
            self._token, self._exp = out["access_token"], now + int(out.get("expires_in", 3600))
            return self._token

    def send(self, token: str, title: str, body: str, data: dict[str, str]) -> str:
        """'ok' | 'dead' (токен больше не действует) | 'error'."""
        msg = {"message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": data,
            "android": {"priority": "high", "notification": {"channel_id": "alerts", "sound": "default"}},
            "apns": {"headers": {"apns-priority": "10"}, "payload": {"aps": {"sound": "default"}}},
        }}
        req = urllib.request.Request(FCM_URL.format(project=self.project), data=json.dumps(msg).encode(),
                                     headers={"Authorization": f"Bearer {self.access_token()}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20):
                return "ok"
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            if e.code == 404 or any(code in detail for code in DEAD_TOKEN):
                return "dead"
            log.warning("FCM %s: %s", e.code, detail[:300])
            return "error"
        except OSError as e:
            log.warning("FCM недоступен: %s", e)
            return "error"


def short(text: str, limit: int = BODY_MAX) -> str:
    """Первые строки текста алерта без пустых, не длиннее limit."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out = ""
    for ln in lines[1:] or lines:            # первая строка текста повторяет заголовок
        nxt = f"{out} {ln}".strip()
        if len(nxt) > limit:
            break
        out = nxt
    return out or (lines[0][: limit - 1] + "…" if lines else "")


class PushNotifier:
    """Подписчик шины событий: alert.created и принятие решения → пуш на все устройства."""

    def __init__(self, devices: Devices, client):
        self.devices = devices
        self.client = client
        self.done: set[tuple[str, str]] = set()   # (alert_id, статус) — один пуш на событие

    async def __call__(self, type_: str, payload) -> None:
        if type_ == "demo.reset":   # новый прогон демо: номера алертов идут заново, пуши должны уйти снова
            self.done.clear()
        elif type_ == "alert.created" and payload and payload.get("items"):
            await self.push(payload, "alert.created", payload["title"], short(payload.get("text", "")))
        elif type_ == "alert.updated" and payload and payload.get("status") == "accepted":
            opt = next((o for o in payload.get("options", []) if o.get("recommended")), None)
            what = opt["title"].split(" (")[0] if opt else "ждать следующий рейс"
            await self.push(payload, "alert.updated", "Решение принято", f"{what}. {payload['title']}")

    async def push(self, alert: dict, type_: str, title: str, body: str) -> None:
        key = (alert["id"], type_ + ":" + alert.get("status", ""))
        if key in self.done:
            return
        self.done.add(key)
        tokens = self.devices.tokens()
        if not tokens:
            return
        data = {"type": type_, "alert_id": alert["id"], "status": alert.get("status", "")}
        results = await asyncio.gather(*(asyncio.to_thread(self.client.send, t, title, body, data) for t in tokens),
                                       return_exceptions=True)
        ok = 0
        for t, r in zip(tokens, results):
            if r == "dead":
                self.devices.unregister(t)
            elif isinstance(r, Exception):
                log.warning("FCM: сбой отправки: %s", r)
            ok += r == "ok"
        log.info("Пуш: %s %s отправлен на %d из %d устройств", type_, alert["id"], ok, len(tokens))


def make_client(path: str | None):
    """FcmClient по FIREBASE_CREDENTIALS или None (пуши выключены, причина в логе)."""
    if not path:
        log.info("Пуш: FIREBASE_CREDENTIALS не задан — пуши в приложение выключены")
        return None
    try:
        client = FcmClient.from_file(path)
    except (OSError, ValueError, KeyError) as e:
        log.warning("Пуш: не прочитал ключ Firebase %s (%s) — пуши выключены", path, type(e).__name__)
        return None
    log.info("Пуш: FCM включён, проект %s", client.project)
    return client
