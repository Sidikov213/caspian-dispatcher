"""Проверки снаружи (раннер GitHub): главная сайта, /api/graph, вход, WebSocket /ws, /docs.

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


with httpx.Client(timeout=30, follow_redirects=True) as c:
    try:
        r = c.get(f"{BASE}/")
        html = r.text if r.status_code == 200 else ""
        has_title = "Каспийский" in html or "каспий" in html.lower()
        has_bundle = "/_next/" in html
        report(
            "GET /",
            r.status_code == 200 and has_title and has_bundle,
            f"{r.status_code}, title={has_title}, next={has_bundle}, bytes={len(html)}",
        )
    except Exception as e:
        report("GET /", False, repr(e))

    try:
        r = c.get(f"{BASE}/api/graph", headers=H)
        g = r.json() if r.status_code == 200 else {}
        no_key = c.get(f"{BASE}/api/graph").status_code
        report(
            "GET /api/graph",
            r.status_code == 200 and no_key == 401,
            f"{r.status_code}, узлов {len(g.get('nodes', []))}, без ключа {no_key}",
        )
    except Exception as e:
        report("GET /api/graph", False, repr(e))

    try:
        r = c.get(f"{BASE}/api/stats", headers=H)
        st = r.json() if r.status_code == 200 else {}
        report(
            "GET /api/stats",
            r.status_code == 200 and "shipments_total" in st,
            f"{r.status_code}, shipments_total={st.get('shipments_total')}",
        )
    except Exception as e:
        report("GET /api/stats", False, repr(e))

    try:
        r = c.get(f"{BASE}/api/shipments", headers=H)
        ships = r.json() if r.status_code == 200 else []
        report(
            "GET /api/shipments",
            r.status_code == 200 and isinstance(ships, list) and len(ships) > 0,
            f"{r.status_code}, грузов {len(ships) if isinstance(ships, list) else 0}",
        )
    except Exception as e:
        report("GET /api/shipments", False, repr(e))

    try:
        r = c.post(
            f"{BASE}/api/auth/login",
            headers=H,
            json={"email": "logist@demo.ru", "password": "demo123"},
        )
        tok = r.json().get("token") if r.status_code == 200 else None
        me = (
            c.get(f"{BASE}/api/auth/me", headers={**H, "Authorization": f"Bearer {tok}"})
            if tok
            else None
        )
        report(
            "POST /api/auth/login",
            bool(me and me.status_code == 200),
            f"{r.status_code}, /auth/me {me.status_code if me else '-'} "
            f"{me.json().get('email') if me else ''}",
        )
    except Exception as e:
        report("POST /api/auth/login", False, repr(e))

    try:
        t = c.get(f"{BASE}/tg/")
        fake = c.post(f"{BASE}/api/tg/auth", json={"init_data": "auth_date=1&user=%7B%7D&hash=00"})
        report("GET /tg/ (мини-приложение)",
               t.status_code == 200 and "Откройте через бота" in t.text and fake.status_code == 401,
               f"{t.status_code}, вход с поддельной подписью → {fake.status_code} (503 — нет BOT_TOKEN на сервере)")
    except Exception as e:
        report("GET /tg/ (мини-приложение)", False, repr(e))

    try:
        d = c.get(f"{BASE}/docs")
        report(
            "GET /docs",
            d.status_code == 200 and "swagger" in d.text.lower(),
            f"{d.status_code}",
        )
    except Exception as e:
        report("GET /docs", False, repr(e))


async def ws() -> None:
    url = BASE.replace("https://", "wss://").replace("http://", "ws://") + f"/ws?api_key={KEY}"
    try:
        async with websockets.connect(url, open_timeout=20) as sock:
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
