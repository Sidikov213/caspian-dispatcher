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
        "active": active, "requested": PREDICTOR, "fallback_reason": reason,
        "synthetic": rep.get("synthetic", True), "note": NOTE,
        "used_at_runtime": {"miss_probability": prob, "departure_shift_and_delays": SHIFT,
                            "shift_regressor": REGRESSOR},
        "trained_at": rep.get("trained_at"), "seed": rep.get("seed"),
        "classifier": {k: clf[k] for k in ("auc", "brier", "n_train", "n_test")} if clf else None,
        "regressor": {k: reg[k] for k in ("mae_h", "n_train", "n_test")} if reg else None,
        "feature_importance": clf.get("feature_importance", []) if clf else [],
    }
