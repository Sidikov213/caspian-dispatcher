"""Shipment.position: точка на Edge.path по расписанию этапов (CLAUDE.md, раздел 4)."""
import asyncio
import copy
import math

from app.livepos import edge_line, live_position
from app.models import Shipment
from app.util import H, parse


def dist_to_segment(p, a, b) -> float:
    """Расстояние от точки до отрезка в градусах (долгота сжата по широте)."""
    k = math.cos(math.radians(p[0]))
    ax, ay, bx, by, px, py = a[1] * k, a[0], b[1] * k, b[0], p[1] * k, p[0]
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def on_line(pos, line, tol=1e-3) -> bool:
    p = (pos["lat"], pos["lon"])
    return min(dist_to_segment(p, a, b) for a, b in zip(line, line[1:])) < tol


def test_point_lies_on_its_edge_path(st):
    moving = [s for s in st.shipments.values() if s["position"]]
    assert moving
    for sh in moving:
        pos = sh["position"]
        assert pos["edge_id"] == sh["route"]["legs"][sh["current_leg"]]["edge_id"]
        line = edge_line(st.graph, pos["edge_id"], pos["from_node"])
        assert len(line) > 2, "у ребра есть Edge.path"
        assert on_line(pos, line), sh["id"]
        assert pos["mode"] == st.graph.edges[pos["edge_id"]]["mode"]
        assert 0 <= pos["progress"] <= 1 and 0 <= pos["heading_deg"] < 360
        Shipment.model_validate(sh)      # контракт


def test_progress_grows_with_sim_now(st):
    sh = st.shipments["sh-01"]
    leg = sh["route"]["legs"][sh["current_leg"]]
    end = parse(leg["planned_end"])
    a = live_position(st, sh)
    b = live_position(st, sh, st.sim_now + H(5))
    c = live_position(st, sh, end - H(1))
    assert a["edge_id"] == b["edge_id"] == c["edge_id"]
    assert a["progress"] < b["progress"] < c["progress"] < 1
    line = edge_line(st.graph, a["edge_id"], a["from_node"])
    assert on_line(b, line) and on_line(c, line)
    assert c["eta_next_node"] == leg["planned_end"]


def test_waiting_in_node_between_legs(st):
    sh = st.shipments["sh-01"]
    legs = sh["route"]["legs"]
    ferry = next(leg for leg in legs if leg["sailing_id"])
    prev = legs[ferry["index"] - 1]
    gap = parse(prev["planned_end"]) + H(1)
    assert gap < parse(ferry["planned_start"]), "между поездом и паромом есть ожидание"
    pos = live_position(st, sh, gap)
    node = st.graph.nodes[ferry["from"]]
    assert pos["waiting"] is True and pos["progress"] == 0
    assert (pos["lat"], pos["lon"]) == (node["lat"], node["lon"])
    assert pos["mode"] == "sea" and pos["edge_id"] == ferry["edge_id"]
    assert pos["waiting_reason"] == "sailing" and pos["waiting_label"] == "Ждёт рейс"


def test_after_accept_point_is_on_new_route(st):
    a = asyncio.run(st.run_scenario("ice_north"))["alert"]
    old = copy.deepcopy(st.shipments["sh-01"]["route"])
    asyncio.run(st.accept(a["id"], "web"))
    sh = st.shipments["sh-01"]
    new = sh["route"]
    assert [leg["edge_id"] for leg in new["legs"]] != [leg["edge_id"] for leg in old["legs"]]
    new_edges = {leg["edge_id"] for leg in new["legs"]}
    assert sh["position"]["edge_id"] in new_edges
    # через несколько часов груз идёт по новому участку, которого в старом маршруте не было
    fresh = next(leg for leg in new["legs"] if leg["edge_id"] not in {x["edge_id"] for x in old["legs"]})
    t = parse(fresh["planned_start"]) + (parse(fresh["planned_end"]) - parse(fresh["planned_start"])) / 2
    pos = live_position(st, sh, t, cap=False)
    assert pos["edge_id"] == fresh["edge_id"] and not pos["waiting"]
    assert on_line(pos, edge_line(st.graph, fresh["edge_id"], fresh["from"]))


def test_delivered_and_planned_have_no_position(st):
    assert st.shipments["sh-05"]["stage"] == "planned" and st.shipments["sh-05"]["position"] is None
    sh = st.shipments["sh-01"]
    after = parse(sh["route"]["legs"][-1]["planned_end"]) + H(1)
    assert live_position(st, sh, after, cap=False) is None
    done = copy.deepcopy(sh)
    done["stage"] = "delivered"
    assert live_position(st, done) is None


def test_api_shipments_carry_position(client):
    rows = client.get("/api/shipments").json()
    by = {s["id"]: s for s in rows}
    assert by["sh-05"]["position"] is None
    p = by["sh-01"]["position"]
    assert {"lat", "lon", "edge_id", "mode", "progress", "heading_deg", "from_node", "to_node",
            "eta_next_node", "waiting"} <= set(p)
