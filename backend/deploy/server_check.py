"""Проверки на сервере после выкатки: Telegram getMe, волна из Open-Meteo, /api/model, /api/demo/check.

Запуск (на VPS): /opt/caspian/backend/.venv/bin/python /opt/caspian/backend/deploy/server_check.py
Секреты читаются из .env и не печатаются. Код выхода 1, если что-то не прошло.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
env = dict(re.findall(r"(?m)^([A-Z_]+)=(.*)$", (APP / ".env").read_text(encoding="utf-8")))
API = "http://127.0.0.1:8000/api"
results = []


def get(url: str, headers: dict | None = None, timeout: int = 30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check(name: str, fn) -> None:
    try:
        ok, detail = fn()
    except Exception as e:  # сеть, таймаут, неверный ответ
        ok, detail = False, f"{type(e).__name__}: {e}"
    results.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {name}: {detail}")


def telegram():
    token = env.get("BOT_TOKEN", "").strip()
    if not token:
        return False, "BOT_TOKEN пуст"
    me = get(f"https://api.telegram.org/bot{token}/getMe")
    return me.get("ok") is True, f"@{me.get('result', {}).get('username')}"


def open_meteo():
    d = get("https://marine-api.open-meteo.com/v1/marine?latitude=42.98&longitude=47.5"
            "&hourly=wave_height&forecast_days=1")
    waves = [w for w in d["hourly"]["wave_height"] if w is not None]
    return bool(waves), f"волна у Махачкалы сейчас {waves[0]} м, точек {len(waves)}" if waves else "нет данных"


def model():
    m = get(f"{API}/model", {"X-API-Key": env["API_KEY"]})
    return m["active"] == "catboost", m["summary"]


def demo_check():
    c = get(f"{API}/demo/check", {"X-API-Key": env["API_KEY"]}, timeout=60)
    bad = [f"{x['name']}: {x['actual']} вместо {x['expected']}" for x in c["checks"] if not x["ok"]]
    risks = "/".join(str(int(x["actual"])) for x in c["checks"] if x["name"].startswith("risk_sh"))
    return c["ok"], (f"риск {risks}%, погода {c['weather']['source']}" if c["ok"]
                     else "; ".join(bad + c["problems"]))


check("Telegram API getMe", telegram)
check("Open-Meteo Marine", open_meteo)
check("GET /api/model", model)
check("GET /api/demo/check", demo_check)
sys.exit(0 if all(results) else 1)
