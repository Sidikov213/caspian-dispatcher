"""Предиктивная модель: воспроизводимость истории и обучения, оба предиктора на сценарии, откат на формулу,
GET /api/model. Старые тесты идут на формуле (conftest: PREDICTOR=formula), CatBoost здесь — явно."""
import asyncio
import logging
import sys

import gen_history as G
import gen_mocks as ref
import pytest

from app import main
from app import predictor as P
from app.clock import FixedClock
from app.config import MODEL_PATH, SCENARIO_ANCHOR
from app.democheck import EXPECTED_RISK, RISK_TOLERANCE_PP, run_check
from app.state import State
from app.weather import SyntheticForecast

catboost = pytest.importorskip("catboost")
AFFECTED = ("sh-01", "sh-02", "sh-03")


@pytest.fixture(scope="module")
def cb() -> P.CatBoostPredictor:
    return P.CatBoostPredictor()


def make_state(predictor) -> State:
    return State(clock=FixedClock(SCENARIO_ANCHOR), predictor=predictor, forecast=SyntheticForecast())


def storm(st) -> dict:
    return asyncio.run(st.run_scenario("storm_north"))["alert"]


# ---------------- история и обучение ----------------

def test_history_reproducible_and_matches_runtime_features():
    a, b = G.generate(2000, seed=5), G.generate(2000, seed=5)
    assert a.equals(b)
    assert not a.equals(G.generate(2000, seed=6))
    assert list(a.columns) == G.FEATURES + G.TARGETS
    assert G.FEATURES == P.FEATURES and G.CAT_FEATURES == P.CAT_FEATURES
    # закономерности: до 2 м волна не влияет, в Махачкале нет льда, срыв = сдвиг > 0
    assert a.loc[a.port_id == "makhachkala", "ice"].sum() == 0
    assert ((a.departure_shift_h > 0) <= (a.missed_connection == 1)).all()


def test_training_reproducible():
    import train as T
    df = G.generate(3000, seed=11)
    small = {"iterations": 60, "depth": 4, "learning_rate": 0.1}
    c1, r1, m1, h1 = T.fit(df, 11, small, small)
    c2, r2, m2, h2 = T.fit(df, 11, small, small)
    assert m1 == m2
    assert (h1["p"] == h2["p"]).all() and (h1["shift_pred"] == h2["shift_pred"]).all()


def test_report_metrics_in_range():
    from app.modelinfo import load_report
    rep = load_report()
    assert rep and rep["synthetic"] is True and "синтетическая" in rep["note"]
    assert 0.85 <= rep["classifier"]["auc"] <= 0.95
    assert rep["classifier"]["n_test"] == 6000 and rep["classifier"]["n_train"] == 24000
    assert rep["regressor"]["used_at_runtime"] is False
    assert rep["seed"] == G.SEED and rep["history"]["params"] == G.PARAMS


# ---------------- оба предиктора проходят сценарий ----------------

@pytest.mark.parametrize("kind", ["formula", "catboost"])
def test_scenario_numbers_exact_for_both(kind, cb):
    st = make_state(cb if kind == "catboost" else P.FormulaPredictor())
    alert = storm(st)
    got, want = ref.engine_numbers(st, alert), ref.SCENARIO_DOC
    for name, doc in want.items():
        assert got[name] == pytest.approx(doc), name
    pct = {sid: round(st.shipments[sid]["risk"]["miss_probability"] * 100) for sid in AFFECTED}
    for sid in AFFECTED:
        r = st.shipments[sid]["risk"]
        assert abs(pct[sid] - EXPECTED_RISK[sid]) <= RISK_TOLERANCE_PP, (sid, pct)
        assert r["level"] == "high"
        assert r["departure_shift_h"] == 18 and r["arrival_delay_h"] == 48
        assert [f["impact_hours"] for f in r["factors"]] == [11, 5, 2]   # расчёт, не SHAP
    assert pct["sh-01"] > pct["sh-02"] > pct["sh-03"]
    rec = next(o for o in alert["options"] if o["recommended"])
    assert rec["id"] == "mkh" and rec["delay_vs_plan_h"] == 6
    # текст алерта берёт процент из ответа предиктора
    assert f"Риск срыва стыковки до {pct['sh-01']}%" in alert["text"]
    if kind == "formula":
        assert pct == EXPECTED_RISK and "probability_drivers" not in st.shipments["sh-01"]["risk"]


def test_catboost_probability_drivers(cb):
    st = make_state(cb)
    storm(st)
    for sid in AFFECTED:
        drivers = st.shipments[sid]["risk"]["probability_drivers"]
        assert len(drivers) == 3
        assert all(d["name"] in P.FEATURES and isinstance(d["impact_pp"], float) and d["label"] for d in drivers)
        assert abs(drivers[0]["impact_pp"]) >= abs(drivers[1]["impact_pp"]) >= abs(drivers[2]["impact_pp"])
    top = st.shipments["sh-01"]["risk"]["probability_drivers"][0]
    assert top["name"] in ("wave_height_m", "wind_ms") and top["impact_pp"] > 0
    # ответ проходит модель контракта
    from app import models as M
    M.Shipment.model_validate(st.shipments["sh-01"])


@pytest.mark.parametrize("kind", ["formula", "catboost"])
def test_demo_check_ok_for_both(kind, cb):
    res = run_check(make_state(cb if kind == "catboost" else P.FormulaPredictor()))
    assert res["ok"], res["problems"]
    assert {c["name"] for c in res["checks"]} >= {"calm_start", "risk_sh-01", "risk_order", "saved_rub"}
    calm = next(c for c in res["checks"] if c["name"] == "calm_start")
    assert calm["ok"] and calm["actual"].startswith("0 под риском")


def test_demo_check_calm_start_fails_with_reason():
    class Nervous(P.FormulaPredictor):
        """Риск 90% на любом пароме — и до сценария тоже."""
        def predict(self, ctx):
            r = super().predict(ctx)
            if ctx.port:
                r.miss_probability = 0.9
            return r

    res = run_check(make_state(Nervous()))
    calm = next(c for c in res["checks"] if c["name"] == "calm_start")
    assert not calm["ok"] and not res["ok"] and calm["actual"].startswith("4 под риском")   # №01–03 и №05 на пароме
    first = res["problems"][0]
    assert first.startswith("№01 под риском до сценария: риск 90%, волна в порту Астрахань")
    assert "предел 2,5 м" in first and "запас 2 ч" in first


def test_demo_check_tolerance_and_order():
    class Fixed(P.FormulaPredictor):
        """Вероятности сдвинуты: №01 на +4 п. п. — в допуске, порядок цел."""
        def predict(self, ctx):
            r = super().predict(ctx)
            if ctx.port and r.miss_probability > 0.8:
                r.miss_probability = round(r.miss_probability + 0.04, 2)
            return r

    assert run_check(make_state(Fixed()))["ok"]

    class Swapped(P.FormulaPredictor):
        def predict(self, ctx):
            r = super().predict(ctx)
            if ctx.port and r.miss_probability >= 0.6:
                r.miss_probability = 0.78 if ctx.shipment_id == "sh-01" else 0.79 if ctx.shipment_id == "sh-02" else 0.68
            return r

    res = run_check(make_state(Swapped()))
    bad = {c["name"] for c in res["checks"] if not c["ok"]}
    assert bad == {"risk_order"}
    assert any("порядок рисков" in p for p in res["problems"])


# ---------------- откат на формулу ----------------

def test_fallback_when_model_missing(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("app.config.MODEL_PATH", tmp_path / "nope.cbm")
    with caplog.at_level(logging.WARNING, logger="caspian"):
        p = P.get_predictor("catboost")
    assert p.name == "formula" and "nope.cbm" in p.fallback_reason
    assert "откат на логистическую формулу" in caplog.text
    st = make_state(p)
    storm(st)
    assert round(st.shipments["sh-01"]["risk"]["miss_probability"] * 100) == 82


def test_fallback_when_catboost_not_importable(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "catboost", None)    # import catboost → ImportError
    with caplog.at_level(logging.WARNING, logger="caspian"):
        p = P.get_predictor("catboost")
    assert p.name == "formula" and "catboost не импортируется" in p.fallback_reason
    assert "откат" in caplog.text


def test_selection_by_env():
    assert P.get_predictor("formula").name == "formula"
    assert P.get_predictor("formula").fallback_reason is None
    assert P.get_predictor("catboost").name == "catboost"
    assert MODEL_PATH.exists()
    p = P.get_predictor("xgboost")
    assert p.name == "formula" and "PREDICTOR" in p.fallback_reason


# ---------------- GET /api/model ----------------

def test_api_model(client, cb):
    r = client.get("/api/model").json()
    assert r["summary"] == "Активен предиктор: логистическая формула (PREDICTOR=formula)"
    assert r["active"] == "formula" and r["requested"] == "formula" and r["fallback_reason"] is None
    assert r["synthetic"] is True and "синтетической истории" in r["note"]
    assert 0.85 <= r["classifier"]["auc"] <= 0.95 and r["regressor"]["mae_h"] > 0
    assert r["used_at_runtime"]["departure_shift_and_delays"].startswith("расчёт по прогнозу погоды")
    assert "только проверка" in r["used_at_runtime"]["shift_regressor"]
    assert len(r["feature_importance"]) == len(P.FEATURES)
    old = main.state.predictor
    main.state.predictor = cb
    try:
        r = client.get("/api/model").json()
        assert r["active"] == "catboost"
        assert r["summary"].startswith("Активен предиктор: CatBoost (data/model.cbm") and "AUC 0," in r["summary"]
        assert r["used_at_runtime"]["miss_probability"].startswith("классификатор CatBoost")
    finally:
        main.state.predictor = old


def test_api_shipment_has_drivers_with_catboost(client, cb):
    old = main.state.predictor
    main.state.predictor = cb
    try:
        main.state.reset()
        client.post("/api/scenarios", json={"preset": "storm_north"})
        risk = client.get("/api/shipments/sh-01").json()["risk"]
        assert len(risk["probability_drivers"]) == 3 and risk["factors"][0]["impact_hours"] == 11
    finally:
        main.state.predictor = old
        main.state.reset()
    assert client.get("/api/shipments/sh-01").json()["risk"]["probability_drivers"] is None


def test_mocks_stay_on_formula():
    import json
    from app.config import MOCK_DIR
    sh = {s["id"]: s for s in json.loads((MOCK_DIR / "shipments.storm.json").read_text(encoding="utf-8"))}
    assert [sh[s]["risk"]["miss_probability"] for s in AFFECTED] == [0.82, 0.74, 0.68]
    assert sh["sh-01"]["risk"]["probability_drivers"] is None


def test_committed_history_matches_generator():
    """data/history.csv в git — ровно то, что даёт генератор с seed и PARAMS из отчёта."""
    import pandas as pd
    df = pd.read_csv(G.HISTORY_PATH)
    assert df.to_csv(index=False, lineterminator="\n") == G.generate(G.ROWS, G.SEED).to_csv(
        index=False, lineterminator="\n")


def test_active_predictor_summary_and_startup_log(tmp_path, monkeypatch, caplog):
    from app.modelinfo import log_active, summary
    monkeypatch.setattr("app.config.MODEL_PATH", tmp_path / "nope.cbm")
    fb = P.get_predictor("catboost")
    assert summary(fb).startswith("Активен предиктор: логистическая формула — ОТКАТ с CatBoost: модель не загрузилась")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="caspian"):
        log_active(fb)
    assert caplog.records[-1].levelno == logging.WARNING and "ОТКАТ" in caplog.records[-1].getMessage()


def test_startup_logs_active_predictor_and_calm_start(caplog):
    from fastapi.testclient import TestClient
    with caplog.at_level(logging.INFO, logger="caspian"):
        with TestClient(main.app):
            pass
    assert "Активен предиктор: логистическая формула (PREDICTOR=formula)" in caplog.text
    assert "начальное состояние спокойное — 0 под риском" in caplog.text
