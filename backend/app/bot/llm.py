"""Подключаемый ИИ для свободных вопросов. Включается, если задан LLM_API_KEY; без ключа бот
полностью работает на кнопках и шаблонах.

Любой OpenAI-совместимый API (OpenRouter, YandexGPT-compatible, vLLM). У агента только инструменты
на чтение: get_shipments, get_shipment, get_alternatives, get_weather, explain_risk. Менять состояние
он не может — для решений есть кнопки. Числа агент берёт из инструментов, сам их не считает.
"""
import json
import logging
from collections import defaultdict, deque

import aiohttp

log = logging.getLogger(__name__)
MAX_STEPS = 4
_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=8))

SYSTEM = ("Ты — ИИ-диспетчер «Каспийского диспетчера» (МТК «Север–Юг»). Отвечай по-русски, коротко. "
          "Все числа бери только из инструментов, не придумывай и не пересчитывай. Пиши время как "
          "«12 ноя, 14:30», задержки как «+18 ч», деньги как «298 тыс ₽». Деньги и часы до события — "
          "«расчётные». Ты ничего не меняешь: чтобы принять решение, логист жмёт кнопку в алерте.")


def _fn(name: str, desc: str, props: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": required or []}}}


_ID = {"id": {"type": "string", "description": "id груза, например sh-01"}}
TOOLS = [
    _fn("get_shipments", "Список грузов пользователя со статусом, риском и ETA",
        {"tg_id": {"type": "integer"}}),
    _fn("get_shipment", "Один груз: этапы маршрута, риск, ETA, пропуск", _ID, ["id"]),
    _fn("get_alternatives", "Альтернативные маршруты груза: задержка к плану, доплата, CO₂", _ID, ["id"]),
    _fn("get_weather", "Волна в портах Каспия сейчас и максимум на 48 ч"),
    _fn("explain_risk", "Риск срыва стыковки груза: вероятность, сдвиг отправления, факторы в часах", _ID, ["id"]),
]


def _short(sh: dict) -> dict:
    return {"id": sh["id"], "title": sh["title"], "weight_t": sh["weight_t"], "status": sh["display_status"],
            "origin": sh["origin"], "destination": sh["destination"], "planned_eta": sh["planned_eta"],
            "eta": sh["eta"], "miss_probability": sh["risk"]["miss_probability"], "route_id": sh["route"]["id"],
            "pass_id": sh["pass_id"], "pass_state": sh["pass_state"]}


def run_tool(st, name: str, args: dict):
    """Только чтение состояния."""
    try:
        if name == "get_shipments":
            return [_short(s) for s in st.shipments_list()]
        if name == "get_shipment":
            sh = st.shipment(args["id"])
            return {**_short(sh), "legs": [{k: leg[k] for k in ("from", "to", "mode", "planned_start",
                                                               "planned_end", "predicted_delay_h", "status")}
                                          for leg in sh["route"]["legs"]]}
        if name == "get_alternatives":
            return [{"route_id": a["route"]["id"], "delta": a["delta"], "recommended": a["recommended"],
                     "miss_probability": a["risk"]["miss_probability"]} for a in st.alternatives(args["id"])]
        if name == "get_weather":
            w = st.weather_out()
            return {"updated_at": w["updated_at"], "wave_limit_m": st.meta["wave_limit_m"],
                    "points": [{"node_id": p["node_id"], "now_m": p["wave_height_m"],
                                "max_48h_m": max(f["wave_height_m"] for f in p["forecast"][:48])}
                               for p in w["points"]]}
        if name == "explain_risk":
            return st.shipment(args["id"])["risk"]
    except Exception as e:  # noqa: BLE001 — ошибку отдаём модели текстом
        return {"error": str(e)}
    return {"error": f"нет инструмента {name}"}


async def _chat(settings, messages: list[dict]) -> dict:
    payload = {"model": settings.llm_model, "messages": messages, "tools": TOOLS, "temperature": 0.2}
    headers = {"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
        async with s.post(f"{settings.llm_base_url}/chat/completions", json=payload, headers=headers) as r:
            data = await r.json(content_type=None)
            if r.status != 200:
                raise RuntimeError(f"LLM {r.status}: {data}")
            return data["choices"][0]["message"]


async def answer(st, settings, tg_id: int, text: str) -> str | None:
    """Ответ ИИ или None (ключа нет / сбой) — тогда бот отвечает подсказкой про кнопки."""
    if not settings.llm_enabled:
        return None
    hist = _history[tg_id]
    messages = [{"role": "system", "content": SYSTEM}, *hist, {"role": "user", "content": text}]
    try:
        for _ in range(MAX_STEPS):
            msg = await _chat(settings, messages)
            calls = msg.get("tool_calls") or []
            if not calls:
                out = (msg.get("content") or "").strip()
                hist.extend([{"role": "user", "content": text}, {"role": "assistant", "content": out}])
                return out or None
            messages.append(msg)
            for c in calls:
                args = json.loads(c["function"].get("arguments") or "{}")
                result = run_tool(st, c["function"]["name"], args)
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": json.dumps(result, ensure_ascii=False)})
    except Exception:
        log.exception("LLM недоступен")
    return None
