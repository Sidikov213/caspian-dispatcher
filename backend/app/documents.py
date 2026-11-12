"""Документы: фото → поля (vision-LLM) → проверки → подтверждение → хэш → пропуск.

Уже работает: хэш подтверждённых полей.
TODO: извлечение полей vision-LLM, запасной путь — кэш для демо-инвойса;
проверки: пустое обязательное поле и расхождение веса > 5% блокируют, сомнение в ТН ВЭД — предупреждение.
"""
import hashlib
import json


def doc_hash(fields: dict) -> str:
    raw = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
