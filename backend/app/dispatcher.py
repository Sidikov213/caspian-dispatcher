"""ИИ-диспетчер: конвейер раздела 3 CLAUDE.md. Числа считает код, текст алерта — шаблон (LLM позже).

1. affected — грузы, чей паромный рейс попадает в окно сценария (ребро закрыто или порт затронут)
2. predictor.predict → вероятность срыва, самое раннее отправление, факторы
3. «ничего не делать» — первый рейс по расписанию после самого раннего отправления → задержка
4. graph.paths + schedule → до 3 маршрутов с проверками (волна, рейс, место, окончание приёма, тип груза)
5. лучший — самое раннее прибытие, затем дешевле; расчётная экономия против «ничего не делать»
6. Alert (шаблон текста); нет допустимого маршрута — алерт без предложения (action: wait)
7. accept — одна операция под asyncio.Lock (см. State.accept): статус → повторная проверка и резерв
   места → смена маршрута → новый пропуск → отзыв старого → блок → Decision → stats
8. сбой выпуска пропуска: pass_state = reissue_pending, старый пропуск активен, повтор — retry_pass;
   экономия начисляется один раз (Decision пишется при accept и больше не меняется)

Формулы денег (DEMO_SCENARIO.md, раздел 1), 125 ₽/т·ч — условная стоимость часа задержки:
  задержка при бездействии = ч(план → ждать рейс) × т × 125
  остаточная задержка      = ч(план → обход) × т × 125
  доплата за перевозку     = стоимость обхода − стоимость текущего маршрута
  расчётная экономия       = бездействие − (остаточная + доплата + переоформление 0)
"""
import copy
from collections import defaultdict

from . import models as M
from .errors import ApiError
from .graph import KIND_FERRY
from .predictor import PredictContext, PredictorResult
from .scenarios import make_scenario, public
from .schedule import Ctx, build_legs, make_route, route_end
from .util import (H, cargo_dative, cargo_dative_words, cargo_word, day_only, day_time, hours, iso,
                   k_rub, num, parse, ru, signed, time_only)
from .weather import Weather

ROUTE_TAGS = {"makhachkala": "mkh", "astrakhan": "ast", "olya": "olya", "aktau": "akt", "baku": "baku"}
MAX_ALTERNATIVES = 3


# ---------------- условия в узлах с учётом сценариев ----------------

def congestion(st, node: str) -> float:
    base = st.graph.nodes[node]["congestion"]
    return max([base] + [sc["_congestion"].get(node, 0) for sc in st.scenarios.values()])


def customs_h(st, node: str) -> float:
    base = st.meta["customs_h"]
    return max([base] + [sc["_customs_h"].get(node, 0) for sc in st.scenarios.values()])


def banned_edges(st) -> set[str]:
    return {e for sc in st.scenarios.values() for e in sc["blocked_edges"]}


# ---------------- маршрут: этапы, прогноз ----------------

def first_pending(route: dict) -> int | None:
    for leg in route["legs"]:
        if leg["status"] in ("pending", "blocked"):
            return leg["index"]
    return None


def first_ferry(st, route: dict) -> int | None:
    for leg in route["legs"]:
        if leg["status"] in ("pending", "blocked") and st.graph.kind(leg["edge_id"]) == KIND_FERRY:
            return leg["index"]
    return None


def arrival_before(st, route: dict, i: int):
    """(время прибытия в узел перед этапом i, вид предыдущего этапа)."""
    if i == 0:
        return st.sim_now, None
    prev = route["legs"][i - 1]
    return parse(prev["planned_end"]), st.graph.kind(prev["edge_id"])


def predict_route(st, sh: dict, route: dict) -> tuple[PredictorResult, int | None]:
    fi = first_ferry(st, route)
    base = dict(shipment_id=sh["id"], cargo_type=sh["cargo_type"], weight_t=sh["weight_t"],
                weather=st.weather, wave_limit=st.meta["wave_limit_m"])
    if fi is None:
        legs = route["legs"][first_pending(route) or 0:]
        borders = [st.graph.nodes[leg["from"]]["name"].split(" (")[0] for leg in legs
                   if st.graph.nodes[leg["from"]]["type"] == "border"]
        ctx = PredictContext(**base, customs_h=st.meta["customs_h"], congestion=0.0, borders=borders)
        return st.predictor.predict(ctx), None
    leg = route["legs"][fi]
    s = st.sailings[leg["sailing_id"]]
    arrive, prev_kind = arrival_before(st, route, fi)
    if prev_kind == KIND_FERRY:
        arrive = arrive + H(st.meta["handling_h"]["ferry_after_h"])
    ready = arrive + H(st.meta["handling_h"]["ferry_before_h"])
    port = leg["from"]
    ctx = PredictContext(**base, customs_h=customs_h(st, port), congestion=congestion(st, port),
                         port=port, ready_at=ready, departure=parse(s["departure"]),
                         cutoff=parse(s["cutoff"]))
    return st.predictor.predict(ctx), fi


def risk_of(res: PredictorResult, departure=None, arrival_delay_h: float = 0) -> dict:
    shift = hours(departure, res.earliest_departure) if departure and res.earliest_departure else 0
    return {"miss_probability": res.miss_probability, "level": res.level,
            "departure_shift_h": max(shift, 0), "arrival_delay_h": arrival_delay_h,
            "factors": copy.deepcopy(res.factors)}


def position(st, route: dict, stage: str, origin: str) -> tuple[dict, int | None]:
    if stage == "planned":
        n = st.graph.nodes[origin]
        return {"lat": n["lat"], "lon": n["lon"]}, None
    for leg in route["legs"]:
        if leg["status"] == "active":
            s, e = parse(leg["planned_start"]), parse(leg["planned_end"])
            k = hours(s, st.sim_now) / hours(s, e)
            a, b = st.graph.nodes[leg["from"]], st.graph.nodes[leg["to"]]
            return {"lat": round(a["lat"] + (b["lat"] - a["lat"]) * k, 4),
                    "lon": round(a["lon"] + (b["lon"] - a["lon"]) * k, 4)}, leg["index"]
    n = st.graph.nodes[route["legs"][-1]["to"]]
    return {"lat": n["lat"], "lon": n["lon"]}, None


def set_route(st, sh: dict, route: dict, risk: dict, rerouted: bool | None = None) -> None:
    sh["route"] = route
    sh["risk"] = risk
    sh["risk_level"] = risk["level"]
    if rerouted is not None:
        sh["rerouted"] = rerouted
    sh["eta"] = iso(route_end(route) + H(route["legs"][-1]["predicted_delay_h"]))
    sh["position"], sh["current_leg"] = position(st, route, sh["stage"], sh["origin"])
    sh["display_status"] = M.display_status_of(sh["stage"], sh["risk_level"], sh["rerouted"])


def refresh_shipment(st, sh: dict) -> None:
    """Пересчёт риска по текущему прогнозу (при загрузке сида). Сухопутные маршруты — риск из сида."""
    res, fi = predict_route(st, sh, sh["route"])
    risk = sh["risk"]
    if fi is not None:
        dep = st.sailings[sh["route"]["legs"][fi]["sailing_id"]]["departure"]
        risk = risk_of(res, dep)
    set_route(st, sh, sh["route"], risk)


def checkpoint_of(st, route: dict) -> str:
    """Пункт пропуска: порт первого предстоящего парома или первый предстоящий погранпереход."""
    for leg in route["legs"]:
        if leg["status"] == "done":
            continue
        if leg["status"] != "active" and st.graph.kind(leg["edge_id"]) == KIND_FERRY:
            return leg["from"]
        if st.graph.nodes[leg["from"]]["type"] == "border":
            return leg["from"]
    return route["legs"][-1]["to"]


# ---------------- альтернативы ----------------

def route_tag(st, path: list[str]) -> str:
    if st.graph.branch(path) != "transcaspian":
        return st.graph.branch(path)
    ports = [st.graph.edges[e]["from"] for e in path if st.graph.kind(e) == KIND_FERRY]
    return ROUTE_TAGS.get(ports[0], ports[0]) if ports else "land"


def candidates(st, sh: dict, ctx: Ctx, banned: set[str]) -> list[dict]:
    """До 3 допустимых маршрутов от узла первого предстоящего этапа, кроме текущего. Лучший — первый."""
    route = sh["route"]
    p = first_pending(route)
    if p is None:
        return []
    prefix = copy.deepcopy(route["legs"][:p])
    arrive, prev_kind = arrival_before(st, route, p)
    current = [leg["edge_id"] for leg in route["legs"][p:]]
    out = []
    for path in st.graph.paths(route["legs"][p]["from"], sh["destination"], banned):
        if path == current:
            continue
        legs, problems = build_legs(ctx, path, arrive, prev_kind, sh["weight_t"], sh["cargo_type"],
                                    start_index=p)
        if problems:
            continue
        rid = f"r-{sh['id']}-{route_tag(st, path)}"
        if rid == route["id"]:
            rid += "-2"
        r = make_route(ctx, rid, prefix + legs, sh["weight_t"])
        res, fi = predict_route(st, sh, r)
        dep = st.sailings[r["legs"][fi]["sailing_id"]]["departure"] if fi is not None else None
        out.append({"route": r, "risk": risk_of(res, dep),
                    "sailing_id": r["legs"][fi]["sailing_id"] if fi is not None else None})
    out.sort(key=lambda c: (route_end(c["route"]), c["route"]["total_cost_rub"]))
    return out[:MAX_ALTERNATIVES]


def do_nothing(st, sh: dict, ctx: Ctx, fi: int, earliest) -> tuple[object, str | None]:
    """Ждать: тот же путь, паром — первый рейс после самого раннего отправления. (прибытие, рейс)."""
    route = sh["route"]
    arrive, prev_kind = arrival_before(st, route, fi)
    path = [leg["edge_id"] for leg in route["legs"][fi:]]
    legs, problems = build_legs(ctx, path, arrive, prev_kind, sh["weight_t"], sh["cargo_type"],
                                not_before={0: earliest}, start_index=fi)
    if not problems:
        return parse(legs[-1]["planned_end"]), legs[0]["sailing_id"]
    # В расписании сида подходящего рейса нет: продлеваем его с тем же периодом и сдвигаем хвост.
    sails = [s for s in st.sailings.values()
             if (s["from"], s["to"]) == (route["legs"][fi]["from"], route["legs"][fi]["to"])]
    deps = sorted(parse(s["departure"]) for s in sails)
    period = H(48) if len(deps) < 2 else deps[-1] - deps[-2]
    dep = deps[-1] if deps else parse(earliest)
    while dep < parse(earliest):
        dep += period
    planned_dep = parse(route["legs"][fi]["planned_start"])
    return route_end(route) + (dep - planned_dep), None


def mark_route(route: dict, blocked: set[str], from_index: int, delay_h: float) -> dict:
    r = copy.deepcopy(route)
    for leg in r["legs"][from_index:]:
        leg["predicted_delay_h"] = delay_h
        if leg["edge_id"] in blocked and leg["status"] == "pending":
            leg["status"] = "blocked"
    return r


# ---------------- сценарий → алерт ----------------

def run_scenario(st, key: str) -> dict:
    if key in st.scenarios:
        sc = st.scenarios[key]
        alert = next(a for a in reversed(list(st.alerts.values())) if a["scenario_id"] == sc["id"])
        return {"scenario": public(sc), "alert": copy.deepcopy(alert)}
    sc = make_scenario(key, st.sim_now)
    st.scenarios[key] = sc
    st.weather = Weather(st.sim_now, list(st.scenarios.values()))
    st.emit("weather.updated", None)
    alert = build_alert(st, sc)
    return {"scenario": public(sc), "alert": copy.deepcopy(alert)}


def build_alert(st, sc: dict) -> dict:
    hour_cost = st.meta["hour_cost_rub_per_t"]
    ctx = st.ctx()
    banned = banned_edges(st)
    blocked = set(sc["blocked_edges"])
    items, internal, touched = [], {}, []
    for sh in st.shipments.values():
        if sh["stage"] == "delivered":
            continue
        fi = first_ferry(st, sh["route"])
        if fi is None:
            continue
        leg = sh["route"]["legs"][fi]
        s = st.sailings[leg["sailing_id"]]
        if leg["edge_id"] not in blocked and leg["from"] not in sc["affected_nodes"]:
            continue
        if not parse(sc["start"]) <= parse(s["departure"]) <= parse(sc["end"]):
            continue
        res, _ = predict_route(st, sh, sh["route"])
        shift = hours(s["departure"], res.earliest_departure)
        touched.append(sh["id"])
        if shift <= 0:  # успевает на свой рейс — только обновить риск
            set_route(st, sh, sh["route"], risk_of(res, s["departure"]))
            continue

        cur = sh["route"]
        dn_end, dn_sailing = do_nothing(st, sh, ctx, fi, res.earliest_departure)
        dn_delay = hours(sh["planned_eta"], dn_end)
        loss = dn_delay * sh["weight_t"] * hour_cost
        cands = candidates(st, sh, ctx, banned)
        best = cands[0] if cands and route_end(cands[0]["route"]) < dn_end else None
        from_route = mark_route(cur, blocked, fi, hours(route_end(cur), dn_end))
        item = {"shipment_id": sh["id"], "from_route": from_route}
        if best:
            r = best["route"]
            alt_delay = hours(sh["planned_eta"], route_end(r))
            residual = alt_delay * sh["weight_t"] * hour_cost
            surcharge = r["total_cost_rub"] - cur["total_cost_rub"]
            if best["sailing_id"]:
                ctx.extra_booked[best["sailing_id"]] = ctx.extra_booked.get(best["sailing_id"], 0) + sh["weight_t"]
            item.update(action="reroute", to_route=r, sailing_id=best["sailing_id"],
                        delay_vs_plan_h=alt_delay, saved_hours=hours(route_end(r), dn_end),
                        saved_rub=round(loss - residual - surcharge),
                        co2_delta_kg=round(r["total_co2_kg"] - cur["total_co2_kg"], 1))
        else:
            item.update(action="wait", to_route=None, sailing_id=dn_sailing, delay_vs_plan_h=dn_delay,
                        saved_hours=0, saved_rub=0, co2_delta_kg=0)
            residual = surcharge = 0
        items.append(item)
        internal[sh["id"]] = {"to_risk": best["risk"] if best else None, "from_sailing": s["id"],
                              "loss": loss, "alt_cost": residual + surcharge, "dn_sailing": dn_sailing,
                              "dn_delay": dn_delay, "shift": shift, "p": res.miss_probability,
                              "co2_plan": cur["total_co2_kg"], "weight": sh["weight_t"]}
        set_route(st, sh, from_route, risk_of(res, s["departure"], dn_delay))

    st.seq["alert"] += 1
    aid = f"alert-{st.seq['alert']:03d}"
    rer = [i for i in items if i["action"] == "reroute"]
    co2 = round(sum(i["co2_delta_kg"] for i in rer), 1)
    co2_base = sum(internal[i["shipment_id"]]["co2_plan"] for i in rer)
    alert = {
        "id": aid, "scenario_id": sc["id"], "created_at": iso(st.clock.event_ts()),
        "severity": "high" if any(st.shipments[i["shipment_id"]]["risk_level"] == "high" for i in items)
        else "medium",
        "title": f"{sc['title']}: {cargo_word(len(items))} под риском" if items
        else f"{sc['title']}: грузов под риском нет",
        "text": "", "items": items,
        "totals": {"saved_hours": sum(i["saved_hours"] for i in rer),
                   "saved_rub": sum(i["saved_rub"] for i in rer), "co2_delta_kg": co2,
                   "co2_delta_pct": round(co2 / co2_base * 100, 1) if co2_base else 0},
        "do_nothing": {"delay_hours": max((v["dn_delay"] for v in internal.values()), default=0),
                       "loss_rub": sum(v["loss"] for v in internal.values())},
        "port_load": port_load(st, rer),
        "status": "new", "accepted_at": None, "accepted_via": None,
    }
    alert["text"] = alert_text(st, sc, alert, internal)
    st.alerts[aid] = alert
    st.alert_internal[aid] = internal
    st.emit("alert.created", alert)
    for sid in touched:
        st.emit("shipment.updated", st.shipments[sid])
    st.emit("stats.updated", st.stats())
    return alert


def port_load(st, rer: list[dict]) -> dict | None:
    if not rer:
        return None
    first = rer[0]["to_route"]
    fi = first_ferry(st, first)
    if fi is None:  # обход по суше — порт не нагружаем
        return None
    node = first["legs"][fi]["from"]
    before = congestion(st, node)
    total = sum(st.shipments[i["shipment_id"]]["weight_t"] for i in rer)
    return {"node_id": node, "before": before,
            "after": round(min(before + total / st.meta["port_capacity_t_per_day"], 1), 2)}


def _label(st, sid: str | None, fallback: str = "рейс") -> str:
    return st.meta.get("sailing_labels", {}).get(sid, fallback) if sid else fallback


def _flight(st, sid: str | None) -> str:
    """«паром А» → «рейс А»."""
    lab = _label(st, sid, "")
    return f"рейс {lab.split()[-1]}" if lab else "рейс"


def via_title(st, route: dict) -> str:
    if route["branch"] == "west":
        names = st.meta.get("via_names", {})
        borders = [names.get(leg["from"], st.graph.nodes[leg["from"]]["name"].split(" (")[0])
                   for leg in route["legs"]
                   if leg["status"] != "done" and st.graph.nodes[leg["from"]]["type"] == "border"]
        return "По западной ветке через " + " и ".join(borders) if borders else "По западной ветке"
    fi = first_ferry(st, route)
    port = route["legs"][fi]["from"] if fi is not None else route["legs"][-1]["to"]
    return "Через " + st.meta.get("via_names", {}).get(port, st.graph.nodes[port]["name"])


def alert_text(st, sc: dict, alert: dict, internal: dict) -> str:
    """Шаблон текста. Позже текст пишет LLM по тем же готовым числам, шаблон остаётся запасным."""
    lim = st.meta["wave_limit_m"]
    s, e = parse(sc["start"]), parse(sc["end"])
    span = (f"{day_only(s)} {time_only(s)}–{time_only(e)}" if day_only(s) == day_only(e)
            else f"{day_only(s)} {time_only(s)} – {day_only(e)} {time_only(e)}")
    if sc["type"] == "storm":
        head = (f"⚠️ {sc['title']}: {span}, волна до {ru(sc['params']['wave_height_m'])} м "
                f"(предел парома {ru(lim)} м).")
    else:
        node = sc["affected_nodes"][0]
        head = (f"⚠️ {sc['title']}: {span}, загрузка порта {round(congestion(st, node) * 100)}%, "
                f"таможня до {num(customs_h(st, node))} ч.")
    items = alert["items"]
    if not items:
        return head + "\nГрузов, у которых сорвётся стыковка, нет."
    first = internal[items[0]["shipment_id"]]
    fs = st.sailings[first["from_sailing"]]
    n, w = len(items), sum(v["weight"] for v in internal.values())
    lines = [head,
             f"Под риском {_label(st, fs['id'])} {st.graph.nodes[fs['from']]['name']} → "
             f"{st.graph.nodes[fs['to']]['name']} ({day_time(fs['departure'])}): {cargo_word(n)}, {num(w)} т.",
             f"Риск срыва стыковки до {round(max(v['p'] for v in internal.values()) * 100)}%: "
             f"отправление на {num(max(v['shift'] for v in internal.values()))} ч позже планового рейса.",
             ""]
    dn = alert["do_nothing"]
    wait = (f"если {_flight(st, fs['id'])} отменят, ждать {_flight(st, first['dn_sailing'])}"
            if first["dn_sailing"] else f"если {_flight(st, fs['id'])} отменят, ждать следующий рейс")
    rer = [i for i in items if i["action"] == "reroute"]
    if rer:
        lines.append(f"Ничего не делать: {wait} — прибытие +{num(dn['delay_hours'])} ч, "
                     f"задержка обойдётся в {k_rub(dn['loss_rub'])} по {cargo_dative_words(n)}.")
        r = rer[0]["to_route"]
        sid = rer[0]["sailing_id"]
        via = via_title(st, r)
        if sid:
            via += f" ({_label(st, sid)}, {day_time(st.sailings[sid]['departure'])})"
        alt_cost = sum(internal[i["shipment_id"]]["alt_cost"] for i in rer)
        lines.append(f"{via}: прибытие +{num(max(i['delay_vs_plan_h'] for i in rer))} ч к плану, "
                     f"{k_rub(alt_cost)}.")
        t = alert["totals"]
        lines += ["", f"Расчётная экономия по {cargo_dative(len(rer))}: {num(t['saved_hours'])} груз-часов, "
                      f"{k_rub(t['saved_rub'])}, {signed(t['co2_delta_kg'] / 1000)} т CO₂ "
                      f"({signed(t['co2_delta_pct'])}%)."]
    else:
        lines.append(f"Обхода нет: допустимого маршрута не нашлось, лучший вариант — "
                     f"{wait.split(', ')[-1]}, "
                     f"прибытие +{num(dn['delay_hours'])} ч.")
    return "\n".join(lines)


# ---------------- принятие, повтор, ручная смена маршрута ----------------

def _supersede(st, alert: dict, why: str):
    alert["status"] = "superseded"
    st.emit("alert.updated", alert)
    sc = next(s for s in st.scenarios.values() if s["id"] == alert["scenario_id"])
    new = build_alert(st, sc)
    raise ApiError(409, "superseded", f"Предложение устарело ({why}). Новый вариант — {new['id']}")


def accept(st, alert_id: str, via: str) -> dict:
    """Вызывать только под st.lock."""
    alert = st.alerts.get(alert_id)
    if alert is None:
        raise ApiError(404, "alert_not_found", f"Алерт {alert_id} не найден")
    if alert["status"] == "accepted":
        out = copy.deepcopy(st.accept_results[alert_id])
        out["shipments"] = [copy.deepcopy(st.shipments[s["id"]]) for s in out["shipments"]]
        out["already_accepted"] = True
        return out
    if alert["status"] == "rejected":
        raise ApiError(409, "alert_rejected", "Алерт уже отклонён")
    if alert["status"] == "superseded":
        raise ApiError(409, "superseded", "Предложение устарело, есть новый алерт")
    internal = st.alert_internal[alert_id]
    rer = [i for i in alert["items"] if i["action"] == "reroute"]

    # 1. повторная проверка рейса и резерв места — в той же операции
    ctx = st.ctx()
    need = defaultdict(float)
    for it in rer:
        need[it["sailing_id"]] += st.shipments[it["shipment_id"]]["weight_t"]
    for sid, t in need.items():
        if sid is None:
            continue
        s = st.sailings[sid]
        if s["status"] != "scheduled":
            _supersede(st, alert, f"рейс {sid} {s['status']}")
        if ctx.free_t(sid) < t:
            _supersede(st, alert, f"на рейсе {sid} свободно {ctx.free_t(sid):g} т из нужных {t:g}")
        if st.weather.wave(s["from"], s["departure"]) >= st.meta["wave_limit_m"] or \
                ctx.edge_blocked_at(f"e-{s['from']}-{s['to']}", s["departure"]):
            _supersede(st, alert, f"рейс {sid} закрыт погодой")
    ts = iso(st.clock.event_ts())
    for it in rer:
        w = st.shipments[it["shipment_id"]]["weight_t"]
        if it["sailing_id"]:
            st.sailings[it["sailing_id"]]["booked_t"] += w
        old = st.sailings.get(internal[it["shipment_id"]]["from_sailing"])
        if old and old["status"] == "scheduled":
            old["booked_t"] -= w

    # 2–5. маршрут → новый пропуск → отзыв старого → блок
    blocks = []
    for it in rer:
        sh = st.shipments[it["shipment_id"]]
        set_route(st, sh, copy.deepcopy(it["to_route"]), copy.deepcopy(internal[sh["id"]]["to_risk"]),
                  rerouted=True)
        b = reissue_pass(st, sh, ts)
        if b:
            blocks.append(b)

    # 6. Decision с замороженными числами; stats — сумма Decision
    st.seq["decision"] += 1
    decision = {"id": f"dec-{st.seq['decision']:03d}", "alert_id": alert_id, "ts": ts, "accepted_via": via,
                "items": [{"shipment_id": i["shipment_id"], "saved_hours": i["saved_hours"],
                           "saved_rub": i["saved_rub"], "co2_delta_kg": i["co2_delta_kg"],
                           "sailing_id": i["sailing_id"]} for i in rer]}
    st.decisions.append(decision)
    alert.update(status="accepted", accepted_at=ts, accepted_via=via)

    out = {"alert": copy.deepcopy(alert),
           "shipments": [copy.deepcopy(st.shipments[i["shipment_id"]]) for i in rer],
           "blocks": copy.deepcopy(blocks), "decision": copy.deepcopy(decision), "already_accepted": False}
    st.accept_results[alert_id] = copy.deepcopy(out)
    st.emit("alert.updated", alert)
    for it in rer:
        st.emit("shipment.updated", st.shipments[it["shipment_id"]])
    st.emit("stats.updated", st.stats())
    return out


def reissue_pass(st, sh: dict, ts: str) -> dict | None:
    """Новый пропуск выпускается раньше, чем отзывается старый. Сбой → reissue_pending, старый активен."""
    if not sh["pass_id"]:
        return None
    old = st.passes[sh["pass_id"]]
    try:
        new, block = st.issue_pass(sh["id"], checkpoint_of(st, sh["route"]), "reissued", old["doc_hash"], ts)
    except st.PassIssueError:
        sh["pass_state"] = "reissue_pending"
        return None
    old["status"] = "reissued"
    sh["pass_id"], sh["pass_state"] = new["id"], "active"
    return block


def retry_pass(st, sid: str) -> dict:
    """Вызывать под st.lock. Повтор выпускает пропуск ровно один раз; экономию не трогает."""
    sh = st.get_shipment(sid)
    if sh["pass_state"] == "reissue_pending":
        if reissue_pass(st, sh, iso(st.clock.event_ts())) is None:
            raise ApiError(503, "pass_issue_failed", "Пропуск снова не выпущен, повторите позже")
        st.emit("shipment.updated", sh)
    elif not sh["pass_id"]:
        raise ApiError(404, "no_pass", f"У груза {sid} нет пропуска")
    return {"shipment": copy.deepcopy(sh), "pass": copy.deepcopy(st.passes[sh["pass_id"]])}


def alternatives(st, sid: str) -> list[dict]:
    sh = st.get_shipment(sid)
    plan = st.plan_routes[sid]

    def delta(route, end):
        return {"hours": hours(sh["planned_eta"], end),
                "rub": route["total_cost_rub"] - plan["total_cost_rub"],
                "co2_kg": round(route["total_co2_kg"] - plan["total_co2_kg"], 1)}

    cur = {"route": copy.deepcopy(sh["route"]), "risk": copy.deepcopy(sh["risk"]),
           "delta": delta(sh["route"], parse(sh["eta"])), "recommended": False}
    if first_pending(sh["route"]) is None or sh["stage"] == "delivered":
        cur["recommended"] = True
        return [cur]
    alts = [{"route": c["route"], "risk": c["risk"], "delta": delta(c["route"], route_end(c["route"])),
             "recommended": False} for c in candidates(st, sh, st.ctx(), banned_edges(st))]
    if sh["risk_level"] == "high" and alts and route_end(alts[0]["route"]) < parse(sh["eta"]):
        alts[0]["recommended"] = True
        return [alts[0], cur] + alts[1:]
    cur["recommended"] = True
    return [cur] + alts


def reroute(st, sid: str, route_id: str) -> dict:
    """Ручная смена маршрута логистом (под st.lock). Decision не создаётся — счётчики не меняются."""
    sh = st.get_shipment(sid)
    alt = next((a for a in alternatives(st, sid) if a["route"]["id"] == route_id), None)
    if alt is None:
        raise ApiError(404, "route_not_found", f"Маршрут {route_id} не найден")
    if route_id == sh["route"]["id"]:
        return copy.deepcopy(sh)
    new_route = alt["route"]
    ctx = st.ctx()
    fi_new, fi_old = first_ferry(st, new_route), first_ferry(st, sh["route"])
    new_s = new_route["legs"][fi_new]["sailing_id"] if fi_new is not None else None
    old_s = sh["route"]["legs"][fi_old]["sailing_id"] if fi_old is not None else None
    if new_s and new_s != old_s:
        if ctx.free_t(new_s) < sh["weight_t"]:
            raise ApiError(409, "no_capacity", f"На рейсе {new_s} нет места")
        st.sailings[new_s]["booked_t"] += sh["weight_t"]
        if old_s and st.sailings[old_s]["status"] == "scheduled":
            st.sailings[old_s]["booked_t"] -= sh["weight_t"]
    set_route(st, sh, copy.deepcopy(new_route), copy.deepcopy(alt["risk"]),
              rerouted=route_id != st.plan_routes[sid]["id"])
    reissue_pass(st, sh, iso(st.clock.event_ts()))
    for a in st.alerts.values():  # открытые алерты по этому грузу больше не актуальны
        if a["status"] == "new" and any(i["shipment_id"] == sid for i in a["items"]):
            a["status"] = "superseded"
            st.emit("alert.updated", a)
    st.emit("shipment.updated", sh)
    st.emit("stats.updated", st.stats())
    return copy.deepcopy(sh)


def plan_new_shipment(st, body: dict) -> dict:
    g = st.graph
    for n in (body["origin"], body["destination"]):
        if n not in g.nodes:
            raise ApiError(404, "node_not_found", f"Узел {n} не найден")
    ctx = st.ctx()
    st.seq["shipment"] += 1
    sid = f"sh-{st.seq['shipment']:02d}"
    for path in g.paths(body["origin"], body["destination"], banned_edges(st)):
        legs, problems = build_legs(ctx, path, st.sim_now, None, body["weight_t"], body["cargo_type"])
        if not problems:
            break
    else:
        st.seq["shipment"] -= 1
        raise ApiError(422, "no_route", "Допустимого маршрута по расписанию нет")
    route = make_route(ctx, f"r-{sid}-plan", legs, body["weight_t"])
    sh = {"id": sid, "title": body["title"], "cargo_type": body["cargo_type"], "weight_t": body["weight_t"],
          "owner_tg_id": st.meta.get("owner_tg_id"), "origin": body["origin"],
          "destination": body["destination"], "stage": "planned", "risk_level": "low", "rerouted": False,
          "display_status": "planned", "position": None, "current_leg": None, "route": route,
          "planned_eta": iso(route_end(route)), "eta": iso(route_end(route)),
          "risk": {"miss_probability": 0, "level": "low", "departure_shift_h": 0, "arrival_delay_h": 0,
                   "factors": []},
          "pass_id": None, "pass_state": "none"}
    st.shipments[sid] = sh
    st.plan_routes[sid] = copy.deepcopy(route)
    refresh_shipment(st, sh)
    st.emit("shipment.updated", sh)
    st.emit("stats.updated", st.stats())
    return copy.deepcopy(sh)
