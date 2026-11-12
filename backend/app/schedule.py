"""Расписание: время этапов по графу и выбор первого подходящего рейса.

Время в узлах (seed.meta.handling_h):
  граница — border_h (24 ч); перед паромом — ferry_before_h (8 ч обработки и таможни), затем ожидание
  рейса; после парома — ferry_after_h (12 ч); перед океанским судном — ocean_before_h (12 ч);
  транзит поезда или авто — 0.

Первый подходящий рейс: статус scheduled, не раньше not_before, груз готов к окончанию приёма,
ребро не закрыто сценарием в момент отправления, волна в порту отправления ниже предела,
свободного места хватает (с учётом предварительных резервов внутри одного расчёта).
"""
import math
from dataclasses import dataclass, field
from datetime import datetime

from .graph import KIND_FERRY, KIND_OCEAN, Graph
from .util import H, hours, iso, parse
from .weather import Weather


@dataclass
class Ctx:
    graph: Graph
    sailings: dict[str, dict]
    weather: Weather
    meta: dict
    scenarios: list[dict]
    sim_now: datetime
    extra_booked: dict[str, float] = field(default_factory=dict)

    @property
    def wave_limit(self) -> float:
        return self.meta["wave_limit_m"]

    def handling(self, key: str) -> float:
        return self.meta["handling_h"][key]

    def free_t(self, sid: str) -> float:
        s = self.sailings[sid]
        return s["capacity_t"] - s["booked_t"] - self.extra_booked.get(sid, 0)

    def edge_blocked_at(self, eid: str, ts) -> bool:
        t = parse(ts)
        return any(eid in sc["blocked_edges"] and parse(sc["start"]) <= t <= parse(sc["end"])
                   for sc in self.scenarios)


def sailings_for(ctx: Ctx, eid: str) -> list[dict]:
    e = ctx.graph.edges[eid]
    return sorted((s for s in ctx.sailings.values() if s["from"] == e["from"] and s["to"] == e["to"]),
                  key=lambda s: s["departure"])


def first_sailing(ctx: Ctx, eid: str, ready, weight_t: float, not_before=None,
                  check_wave: bool = True) -> tuple[dict | None, str | None]:
    """(рейс, None) или (None, причина) — причина первого рейса, который прошёл по окончанию приёма."""
    ready = parse(ready)
    reason = None
    for s in sailings_for(ctx, eid):
        dep = parse(s["departure"])
        if s["status"] != "scheduled":
            continue
        if not_before is not None and dep < parse(not_before):
            continue
        if parse(s["cutoff"]) < ready:
            reason = reason or "cutoff"
            continue
        if ctx.edge_blocked_at(eid, dep):
            reason = reason or "edge_blocked"
            continue
        if check_wave and ctx.weather.wave(s["from"], dep) >= ctx.wave_limit:
            reason = reason or "wave_above_limit"
            continue
        if ctx.free_t(s["id"]) < weight_t:
            reason = reason or "no_capacity"
            continue
        return s, None
    return None, reason or "no_sailing"


def next_departure(ctx: Ctx, eid: str, t: datetime) -> datetime:
    """Плечо с суточным расписанием — первое отправление ≥ t.

    seed.meta.rail_departures_h: {ребро: [часы от «сейчас» сценария]}, дальше каждые 24 ч. Задано
    смещением, а не часами по Москве, чтобы при любом sim_now поезд шёл в том же месте сценария
    (20:00 МСК при якоре 14:00 = +6 ч).
    """
    slots = ctx.meta.get("rail_departures_h", {}).get(eid)
    if not slots:
        return t
    best = None
    for off in slots:
        first = ctx.sim_now + H(off)
        k = max(0, math.ceil(hours(first, t) / 24))
        cand = first + H(24 * k)
        if best is None or cand < best:
            best = cand
    return best


def leg_status(start, end, now) -> str:
    if parse(end) <= now:
        return "done"
    if parse(start) <= now:
        return "active"
    return "pending"


def build_legs(ctx: Ctx, eids: list[str], arrive_at, prev_kind: str | None, weight_t: float,
               cargo_type: str, not_before: dict[int, datetime] | None = None,
               start_index: int = 0) -> tuple[list[dict], list[str]]:
    """Этапы по рёбрам начиная с узла, куда груз прибывает в arrive_at. not_before: {i: время} для рейсов."""
    legs, problems = [], []
    t = parse(arrive_at)
    prev = prev_kind
    for i, eid in enumerate(eids):
        e = ctx.graph.edges[eid]
        kind = ctx.graph.kind(eid)
        if prev is not None and ctx.graph.nodes[e["from"]]["type"] == "border":
            t = t + H(ctx.handling("border_h"))
        if prev == KIND_FERRY:
            t = t + H(ctx.handling("ferry_after_h"))
        sid = None
        if kind == KIND_FERRY:
            if cargo_type in ctx.meta.get("ferry_forbidden_cargo", ()):
                problems.append(f"{eid}:cargo_type")
                return legs, problems
            ready = t + H(ctx.handling("ferry_before_h"))
            s, why = first_sailing(ctx, eid, ready, weight_t, (not_before or {}).get(i))
            if s is None:
                problems.append(f"{eid}:{why}")
                return legs, problems
            sid, start, dur = s["id"], parse(s["departure"]), s["duration_h"]
        elif kind == KIND_OCEAN:
            start, dur = t + H(ctx.handling("ocean_before_h")), e["base_hours"]
        else:
            start, dur = next_departure(ctx, eid, t), e["base_hours"]
        end = start + H(dur)
        legs.append({"index": start_index + i, "edge_id": eid, "from": e["from"], "to": e["to"],
                     "mode": e["mode"], "sailing_id": sid, "planned_start": iso(start),
                     "planned_end": iso(end), "predicted_delay_h": 0,
                     "status": leg_status(start, end, ctx.sim_now)})
        t, prev = end, kind
    return legs, problems


def make_route(ctx: Ctx, rid: str, legs: list[dict], weight_t: float) -> dict:
    eids = [leg["edge_id"] for leg in legs]
    for i, leg in enumerate(legs):
        leg["index"] = i
    return {"id": rid, "legs": legs,
            "total_hours": hours(legs[0]["planned_start"], legs[-1]["planned_end"]),
            "total_cost_rub": round(ctx.graph.cost_rub(eids, weight_t)),
            "total_co2_kg": round(ctx.graph.co2_kg(eids, weight_t), 1),
            "branch": ctx.graph.branch(eids)}


def route_end(route: dict) -> datetime:
    return parse(route["legs"][-1]["planned_end"])
