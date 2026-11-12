"""GET /api/model: какой предиктор активен, метрики из data/model_report.json, честная пометка.

На сервере работает только классификатор CatBoost: он даёт вероятность срыва стыковки. Сдвиг
отправления, задержки, деньги и CO₂ — расчёт по прогнозу погоды и расписанию. Регрессор сдвига
обучен и есть в отчёте, но в расчёт не подключён — только проверка.
"""
import json
import logging

from .config import MODEL_REPORT_PATH, PREDICTOR

log = logging.getLogger("caspian")

NOTE = ("Обучена на синтетической истории: история сгенерирована по правилам (scripts/gen_history.py), "
        "метрики показывают работу конвейера, а не точность на реальных данных.")
SHIFT = "расчёт по прогнозу погоды и расписанию рейсов"
REGRESSOR = "только проверка: метрика в отчёте и график «прогноз против факта», в расчёт не подключён"


def load_report(path=MODEL_REPORT_PATH) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        log.exception("model_report.json не читается")
        return None


def summary(predictor, path=MODEL_REPORT_PATH) -> str:
    """Одна строка: какой предиктор реально активен. Для ответа /api/model и лога при старте."""
    name = getattr(predictor, "name", "formula")
    reason = getattr(predictor, "fallback_reason", None)
    if name == "catboost":
        clf = (load_report(path) or {}).get("classifier") or {}
        auc = f", AUC {clf['auc']:.3f}".replace(".", ",") if "auc" in clf else ""
        return f"Активен предиктор: CatBoost (data/model.cbm, синтетическая история{auc})"
    if reason:
        return f"Активен предиктор: логистическая формула — ОТКАТ с CatBoost: {reason}"
    return "Активен предиктор: логистическая формула (PREDICTOR=formula)"


def log_active(predictor) -> None:
    line = summary(predictor)
    if getattr(predictor, "fallback_reason", None):
        log.warning(line)
    else:
        log.info(line)


def model_info(predictor, path=MODEL_REPORT_PATH) -> dict:
    rep = load_report(path) or {}
    active = getattr(predictor, "name", "formula")
    reason = getattr(predictor, "fallback_reason", None)
    if active == "catboost":
        prob = "классификатор CatBoost (data/model.cbm)"
    elif reason:
        prob = f"логистическая формула — откат: {reason}"
    else:
        prob = "логистическая формула (PREDICTOR=formula)"
    clf, reg = rep.get("classifier"), rep.get("regressor")
    return {
        "summary": summary(predictor, path),
        "active": active, "requested": PREDICTOR, "fallback_reason": reason,
        "synthetic": rep.get("synthetic", True), "note": NOTE,
        "used_at_runtime": {"miss_probability": prob, "departure_shift_and_delays": SHIFT,
                            "shift_regressor": REGRESSOR},
        "trained_at": rep.get("trained_at"), "seed": rep.get("seed"),
        "classifier": {k: clf[k] for k in ("auc", "brier", "n_train", "n_test")} if clf else None,
        "regressor": {k: reg[k] for k in ("mae_h", "n_train", "n_test")} if reg else None,
        "feature_importance": clf.get("feature_importance", []) if clf else [],
    }
