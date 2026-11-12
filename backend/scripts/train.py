"""Обучение моделей на синтетической истории (data/history.csv из scripts/gen_history.py).

- классификатор срыва стыковки (CatBoostClassifier) → data/model.cbm — его использует сервер;
- регрессор сдвига отправления (CatBoostRegressor) → data/model_shift.cbm — только проверка:
  метрика в отчёте и график «прогноз против факта», в расчёт сервера не подключён.
Отложенная выборка 20% (стратифицированная по срыву). Отчёт — data/model_report.json,
графики — docs/pitch/model_calibration.png и docs/pitch/model_pred_vs_fact.png.

В конце модель прогоняется через настоящий движок (storm_north, синтетическая погода) и печатает
вероятности №01–03: допуск ±5 п. п. от 82/74/68% и порядок №01 > №02 > №03. Если не попали —
правим генератор истории, а не ответы модели.

Запуск (из backend/): .venv/Scripts/python scripts/train.py [--regen]
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor, Pool
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, mean_absolute_error, roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gen_history as G  # noqa: E402
from app.util import ru  # noqa: E402

DATA_DIR = ROOT / "data"
PITCH_DIR = ROOT.parent / "docs" / "pitch"
TEST_SIZE = 0.2
# Классификатор: монотонность там, где она очевидна (выше волна, ветер, загрузка, очередь — риск не ниже;
# больше запас — риск не выше), и пониженный вес календаря: месяц и день недели влияют на задержку
# через волну и загрузку порта, а не сами по себе. Без этого прогноз в редкой зоне «шторм + малый
# запас» прыгает от дня недели.
MONOTONE = {"wave_height_m": 1, "wind_ms": 1, "port_congestion": 1, "customs_queue_h": 1, "buffer_hours": -1}
CALENDAR_WEIGHT = {"weekday": 0.1, "month": 0.3}
CLF_PARAMS = {"iterations": 800, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 5,
              "monotone_constraints": MONOTONE,
              "feature_weights": [CALENDAR_WEIGHT.get(f, 1.0) for f in G.FEATURES]}
REG_PARAMS = {"iterations": 600, "depth": 6, "learning_rate": 0.05, "l2_leaf_reg": 3}
EXPECTED_RISK = {"sh-01": 82, "sh-02": 74, "sh-03": 68}
TOLERANCE_PP = 5
NOTE = ("История синтетическая, сгенерирована по правилам (scripts/gen_history.py); метрики показывают "
        "работу конвейера, а не точность на реальных данных.")
LABELS = {"wave_height_m": "Волна", "wind_ms": "Ветер", "port_congestion": "Загрузка порта",
          "customs_queue_h": "Очередь на таможне", "buffer_hours": "Запас до окончания приёма",
          "month": "Месяц", "weekday": "День недели", "cargo_type": "Тип груза", "port_id": "Порт",
          "ice": "Лёд"}


def fit(df: pd.DataFrame, seed: int = G.SEED, clf_params: dict = CLF_PARAMS, reg_params: dict = REG_PARAMS):
    """Обучить обе модели. Возвращает (классификатор, регрессор, метрики, отложенная выборка)."""
    X, y = df[G.FEATURES], df["missed_connection"]
    Xtr, Xte, ytr, yte, str_, ste = train_test_split(X, y, df["departure_shift_h"], test_size=TEST_SIZE,
                                                     random_state=seed, stratify=y)
    common = {"random_seed": seed, "verbose": False, "allow_writing_files": False, "thread_count": 4}
    clf = CatBoostClassifier(loss_function="Logloss", **clf_params, **common)
    clf.fit(Pool(Xtr, ytr, cat_features=G.CAT_FEATURES))
    reg = CatBoostRegressor(loss_function="RMSE", **reg_params, **common)
    reg.fit(Pool(Xtr, str_, cat_features=G.CAT_FEATURES))
    p = clf.predict_proba(Pool(Xte, cat_features=G.CAT_FEATURES))[:, 1]
    s = np.maximum(reg.predict(Pool(Xte, cat_features=G.CAT_FEATURES)), 0)
    metrics = {"auc": round(float(roc_auc_score(yte, p)), 4),
               "brier": round(float(brier_score_loss(yte, p)), 4),
               "mae_h": round(float(mean_absolute_error(ste, s)), 2),
               "n_train": len(Xtr), "n_test": len(Xte),
               "positive_rate_test": round(float(yte.mean()), 4)}
    return clf, reg, metrics, {"y": yte.to_numpy(), "p": p, "shift": ste.to_numpy(), "shift_pred": s}


def importance(model) -> list[dict]:
    imp = model.get_feature_importance()          # PredictionValuesChange, сумма 100
    out = [{"name": n, "label": LABELS[n], "importance": round(float(v), 1)}
           for n, v in zip(model.feature_names_, imp)]
    return sorted(out, key=lambda d: -d["importance"])


def engine_check(model_path: Path) -> dict:
    """storm_north через настоящий движок с этой моделью: вероятности №01–03 и устойчивость к дню недели."""
    from app.clock import FixedClock
    from app.config import SCENARIO_ANCHOR
    from app.predictor import CatBoostPredictor
    from app.state import State
    from app.weather import SyntheticForecast

    pred = CatBoostPredictor(model_path)
    st = State(clock=FixedClock(SCENARIO_ANCHOR), predictor=pred, forecast=SyntheticForecast())
    before = {sid: round(st.shipments[sid]["risk"]["miss_probability"] * 100) for sid in EXPECTED_RISK}
    asyncio.run(st.run_scenario("storm_north"))
    risk = {sid: st.shipments[sid]["risk"] for sid in EXPECTED_RISK}
    pct = {sid: round(r["miss_probability"] * 100) for sid, r in risk.items()}
    # признаки, на которых модель считала №01–03, — для проверки по всем дням недели
    from app import dispatcher as D
    res = {sid: D.predict_route(st, st.shipments[sid], st.shipments[sid]["route"])[0] for sid in EXPECTED_RISK}
    assert all(res[s].miss_probability == risk[s]["miss_probability"] for s in res), "признаки не те"
    feats = {sid: r.features for sid, r in res.items()}
    by_wd = {sid: [round(pred.probability({**f, "weekday": wd}) * 100) for wd in range(7)]
             for sid, f in feats.items()}
    in_tol = all(abs(pct[s] - EXPECTED_RISK[s]) <= TOLERANCE_PP for s in pct)
    order = pct["sh-01"] > pct["sh-02"] > pct["sh-03"]
    wd_ok = all(abs(v - EXPECTED_RISK[s]) <= TOLERANCE_PP for s, row in by_wd.items() for v in row) and all(
        by_wd["sh-01"][d] > by_wd["sh-02"][d] > by_wd["sh-03"][d] for d in range(7))
    return {"storm_north_pct": pct, "expected_pct": EXPECTED_RISK, "tolerance_pp": TOLERANCE_PP,
            "in_tolerance": in_tol, "order_ok": order, "before_storm_pct": before,
            "by_weekday_pct": by_wd, "all_weekdays_ok": wd_ok,
            "drivers_sh01": risk["sh-01"].get("probability_drivers"),
            "true_rate_pct": {sid: round(G.miss_rate(f) * 100, 1) for sid, f in feats.items()}}


def plots(hold: dict, metrics: dict, out_dir: Path) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, grid, blue, surface = "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6", "#fcfcfb"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": muted,
                         "axes.labelcolor": ink, "xtick.color": muted, "ytick.color": muted,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "figure.facecolor": surface, "axes.facecolor": surface})
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    frac, mean = calibration_curve(hold["y"], hold["p"], n_bins=10, strategy="quantile")
    fig, ax = plt.subplots(figsize=(6.4, 5.2), dpi=150)
    ax.grid(color=grid, linewidth=0.8)
    ax.plot([0, 1], [0, 1], color=muted, linewidth=1, linestyle="--", label="Идеальная калибровка")
    ax.plot(mean, frac, color=blue, linewidth=2, marker="o", markersize=7,
            markeredgecolor=surface, markeredgewidth=2, label="Модель")
    ax.set_xlim(0, 1), ax.set_ylim(0, 1)
    ax.set_xlabel("Прогноз модели: вероятность срыва стыковки")
    ax.set_ylabel("Доля срывов на деле")
    ax.set_title(f"Калибровка на отложенной выборке ({metrics['n_test']:,} стыковок)".replace(",", " "),
                 loc="left", color=ink, fontsize=12)
    ax.text(0.98, 0.04, f"AUC {ru(metrics['auc'], 3)} · Brier {ru(metrics['brier'], 3)}\nИстория синтетическая",
            transform=ax.transAxes, ha="right", va="bottom", color=muted, fontsize=10)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    paths.append(out_dir / "model_calibration.png")
    fig.savefig(paths[-1], facecolor=surface)
    plt.close(fig)

    rng = np.random.default_rng(0)
    idx = rng.choice(len(hold["shift"]), size=min(3000, len(hold["shift"])), replace=False)
    fig, ax = plt.subplots(figsize=(6.4, 5.2), dpi=150)
    ax.grid(color=grid, linewidth=0.8)
    top = float(np.percentile(np.concatenate([hold["shift"], hold["shift_pred"]]), 99.5))
    ax.plot([0, top], [0, top], color=muted, linewidth=1, linestyle="--", label="Прогноз = факт")
    ax.scatter(hold["shift"][idx], hold["shift_pred"][idx], s=10, color=blue, alpha=0.35,
               linewidths=0, label="Стыковка")
    ax.set_xlim(0, top), ax.set_ylim(0, top)
    ax.set_xlabel("Факт: сдвиг отправления, ч")
    ax.set_ylabel("Прогноз регрессора, ч")
    ax.set_title("Сдвиг отправления: прогноз против факта", loc="left", color=ink, fontsize=12)
    ax.legend(frameon=False, loc="upper left", markerscale=2)
    n_test = f"{metrics['n_test']:,}".replace(",", " ")
    fig.text(0.02, 0.015, f"MAE {ru(metrics['mae_h'])} ч · 3 000 точек из {n_test}"
             + " · история синтетическая · на сервере регрессор не используется", color=muted, fontsize=8.5)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    paths.append(out_dir / "model_pred_vs_fact.png")
    fig.savefig(paths[-1], facecolor=surface)
    plt.close(fig)
    return paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true", help="пересоздать data/history.csv генератором")
    ap.add_argument("--seed", type=int, default=G.SEED)
    a = ap.parse_args()
    if a.regen or not G.HISTORY_PATH.exists():
        G.generate(G.ROWS, a.seed).to_csv(G.HISTORY_PATH, index=False, lineterminator="\n")
    df = pd.read_csv(G.HISTORY_PATH)
    clf, reg, m, hold = fit(df, a.seed)
    clf.save_model(str(DATA_DIR / "model.cbm"))
    reg.save_model(str(DATA_DIR / "model_shift.cbm"))
    check = engine_check(DATA_DIR / "model.cbm")
    report = {
        "trained_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "synthetic": True, "note": NOTE, "seed": a.seed,
        "history": {"path": "data/history.csv", "rows": len(df),
                    "missed_rate": round(float(df["missed_connection"].mean()), 4),
                    "generator": "scripts/gen_history.py", "params": G.PARAMS},
        "features": G.FEATURES, "cat_features": G.CAT_FEATURES, "test_size": TEST_SIZE,
        "classifier": {"file": "data/model.cbm", "used_at_runtime": True, "params": CLF_PARAMS,
                       "auc": m["auc"], "brier": m["brier"], "n_train": m["n_train"], "n_test": m["n_test"],
                       "positive_rate_test": m["positive_rate_test"], "feature_importance": importance(clf)},
        "regressor": {"file": "data/model_shift.cbm", "used_at_runtime": False, "params": REG_PARAMS,
                      "target": "departure_shift_h", "mae_h": m["mae_h"], "n_train": m["n_train"],
                      "n_test": m["n_test"], "feature_importance": importance(reg)},
        "scenario_check": check,
    }
    (DATA_DIR / "model_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
    for p in plots(hold, m, PITCH_DIR):
        print("график:", p)
    print(f"AUC {m['auc']:.3f} · Brier {m['brier']:.3f} · MAE {m['mae_h']:.1f} ч · "
          f"train {m['n_train']} / test {m['n_test']}")
    print(f"storm_north: {check['storm_north_pct']} (истинная доля в генераторе {check['true_rate_pct']}), "
          f"до шторма {check['before_storm_pct']}, допуск {check['in_tolerance']}, порядок {check['order_ok']}, "
          f"все дни недели {check['all_weekdays_ok']}")
    if not (0.85 <= m["auc"] <= 0.95):
        print("ВНИМАНИЕ: AUC вне 0,85–0,95 — поправьте шум в PARAMS генератора")
    if not (check["in_tolerance"] and check["order_ok"]):
        print("ВНИМАНИЕ: вероятности сценария вне допуска — поправьте генератор истории")
        sys.exit(1)


if __name__ == "__main__":
    main()
