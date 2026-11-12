"""Положение груза на карте: точка на Edge.path по расписанию этапов маршрута.

Новых расчётов времени нет: берутся planned_start / planned_end этапов — те же, по которым
считается ETA. Момент — sim_now (или переданный `at`, для тестов и ползунка времени).

- этап идёт (start ≤ at < end) — точка на линии ребра (узел → Edge.path → узел) на доле пути
  progress = (at − start) / (end − start), по длине линии, а не по прямой между узлами;
- между этапами (ждёт рейс, граница, перегрузка) — точка в узле, progress 0, mode — следующего этапа,
  waiting: true и причина;
- ещё не выехал (stage planned) или уже прибыл — null.
"""
import math

from .util import iso, parse, hours, H

# Причины ожидания в узле — из существующих статусов: этап blocked, рейс по расписанию, погранпереход.
WAIT_LABELS = {
    "blocked": "Участок закрыт",
    "sailing": "Ждёт рейс",
    "border": "Граница и таможня",
    "transfer": "Перегрузка",
    "arrived": "Конечный пункт",
}


def edge_line(graph, eid: str, from_node: str) -> list[tuple[float, float]]:
    """Линия ребра в направлении движения: узел → Edge.path → узел."""
    e = graph.edges[eid]
    a, b = graph.nodes[e["from"]], graph.nodes[e["to"]]
    pts = [(a["lat"], a["lon"]), *[(p[0], p[1]) for p in (e.get("path") or [])], (b["lat"], b["lon"])]
    return pts[::-1] if from_node == e["to"] and from_node != e["from"] else pts


def _seg_len(p, q) -> float:
    """Длина отрезка в «градусах экватора»: долгота сжата по широте — для долей пути и курса хватает."""
    k = math.cos(math.radians((p[0] + q[0]) / 2))
    return math.hypot(q[0] - p[0], (q[1] - p[1]) * k)


def bearing(p, q) -> float:
    """Курс от p к q, градусы по часовой от севера (0 — север, 90 — восток)."""
    la1, la2 = math.radians(p[0]), math.radians(q[0])
    dl = math.radians(q[1] - p[1])
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return round((math.degrees(math.atan2(y, x)) + 360) % 360, 1) % 360


def point_on(line: list[tuple[float, float]], k: float) -> tuple[tuple[float, float], float]:
    """(точка на доле k длины линии, курс отрезка в этой точке)."""
    k = min(max(k, 0.0), 1.0)
    lens = [_seg_len(p, q) for p, q in zip(line, line[1:])]
    total = sum(lens) or 1.0
    left = k * total
    for (p, q), d in zip(zip(line, line[1:]), lens):
        if d > 0 and left <= d:
            t = left / d
            return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t), bearing(p, q)
        left -= d
    return line[-1], bearing(line[-2], line[-1])


def _wait_reason(graph, leg: dict) -> str:
    if leg["status"] == "blocked":
        return "blocked"
    if leg.get("sailing_id"):
        return "sailing"
    if graph.nodes[leg["from"]]["type"] == "border":
        return "border"
    return "transfer"


def _eta(leg: dict) -> str:
    return iso(parse(leg["planned_end"]) + H(leg.get("predicted_delay_h") or 0))


def _moving(g, leg: dict, now) -> dict:
    start, end = parse(leg["planned_start"]), parse(leg["planned_end"])
    line = edge_line(g, leg["edge_id"], leg["from"])
    k = min(max(hours(start, now) / max(hours(start, end), 1e-9), 0.0), 1.0)
    (lat, lon), head = point_on(line, k)
    return {"lat": round(lat, 4), "lon": round(lon, 4), "edge_id": leg["edge_id"], "mode": leg["mode"],
            "progress": round(k, 4), "heading_deg": head, "from_node": leg["from"], "to_node": leg["to"],
            "eta_next_node": _eta(leg), "waiting": False, "waiting_reason": None, "waiting_label": None}


def _waiting(g, leg: dict, why: str | None = None) -> dict:
    """Стоит в узле отправления этапа leg."""
    line = edge_line(g, leg["edge_id"], leg["from"])
    n = g.nodes[leg["from"]]
    why = why or _wait_reason(g, leg)
    return {"lat": n["lat"], "lon": n["lon"], "edge_id": leg["edge_id"], "mode": leg["mode"],
            "progress": 0.0, "heading_deg": bearing(line[0], line[1]), "from_node": leg["from"],
            "to_node": leg["to"], "eta_next_node": _eta(leg), "waiting": True,
            "waiting_reason": why, "waiting_label": WAIT_LABELS[why]}


def _arrived(g, leg: dict) -> dict:
    """Доехал до конечного узла маршрута (в просмотре): стоит там, статус по-прежнему от sim_now."""
    line = edge_line(g, leg["edge_id"], leg["from"])
    n = g.nodes[leg["to"]]
    return {"lat": n["lat"], "lon": n["lon"], "edge_id": leg["edge_id"], "mode": leg["mode"],
            "progress": 1.0, "heading_deg": bearing(line[-2], line[-1]), "from_node": leg["from"],
            "to_node": leg["to"], "eta_next_node": _eta(leg), "waiting": True,
            "waiting_reason": "arrived", "waiting_label": WAIT_LABELS["arrived"]}


def stop_leg(st, legs: list[dict]) -> tuple[int | None, bool]:
    """(последний этап, до конца которого грузу можно доехать в просмотре; стоит ли груз уже в узле на sim_now).

    Груз не проезжает узел, где его статус должен смениться: порт, погранпереход (таможня), пересадка
    (смена вида транспорта), рейс по расписанию или ожидание между этапами. Через промежуточную станцию
    того же вида транспорта без остановки — едет дальше.
    """
    g, now = st.graph, st.sim_now
    k0 = next((i for i, leg in enumerate(legs) if now < parse(leg["planned_end"])), None)
    if k0 is None:
        return None, False
    if now < parse(legs[k0]["planned_start"]):
        return k0, True
    k = k0
    while k + 1 < len(legs):
        cur, nxt = legs[k], legs[k + 1]
        node = g.nodes[cur["to"]]
        if (node["type"] in ("port", "border") or nxt["mode"] != cur["mode"] or nxt.get("sailing_id")
                or nxt["status"] == "blocked" or parse(nxt["planned_start"]) > parse(cur["planned_end"])):
            break
        k += 1
    return k, False


def live_position(st, sh: dict, at=None, cap: bool = True) -> dict | None:
    """Положение на момент `at` (по умолчанию — часы просмотра st.view_now(), без просмотра это sim_now).

    cap — не дальше ближайшего узла смены статуса (stop_leg): значок не противоречит статусу груза.
    """
    if sh["stage"] != "in_transit":
        return None
    if at is not None:
        now = parse(at)
    else:
        now = st.view_now() if hasattr(st, "view_now") else st.sim_now
    legs = sh["route"]["legs"]
    g = st.graph
    if cap:
        k, waiting_now = stop_leg(st, legs)
        if k is None:
            return None
        if waiting_now:                                  # на sim_now уже стоит в узле — так и стоит
            return _waiting(g, legs[k])
        limit = parse(legs[k]["planned_end"])
        if now >= limit:                                 # доехал до узла смены статуса — стоит
            return _waiting(g, legs[k + 1]) if k + 1 < len(legs) else _arrived(g, legs[k])
        now = max(now, st.sim_now)
    for leg in legs:
        start, end = parse(leg["planned_start"]), parse(leg["planned_end"])
        if now >= end:
            continue
        if now >= start:                                 # этап идёт
            return _moving(g, leg, now)
        return _waiting(g, leg)                          # этап ещё не начался: стоит в узле отправления
    return None                                          # все этапы позади — прибыл
