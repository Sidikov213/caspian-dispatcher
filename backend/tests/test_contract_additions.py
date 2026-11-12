"""Дополнения контракта: stats.co2_saved_pct, Scenario.starts_in_h и Alert.starts_in_h."""
import pytest


def test_co2_saved_pct_from_decisions(client):
    assert client.get("/api/stats").json()["co2_saved_pct"] == 0
    alert = client.post("/api/scenarios", json={"preset": "storm_north"}).json()["alert"]
    assert client.get("/api/stats").json()["co2_saved_pct"] == 0          # до решения — ноль
    client.post(f"/api/alerts/{alert['id']}/accept", json={"via": "web"})
    st = client.get("/api/stats").json()
    assert st["co2_saved_pct"] == 6.9 and st["co2_saved_kg"] == 1824      # «−6,9% CO₂» по трём грузам
    assert st["co2_saved_pct"] == -client.get("/api/alerts").json()[0]["totals"]["co2_delta_pct"]
    client.post(f"/api/alerts/{alert['id']}/accept", json={"via": "telegram"})   # повтор не меняет
    assert client.get("/api/stats").json()["co2_saved_pct"] == 6.9


def test_co2_saved_pct_for_non_recommended_option(client):
    alert = client.post("/api/scenarios", json={"preset": "storm_north"}).json()["alert"]
    other = next((o for o in alert["options"] if o["id"] not in ("wait", "mkh")), None)
    if other is None:
        pytest.skip("у алерта нет второго обхода")
    res = client.post(f"/api/alerts/{alert['id']}/accept", json={"via": "web", "option_id": other["id"]}).json()
    assert client.get("/api/stats").json()["co2_saved_pct"] == -res["alert"]["totals"]["co2_delta_pct"]


@pytest.mark.parametrize("preset, hours", [("storm_north", 36), ("storm_full", 36), ("congestion_astrakhan", 18)])
def test_starts_in_h(client, preset, hours):
    out = client.post("/api/scenarios", json={"preset": preset}).json()
    assert out["scenario"]["starts_in_h"] == hours
    assert out["alert"]["starts_in_h"] == hours
    assert client.get("/api/alerts").json()[0]["starts_in_h"] == hours
