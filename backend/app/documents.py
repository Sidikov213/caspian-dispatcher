"""Документы: фото → поля (vision-LLM) → проверки → подтверждение → хэш → пропуск.

Уже работает: хэш подтверждённых полей, проверки (state.py), закэшированный черновик демо-инвойса.
TODO: извлечение полей vision-LLM, запасной путь — кэш для демо-инвойса;
проверки: пустое обязательное поле и расхождение веса > 5% блокируют, сомнение в ТН ВЭД — предупреждение.
"""
import hashlib
import json


def doc_hash(fields: dict) -> str:
    raw = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_fields(fields: dict) -> dict:
    """Целые числа без «.0», чтобы хэш не зависел от того, пришло 30000 или 30000.0."""
    out = {}
    for k, v in fields.items():
        out[k] = int(v) if isinstance(v, float) and v.is_integer() else v
    return out
