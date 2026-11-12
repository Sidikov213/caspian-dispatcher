"""Геометрия для карты: Edge.path (море по акватории, суша по суше) и Scenario.zone."""
import asyncio

import pytest

# Грубый контур Каспийского моря [lat, lon], по часовой: север → восточный берег → юг → западный берег.
CASPIAN = [
    (46.0, 48.7), (46.5, 49.6), (47.0, 51.0), (47.0, 51.8), (46.6, 52.8), (45.6, 53.0), (45.0, 51.4),
    (44.5, 50.3), (43.65, 51.17), (42.0, 52.6), (41.0, 52.9), (40.0, 53.0), (39.4, 53.2), (38.3, 53.8),
    (37.5, 53.95), (36.9, 54.0), (36.85, 53.37), (36.7, 52.65), (37.47, 49.47), (38.43, 48.89),
    (38.75, 48.88), (39.3, 49.45), (39.95, 49.45), (40.35, 49.9), (40.45, 50.35), (40.6, 49.67),
    (41.1, 49.3), (41.5, 48.95), (42.06, 48.30), (42.98, 47.52), (43.6, 47.5), (44.0, 47.3), (45.0, 47.0),
    (45.5, 47.2), (45.8, 47.9),
]
CASPIAN_FERRIES = {"e-astrakhan-anzali", "e-olya-anzali", "e-olya-amirabad", "e-makhachkala-anzali", "e-aktau-baku"}
NEAR_SEA_LAND = {"e-astrakhan-makhachkala", "e-makhachkala-samur", "e-samur-baku", "e-baku-astara",
                 "e-astara-rasht", "e-anzali-rasht", "e-aktau-incheh", "e-moscow-aktau", "e-amirabad-tehran",
                 "e-incheh-tehran"}


def inside(pt, poly) -> bool:
    """Луч на восток: нечётное число пересечений — внутри."""
    lat, lon = pt
    hit = False
    for (a_lat, a_lon), (b_lat, b_lon) in zip(poly, poly[1:] + poly[:1]):
        if (a_lat > lat) != (b_lat > lat):
            x = a_lon + (lat - a_lat) / (b_lat - a_lat) * (b_lon - a_lon)
            if x > lon:
                hit = not hit
    return hit


@pytest.fixture
def graph(st):
    return st.graph.to_api()


def test_every_edge_has_path(graph):
    for e in graph["edges"]:
        assert e["path"] and all(len(p) == 2 for p in e["path"]), e["id"]


def test_sea_routes_go_by_sea(graph):
    edges = {e["id"]: e for e in graph["edges"]}
    for eid in CASPIAN_FERRIES:
        open_sea = [p for p in edges[eid]["path"] if p[0] < 45.5]   # севернее — Волго-Каспийский канал
        assert open_sea, eid
        for p in open_sea:
            assert inside(p, CASPIAN), (eid, p)


def test_land_routes_stay_on_land(graph):
    edges = {e["id"]: e for e in graph["edges"]}
    for eid in NEAR_SEA_LAND:
        for p in edges[eid]["path"]:
            assert not inside(p, CASPIAN), (eid, p)
    assert edges["e-baku-astara"]["mode"] == "rail"                  # Баку → Астара — по суше, вдоль берега


def test_scenario_zone(st):
    zone = asyncio.run(st.run_scenario("storm_north"))["scenario"]["zone"]
    assert len(zone) >= 3
    nodes = {n["id"]: (n["lat"], n["lon"]) for n in st.graph.to_api()["nodes"]}
    assert inside(nodes["astrakhan"], zone) and inside(nodes["olya"], zone)
    assert not inside(nodes["makhachkala"], zone)                    # обход через Махачкалу — вне шторма


def test_active_scenarios_endpoint(client):
    assert client.get("/api/scenarios").json() == []
    client.post("/api/scenarios", json={"preset": "storm_north"})
    sc = client.get("/api/scenarios").json()
    assert [x["id"] for x in sc] == ["scn-storm-north"] and len(sc[0]["zone"]) >= 3
    client.post("/api/demo/reset")
    assert client.get("/api/scenarios").json() == []
