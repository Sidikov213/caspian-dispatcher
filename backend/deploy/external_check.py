"""Проверки снаружи (с раннера GitHub или любой машины): /api/graph с ключом, вход logist@demo.ru,
WebSocket /ws, /docs. Ключ — из переменной окружения API_KEY, не печатается.

    API_KEY=... python external_check.py https://129-101-122-103.sslip.io
"""
import asyncio
import json
import os
import sys

import httpx
import websockets

BASE = sys.argv[1].rstrip("/")
KEY = os.environ["API_KEY"]
H = {"X-API-Key": KEY}
results = []


def report(name: str, ok: bool, detail: str) -> None:
    results.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {name}: {detail}")


with httpx.Client(timeout=30) as c:
    try:
        r = c.get(f"{BASE}/api/graph", headers=H)
        g = r.json() if r.status_code == 200 else {}
        no_key = c.get(f"{BASE}/api/graph").status_code
        report("GET /api/graph", r.status_code == 200 and no_key == 401,
               f"{r.status_code}, узлов {len(g.get('nodes', []))}, без ключа {no_key}")
    except Exception as e:
        report("GET /api/graph", False, repr(e))
    try:
        r = c.post(f"{BASE}/api/auth/login", headers=H, json={"email": "logist@demo.ru", "password": "demo123"})
        tok = r.json().get("token") if r.status_code == 200 else None
        me = c.get(f"{BASE}/api/auth/me", headers={**H, "Authorization": f"Bearer {tok}"}) if tok else None
        report("POST /api/auth/login", bool(me and me.status_code == 200),
               f"{r.status_code}, /auth/me {me.status_code if me else '-'} {me.json().get('email') if me else ''}")
    except Exception as e:
        report("POST /api/auth/login", False, repr(e))
    try:
        d = c.get(f"{BASE}/docs")
        report("GET /docs", d.status_code == 200 and "swagger" in d.text.lower(), f"{d.status_code}")
    except Exception as e:
        report("GET /docs", False, repr(e))


async def ws() -> None:
    url = BASE.replace("https://", "wss://").replace("http://", "ws://") + f"/ws?api_key={KEY}"
    try:
        async with websockets.connect(url, open_timeout=20) as sock:
            # без сценария событий нет: проверяем, что соединение принято и держится
            try:
                msg = await asyncio.wait_for(sock.recv(), timeout=3)
                detail = f"подключился, событие {json.loads(msg).get('type')}"
            except asyncio.TimeoutError:
                detail = "подключился, соединение держится"
            report("WebSocket /ws", True, detail)
    except Exception as e:
        report("WebSocket /ws", False, repr(e))

asyncio.run(ws())
sys.exit(0 if all(results) else 1)
