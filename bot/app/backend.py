"""Клиент к общему бэкенду команды. Если BACKEND_URL пуст — пишет в локальный JSON (для демо)."""
import json
import logging
from pathlib import Path

import aiohttp

from .config import settings

log = logging.getLogger(__name__)
_LOCAL = Path("local_db.json")


def _local_load() -> dict:
    if _LOCAL.exists():
        return json.loads(_LOCAL.read_text(encoding="utf-8"))
    return {"items": [], "users": {}}


def _local_save(db: dict) -> None:
    _LOCAL.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


async def _request(method: str, path: str, **kw):
    headers = {"Authorization": f"Bearer {settings.backend_token}"} if settings.backend_token else {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.request(method, f"{settings.backend_url}{path}", headers=headers, **kw) as r:
            r.raise_for_status()
            return await r.json(content_type=None)


async def register_user(tg_id: int, name: str) -> None:
    if not settings.backend_url:
        db = _local_load()
        db["users"][str(tg_id)] = {"name": name}
        _local_save(db)
        return
    try:
        await _request("POST", "/api/users", json={"telegram_id": tg_id, "name": name})
    except Exception:
        log.exception("register_user failed")


async def create_item(tg_id: int, data: dict) -> dict:
    """Универсальная сущность: заявка / отзыв / бронь — переименуете под кейс."""
    if not settings.backend_url:
        db = _local_load()
        item = {"id": len(db["items"]) + 1, "telegram_id": tg_id, "status": "new", **data}
        db["items"].append(item)
        _local_save(db)
        return item
    return await _request("POST", "/api/items", json={"telegram_id": tg_id, **data})


async def list_items(tg_id: int | None = None) -> list[dict]:
    if not settings.backend_url:
        items = _local_load()["items"]
        return [i for i in items if tg_id is None or i["telegram_id"] == tg_id]
    params = {"telegram_id": tg_id} if tg_id else {}
    return await _request("GET", "/api/items", params=params)


async def all_user_ids() -> list[int]:
    if not settings.backend_url:
        return [int(x) for x in _local_load()["users"]]
    users = await _request("GET", "/api/users")
    return [u["telegram_id"] for u in users]
