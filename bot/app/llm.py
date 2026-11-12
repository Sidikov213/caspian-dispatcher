"""Клиент к любому OpenAI-совместимому API + память диалога в RAM."""
import json
import logging
from collections import defaultdict, deque

import aiohttp

from .config import settings

log = logging.getLogger(__name__)
_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=12))  # последние 6 пар реплик


async def chat(messages: list[dict], temperature: float = 0.4, json_mode: bool = False) -> str:
    payload = {"model": settings.llm_model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(f"{settings.llm_base_url}/chat/completions", json=payload, headers=headers) as r:
                data = await r.json(content_type=None)
                if r.status != 200:
                    log.error("LLM error %s: %s", r.status, data)
                    return "⚠️ ИИ сейчас недоступен, попробуйте ещё раз."
                return data["choices"][0]["message"]["content"].strip()
    except Exception:
        log.exception("LLM request failed")
        return "⚠️ ИИ сейчас недоступен, попробуйте ещё раз."


async def ask(user_id: int, text: str, system: str | None = None) -> str:
    """Диалог с памятью для конкретного пользователя."""
    hist = _history[user_id]
    messages = [{"role": "system", "content": system or settings.system_prompt}, *hist, {"role": "user", "content": text}]
    answer = await chat(messages)
    hist.append({"role": "user", "content": text})
    hist.append({"role": "assistant", "content": answer})
    return answer


async def extract(text: str, schema_hint: str) -> dict:
    """Структурирует свободный текст в JSON (заявки, жалобы, анкеты и т.п.)."""
    messages = [
        {"role": "system", "content": f"Извлеки данные из текста. Верни ТОЛЬКО JSON вида: {schema_hint}"},
        {"role": "user", "content": text},
    ]
    raw = await chat(messages, temperature=0, json_mode=True)
    try:
        return json.loads(raw.strip().removeprefix("```json").removesuffix("```"))
    except json.JSONDecodeError:
        return {"raw": raw}


def reset(user_id: int) -> None:
    _history.pop(user_id, None)
