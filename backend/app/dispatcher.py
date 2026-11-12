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
from html import escape

from . import models as M
from .errors import ApiError
from .graph import KIND_FERRY
from .predictor import PredictContext, PredictorResult
from . import hazards as HZ
from . import negotiation as N
from .card import build_card
from .hazards import note_of
from .livepos import live_position
from .scenarios import make_scenario, public
from .schedule import Ctx, build_legs, make_route, route_end
from .weather import HORIZON_H
from .util import (H, cargo_dative, cargo_dative_words, cargo_word, day_only, day_time, hours, iso,
                   k_rub, num, parse, ru, signed, time_only)


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
    risk = {"miss_probability": res.miss_probability, "level": res.level,
            "departure_shift_h": max(shift, 0), "arrival_delay_h": arrival_delay_h,
            "factors": copy.deepcopy(res.factors)}
    if res.probability_drivers is not None:   # только у CatBoost: объяснение вероятности по SHAP
        risk["probability_drivers"] = copy.deepcopy(res.probability_drivers)
    return risk


def current_leg_of(route: dict) -> int | None:
    for leg in route["legs"]:
        if leg["status"] == "active":
            return leg["index"]
    return None


def set_route(st, sh: dict, route: dict, risk: dict, rerouted: bool | None = None) -> None:
    sh["route"] = route
    sh["risk"] = risk
    sh["risk_level"] = risk["level"]
    if rerouted is not None:
        sh["rerouted"] = rerouted
    sh["eta"] = iso(route_end(route) + H(route["legs"][-1]["predicted_delay_h"]))
    sh["current_leg"] = current_leg_of(route) if sh["stage"] != "planned" else None
    sh["position"] = live_position(st, sh)
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
        out.append({"route": r, "risk": risk_of(res, dep), "tag": route_tag(st, path),
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


# ---------------- наблюдатель угроз → алерт ----------------
#
# Алерт создаёт наблюдатель `watch`: после каждого обновления прогноза, при старте и reset, и после
# запуска сценария. Сценарий не отдельная ветка: он только подменяет прогноз (накладывает шторм или
# затор) и зовёт того же наблюдателя. Угроза — (вид, порт, рейс): у запланированного рейса в ближайшие
# 48 ч в момент отправления волна в порту не ниже предела парома (или порт под затором сценария).
# Одна угроза — один активный алерт. Прогноз изменился существенно → старый алерт superseded, новый.
# Угроза ушла из прогноза до решения → алерт superseded с пометкой «угроза снята».

WATCH_HORIZON_H = 48
CHANGE_H = 3          # окно угрозы сдвинулось на столько часов — прогноз изменился существенно
CHANGE_WAVE_M = 0.5   # или пик волны изменился на столько
NOTE_GONE = "угроза снята"


def storm_window(st, port: str, dep) -> tuple:
    """Непрерывные часы волны не ниже предела вокруг момента отправления: [начало, конец)."""
    lim, w = st.meta["wave_limit_m"], st.weather
    start = parse(dep).replace(minute=0, second=0, microsecond=0)
    while start > st.sim_now and w.wave(port, start - H(1)) >= lim:
        start -= H(1)
    end = w.first_calm(port, dep, lim) or st.sim_now + H(HORIZON_H)
    return start, end


def _scenario_threat(sc: dict, key: tuple, sailing: dict, window: tuple, peak: float) -> dict:
    return {**sc, "_key": key, "_sailing": sailing["id"], "_source": "scenario",
            "_window": (iso(window[0]), iso(window[1])), "_peak": peak}


def threats(st) -> dict[tuple, dict]:
    """Текущие угрозы по прогнозу (с наложенными сценариями). Ключ — (вид, порт, рейс)."""
    lim = st.meta["wave_limit_m"]
    scen = list(st.scenarios.values())
    out: dict[tuple, dict] = {}
    for s in st.sailings.values():
        dep_h = hours(st.sim_now, s["departure"])
        if s["status"] != "scheduled" or not 0 < dep_h <= WATCH_HORIZON_H:
            continue
        port, dep = s["from"], parse(s["departure"])
        if port in st.weather.series and st.weather.wave(port, dep) >= lim:
            start, end = storm_window(st, port, dep)
            peak = round(st.weather.max_wave(port, start, end - H(1)), 2)
            key = ("storm", port, s["id"])
            sc = next((x for x in scen if x.get("_overlay") and port in x["_overlay"]["storm_nodes"]
                       and parse(x["start"]) <= dep < parse(x["end"])), None)
            if sc is not None:
                out[key] = _scenario_threat(sc, key, s, (start, end), peak)
            else:
                name = st.graph.nodes[port]["name"].split(" (")[0].split(" /")[0]
                out[key] = {
                    "id": f"fc-{port}-{s['id']}", "type": "storm", "hazard": "storm",
                    "note": note_of("storm"), "title": f"Шторм у порта {name}",
                    "blocked_edges": [e for e in st.meta["ferry_edges"] if st.graph.edges[e]["from"] == port],
                    "affected_nodes": [port], "start": iso(start), "end": iso(end),
                    "starts_in_h": round(hours(st.sim_now, start)),
                    "params": {"wave_height_m": round(peak, 1), "wind_ms": st.weather.wind(port, dep)},
                    "_key": key, "_sailing": s["id"], "_source": "forecast",
                    "_window": (iso(start), iso(end)), "_peak": peak}
        for sc in scen:   # лёд, затор и таможня: прогноза у них нет, угрозу задаёт сценарий
            if sc["type"] != "storm" and port in sc["affected_nodes"] \
                    and parse(sc["start"]) <= dep <= parse(sc["end"]):
                key = (sc["type"], port, s["id"])
                out[key] = _scenario_threat(sc, key, s, (parse(sc["start"]), parse(sc["end"])), 0.0)
    return out


def _changed(old: dict, new: dict) -> bool:
    if old["_source"] != new["_source"] or old.get("_preset") != new.get("_preset"):
        return True
    (a0, a1), (b0, b1) = old["_window"], new["_window"]
    return (abs(hours(a0, b0)) >= CHANGE_H or abs(hours(a1, b1)) >= CHANGE_H
            or abs(old["_peak"] - new["_peak"]) >= CHANGE_WAVE_M)


NOTE_DECIDED = "по этим грузам решение уже принято"


def hazard_of(sc: dict) -> str:
    """Тип угрозы: из сценария (hazard), у старых угроз — по type."""
    return sc.get("hazard") or ("storm" if sc.get("type") == "storm" else sc.get("type", "storm"))


def close_alert(st, alert: dict, note: str, keep: set[str] = frozenset()) -> None:
    """Алерт больше не актуален: superseded с пометкой; грузы, оставшиеся на плане, — к обычному прогнозу.
    keep — грузы, которые уже взял новый алерт: их маршрут и риск не трогаем."""
    alert["status"], alert["status_note"] = "superseded", note
    alert["card"] = build_card(st, alert)
    internal = st.alert_internal.get(alert["id"], {})
    for it in alert["items"]:
        if it["shipment_id"] in keep:
            continue
        sh = st.shipments.get(it["shipment_id"])
        before = internal.get(it["shipment_id"], {}).get("route_before")
        if sh and before and sh["route"]["id"] == before["id"] and not sh["rerouted"]:
            sh["route"] = copy.deepcopy(before)
            refresh_shipment(st, sh)
            st.emit("shipment.updated", sh)
    st.emit("alert.updated", alert)


def alert_shipments(alert: dict) -> set[str]:
    return {i["shipment_id"] for i in alert["items"]}


def close_overlapping(st, ids: set[str], note: str, keep: set[str] = frozenset(), skip: str | None = None) -> None:
    """Груз входит только в один активный алерт: открытые алерты с этими грузами закрываются."""
    for other in list(st.alerts.values()):
        if other["id"] != skip and other["status"] == "new" and ids & alert_shipments(other):
            close_alert(st, other, note, keep)


def watch(st) -> list[dict]:
    """Сверить угрозы прогноза с алертами: новые — алерт, ушедшие — закрыть, изменившиеся — заменить."""
    current = threats(st)
    for key, aid in list(st.threat_alerts.items()):
        a = st.alerts.get(aid) if aid else None
        if key not in current:
            if a and a["status"] == "new":
                close_alert(st, a, NOTE_GONE)
            del st.threat_alerts[key]
        elif a and a["status"] == "new" and _changed(st.alert_threat[aid], current[key]):
            close_alert(st, a, "прогноз изменился, актуальный алерт ниже")
            del st.threat_alerts[key]
        elif aid is None and current[key]["_source"] == "scenario":
            del st.threat_alerts[key]   # грузов не было, но пришёл сценарий — посмотреть заново
    created = []
    for key, th in current.items():
        if key in st.threat_alerts:
            continue
        alert = build_alert(st, th, quiet_if_empty=th["_source"] == "forecast")
        st.threat_alerts[key] = alert["id"] if alert else None
        if alert:
            created.append(alert)
    if created:
        st.emit("stats.updated", st.stats())
    return created


def run_scenario(st, key: str) -> dict:
    """Сценарий подменяет прогноз и зовёт наблюдателя. Повторный запуск — тот же ответ."""
    if key in st.scenarios:
        sc = st.scenarios[key]
        alert = next(a for a in reversed(list(st.alerts.values())) if a["scenario_id"] == sc["id"])
        return {"scenario": public(sc), "alert": copy.deepcopy(alert)}
    sc = make_scenario(key, st.sim_now)
    st.scenarios[key] = sc
    for sid, free in sc["_sailing_free_t"].items():   # сценарий «мест мало»: на рейсе свободно только free т
        s = st.sailings.get(sid)
        if s:
            s["booked_t"] = max(s["booked_t"], s["capacity_t"] - free)
    st.weather = st.make_weather()
    st.emit("weather.updated", None)
    created = watch(st)
    alert = next((a for a in created if a["scenario_id"] == sc["id"]), None)
    if alert is None:   # угрозы с грузами нет (рейсов в окне нет) — алерт «грузов под риском нет»
        alert = build_alert(st, {**sc, "_source": "scenario"})
    return {"scenario": public(sc), "alert": copy.deepcopy(alert)}


MAX_OPTIONS = 3


def _item(st, base: dict, cand: dict | None, ctx: Ctx) -> tuple[dict, dict | None, float]:
    """Позиция алерта для груза: обход cand или «ждать». (item, риск на новом маршруте, alt_cost)."""
    sh, cur = base["sh"], base["cur"]
    hour_cost = st.meta["hour_cost_rub_per_t"]
    item = {"shipment_id": sh["id"], "from_route": base["from_route"]}
    if cand is None:
        item.update(action="wait", to_route=None, sailing_id=base["dn_sailing"],
                    delay_vs_plan_h=base["dn_delay"], saved_hours=0, saved_rub=0, co2_delta_kg=0)
        return item, None, 0
    r = cand["route"]
    alt_delay = hours(sh["planned_eta"], route_end(r))
    residual = alt_delay * sh["weight_t"] * hour_cost
    surcharge = r["total_cost_rub"] - cur["total_cost_rub"]
    if cand["sailing_id"]:
        ctx.extra_booked[cand["sailing_id"]] = ctx.extra_booked.get(cand["sailing_id"], 0) + sh["weight_t"]
    item.update(action="reroute", to_route=r, sailing_id=cand["sailing_id"],
                delay_vs_plan_h=alt_delay, saved_hours=hours(route_end(r), base["dn_end"]),
                saved_rub=round(base["loss"] - residual - surcharge),
                co2_delta_kg=round(r["total_co2_kg"] - cur["total_co2_kg"], 1))
    return item, cand["risk"], residual + surcharge


def _pick(st, base: dict, ctx: Ctx, banned: set[str], tag: str | None) -> dict | None:
    """Лучший допустимый обход (tag=None) или обход с заданным тегом; None — обход хуже ожидания."""
    for c in candidates(st, base["sh"], ctx, banned):
        if (tag is None or c["tag"] == tag) and route_end(c["route"]) < base["dn_end"]:
            return c
    return None


def totals_of(items: list[dict], co2_plan: dict[str, float]) -> dict:
    rer = [i for i in items if i["action"] == "reroute"]
    co2 = round(sum(i["co2_delta_kg"] for i in rer), 1)
    base = sum(co2_plan[i["shipment_id"]] for i in rer)
    return {"saved_hours": sum(i["saved_hours"] for i in rer), "saved_rub": sum(i["saved_rub"] for i in rer),
            "co2_delta_kg": co2, "co2_delta_pct": round(co2 / base * 100, 1) if base else 0}


def option_title(st, items: list[dict]) -> str:
    rer = [i for i in items if i["action"] == "reroute"]
    if not rer:
        return "Ждать " + _flight(st, items[0]["sailing_id"]) if items else "Ждать"
    r, sid = rer[0]["to_route"], rer[0]["sailing_id"]
    title = via_title(st, r)
    if sid:
        title += f" ({_label(st, sid)}, {day_time(st.sailings[sid]['departure'])})"
    return title


def plan_groups(st, items: list[dict]) -> list[tuple[str, list[dict]]]:
    """Грузы рекомендованного плана по направлениям: [(«Через Махачкалу», [позиции]), …]."""
    groups: dict[str, list[dict]] = {}
    for i in items:
        if i["action"] == "reroute":
            groups.setdefault(via_title(st, i["to_route"]), []).append(i)
    return list(groups.items())


def plan_title(st, items: list[dict]) -> str:
    """«Через Махачкалу — №01 и №03, по западной ветке через Самур и Астару — №02»."""
    parts = [f"{via} — {N.nums([i['shipment_id'] for i in its])}" for via, its in plan_groups(st, items)]
    waits = [i for i in items if i["action"] == "wait"]
    if waits:
        flights = {i["sailing_id"] for i in waits}
        what = _flight(st, waits[0]["sailing_id"]) if len(flights) == 1 else "следующий рейс"
        parts.append(f"ждать {what} — {N.nums([i['shipment_id'] for i in waits])}")
    title = ", ".join(p[:1].lower() + p[1:] for p in parts)
    return title[:1].upper() + title[1:]


def _option(st, oid: str, title: str, items: list[dict], recommended: bool) -> dict:
    rer = [i for i in items if i["action"] == "reroute"]
    route = rer[0]["to_route"] if rer else (items[0]["from_route"] if items else None)
    return {"id": oid, "title": title, "route": copy.deepcopy(route),
            "delay_vs_plan_h": max((i["delay_vs_plan_h"] for i in items), default=0),
            "saved_hours": sum(i["saved_hours"] for i in rer), "saved_rub": sum(i["saved_rub"] for i in rer),
            "co2_delta_kg": round(sum(i["co2_delta_kg"] for i in rer), 1), "recommended": recommended}


def build_alert(st, sc: dict, quiet_if_empty: bool = False) -> dict | None:
    """Алерт по угрозе sc (угроза наблюдателя или сценарий). Угроза наблюдателя задаёт рейс `_sailing`:
    в алерт идут грузы, чья стыковка — этот рейс. quiet_if_empty — без грузов под угрозой алерт не нужен."""
    hour_cost = st.meta["hour_cost_rub_per_t"]
    ctx = st.ctx()
    blocked = set(sc["blocked_edges"])
    banned = banned_edges(st) | blocked
    bases, internal, touched = [], {}, []
    for sh in st.shipments.values():
        if sh["stage"] == "delivered":
            continue
        fi = first_ferry(st, sh["route"])
        if fi is None:
            continue
        leg = sh["route"]["legs"][fi]
        s = st.sailings[leg["sailing_id"]]
        if sc.get("_sailing"):
            if s["id"] != sc["_sailing"]:
                continue
        elif leg["edge_id"] not in blocked and leg["from"] not in sc["affected_nodes"]:
            continue
        elif not parse(sc["start"]) <= parse(s["departure"]) <= parse(sc["end"]):
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
        bases.append({"sh": sh, "cur": cur, "dn_end": dn_end, "dn_sailing": dn_sailing, "dn_delay": dn_delay,
                      "loss": dn_delay * sh["weight_t"] * hour_cost,
                      "from_route": mark_route(cur, blocked, fi, hours(route_end(cur), dn_end))})
        internal[sh["id"]] = {"from_sailing": s["id"], "loss": dn_delay * sh["weight_t"] * hour_cost,
                              "dn_sailing": dn_sailing, "dn_delay": dn_delay, "shift": shift,
                              "p": res.miss_probability, "co2_plan": cur["total_co2_kg"],
                              "weight": sh["weight_t"], "_risk": risk_of(res, s["departure"], dn_delay),
                              "route_before": copy.deepcopy(cur)}

    # варианты: рекомендованный (лучший обход для каждого груза), другие обходы, «ждать»
    options: dict[str, dict] = {}
    rec_items, rec_risks = [], {}
    tags_seen: list[str] = []
    # места на рейсе обхода не хватает всем — сначала считаются грузы, которым оно досталось (N.allocate)
    alloc = N.allocate(st, bases, banned) if sc.get("_negotiate") else None
    order = bases if not alloc else sorted(bases, key=lambda b: b["sh"]["id"] not in alloc["selected"])
    for base in order:
        cand = _pick(st, base, ctx, banned, None)
        if alloc and sc.get("_leftover") == "wait" and base["sh"]["id"] in alloc["left"]:
            cand = None   # настройка пресета: кому не хватило места, ждёт свой рейс, а не едет другим обходом
        item, risk, alt_cost = _item(st, base, cand, ctx)
        rec_items.append(item)
        rec_risks[base["sh"]["id"]] = risk
        internal[base["sh"]["id"]].update(to_risk=risk, alt_cost=alt_cost)
        for c in candidates(st, base["sh"], st.ctx(), banned):
            if c["tag"] not in tags_seen and route_end(c["route"]) < base["dn_end"]:
                tags_seen.append(c["tag"])
    if alloc:
        pos = {b["sh"]["id"]: n for n, b in enumerate(bases)}
        rec_items.sort(key=lambda i: pos[i["shipment_id"]])
    rec_tags = {i["to_route"]["id"].rsplit("-", 1)[-1] if i["to_route"] else None for i in rec_items}
    rer_tags = {next((c["tag"] for c in candidates(st, b["sh"], st.ctx(), banned)
                      if c["route"]["id"] == i["to_route"]["id"]), None)
                for b, i in zip(bases, rec_items) if i["action"] == "reroute"}
    has_reroute = any(i["action"] == "reroute" for i in rec_items)
    if has_reroute:
        rec_id = next(iter(rer_tags)) if len(rer_tags) == 1 and None not in rec_tags else "best"
        options[rec_id] = {"items": rec_items, "risks": rec_risks,
                           "title": option_title(st, rec_items) if rec_id != "best"
                           else (plan_title(st, rec_items) if alloc else "Лучший обход для каждого груза")}
        for tag in tags_seen:
            if len(options) >= MAX_OPTIONS - 1 or tag in options:
                continue
            octx = st.ctx()
            items, risks = [], {}
            for base in bases:
                item, risk, _ = _item(st, base, _pick(st, base, octx, banned, tag), octx)
                items.append(item)
                risks[base["sh"]["id"]] = risk
            if not any(i["action"] == "reroute" for i in items):
                continue
            if [i["to_route"] and i["to_route"]["id"] for i in items] == \
                    [i["to_route"] and i["to_route"]["id"] for i in rec_items]:
                continue
            mixed = alloc and any(i["action"] == "wait" for i in items)
            options[tag] = {"items": items, "risks": risks,
                            "title": plan_title(st, items) if mixed else option_title(st, items)}
    if bases:
        wait_items = [_item(st, b, None, ctx)[0] for b in bases]
        options["wait"] = {"items": wait_items, "risks": {}, "title": option_title(st, wait_items)}
    rec_key = next(iter(options), None)
    if quiet_if_empty and not bases:
        for sid in touched:
            st.emit("shipment.updated", st.shipments[sid])
        return None

    st.seq["alert"] += 1
    aid = f"alert-{st.seq['alert']:03d}"
    items = options[rec_key]["items"] if rec_key else []
    co2_plan = {k: v["co2_plan"] for k, v in internal.items()}
    alert = {
        "id": aid, "scenario_id": sc["id"], "created_at": iso(st.clock.event_ts()),
        "starts_in_h": sc["starts_in_h"],
        "severity": "high" if any(v["_risk"]["level"] == "high" for v in internal.values()) else "medium",
        "title": f"{sc['title']}: {cargo_word(len(items))} под риском" if items
        else f"{sc['title']}: грузов под риском нет",
        "text": "", "items": copy.deepcopy(items),
        "totals": totals_of(items, co2_plan),
        "do_nothing": {"delay_hours": max((v["dn_delay"] for v in internal.values()), default=0),
                       "loss_rub": sum(v["loss"] for v in internal.values())},
        "port_load": port_load(st, [i for i in items if i["action"] == "reroute"]),
        "options": [_option(st, k, o["title"], o["items"], k == rec_key) for k, o in options.items()],
        "status": "new", "accepted_at": None, "accepted_via": None, "accepted_by": None,
        "source": sc.get("_source", "scenario"), "status_note": None,
        "hazard": hazard_of(sc),
    }
    if sc.get("_negotiate") and has_reroute:
        st.alert_alloc[aid] = alloc
        alert["negotiation"] = N.negotiate(st, alert, alloc)
        N.set_deadlines(st, alert, options)
    alert["text"] = alert_text(st, sc, alert, internal)
    ids = {b["sh"]["id"] for b in bases}
    # новая угроза по тем же грузам заменяет прежний алерт: груз входит только в один активный алерт
    close_overlapping(st, ids, f"заменён алертом {aid} ({sc['title']}): угроза по тем же грузам", keep=ids)
    for base in bases:
        set_route(st, base["sh"], base["from_route"], internal[base["sh"]["id"]].pop("_risk"))
    st.alerts[aid] = alert
    st.alert_internal[aid] = internal
    st.alert_options[aid] = options
    st.alert_threat[aid] = {k: v for k, v in sc.items()}
    alert["card"] = build_card(st, alert)
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
    def via_node(r: dict) -> bool:   # в смешанном плане считаются только грузы, идущие через этот порт
        f = first_ferry(st, r)
        return f is not None and r["legs"][f]["from"] == node

    total = sum(st.shipments[i["shipment_id"]]["weight_t"] for i in rer if via_node(i["to_route"]))
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


B0, B1 = "\x01", "\x02"   # метки жирного: для сайта вырезаются, в Telegram — <b>…</b>


def render(text: str, html: bool) -> str:
    if not html:
        return text.replace(B0, "").replace(B1, "")
    return escape(text).replace(B0, "<b>").replace(B1, "</b>")


def alert_text(st, sc: dict, alert: dict, internal: dict, html: bool = False) -> str:
    """Шаблон текста. Позже текст пишет LLM по тем же готовым числам, шаблон остаётся запасным.

    html=False — Alert.text для сайта: без разметки, первая строка с названием сценария.
    html=True  — сообщение Telegram: заголовок там отдельной строкой, поэтому без повтора; блоки
    через пустые строки, жирным — риск, «ничего не делать», обход и расчётная экономия.
    """
    lim = st.meta["wave_limit_m"]
    s, e = parse(sc["start"]), parse(sc["end"])
    span = (f"{day_only(s)} {time_only(s)}–{time_only(e)}" if day_only(s) == day_only(e)
            else f"{day_only(s)} {time_only(s)} – {day_only(e)} {time_only(e)}")
    lead = "" if html else f"⚠️ {sc['title']}: "
    node = sc["affected_nodes"][0]
    head = HZ.alert_head(sc, span, lead, wave_limit=lim, port_load=round(congestion(st, node) * 100),
                         customs_h=customs_h(st, node))
    items = alert["items"]
    if not items:
        return render(head + "\nГрузов, у которых сорвётся стыковка, нет.", html)
    first = internal[items[0]["shipment_id"]]
    fs = st.sailings[first["from_sailing"]]
    n, w = len(items), sum(v["weight"] for v in internal.values())
    lines = [head,
             f"Под риском {_label(st, fs['id'])} {st.graph.nodes[fs['from']]['name']} → "
             f"{st.graph.nodes[fs['to']]['name']} ({day_time(fs['departure'])}): {cargo_word(n)}, {num(w)} т."]
    if html:
        lines.append("")
    lines += [f"Риск срыва стыковки до {B0}{round(max(v['p'] for v in internal.values()) * 100)}%{B1}: "
              f"отправление на {num(max(v['shift'] for v in internal.values()))} ч позже планового рейса.",
              ""]
    dn = alert["do_nothing"]
    wait = (f"если {_flight(st, fs['id'])} отменят, ждать {_flight(st, first['dn_sailing'])}"
            if first["dn_sailing"] else f"если {_flight(st, fs['id'])} отменят, ждать следующий рейс")
    rer = [i for i in items if i["action"] == "reroute"]
    if rer:
        lines.append(f"Ничего не делать: {wait} — прибытие {B0}+{num(dn['delay_hours'])} ч{B1}, "
                     f"задержка обойдётся в {k_rub(dn['loss_rub'])} по {cargo_dative_words(n)}.")
        alloc = st.alert_alloc.get(alert["id"])
        if alloc:   # места на рейсе обхода хватило не всем: кто едет, решено по правилу N.allocate
            lines.append(f"На {_label(st, alloc['sailing_id'], 'пароме').replace('паром ', 'пароме ')} свободно "
                         f"{num(alloc['free_t'])} т из нужных {num(alloc['requested_t'])} т: место получают "
                         f"{N.nums(alloc['selected'])} — так спасено больше груз-часов.")
            for via, its in plan_groups(st, items):
                sid = its[0]["sailing_id"]
                if sid:
                    via += f" ({_label(st, sid)}, {day_time(st.sailings[sid]['departure'])})"
                lines.append(f"{via}: {N.nums([i['shipment_id'] for i in its])}, прибытие "
                             f"{B0}+{num(max(i['delay_vs_plan_h'] for i in its))} ч{B1} к плану.")
            waits = [i for i in items if i["action"] == "wait"]
            if waits:
                lines.append(f"Ждать {_flight(st, waits[0]['sailing_id'])}: "
                             f"{N.nums([i['shipment_id'] for i in waits])}, прибытие "
                             f"{B0}+{num(max(i['delay_vs_plan_h'] for i in waits))} ч{B1} к плану.")
        else:
            r = rer[0]["to_route"]
            sid = rer[0]["sailing_id"]
            via = via_title(st, r)
            if sid:
                via += f" ({_label(st, sid)}, {day_time(st.sailings[sid]['departure'])})"
            alt_cost = sum(internal[i["shipment_id"]]["alt_cost"] for i in rer)
            lines.append(f"{via}: прибытие {B0}+{num(max(i['delay_vs_plan_h'] for i in rer))} ч{B1} к плану, "
                         f"{k_rub(alt_cost)}.")
        t = alert["totals"]
        lines += ["", f"{B0}Расчётная экономия по {cargo_dative(len(rer))}: {num(t['saved_hours'])} груз-часов, "
                      f"{k_rub(t['saved_rub'])}, {signed(t['co2_delta_kg'] / 1000)} т CO₂ "
                      f"({signed(t['co2_delta_pct'])}%).{B1}"]
        pl = alert.get("port_load")
        if pl:
            lines.append(f"Загрузка порта {st.graph.nodes[pl['node_id']]['name']} после переноса: "
                         f"{round(pl['before'] * 100)}% → {round(pl['after'] * 100)}%.")
        steps = alert.get("negotiation")
        if steps:
            lines.append(("Согласовано с цифровыми моделями участников" if N.agreed(steps)
                          else "Согласование с цифровыми моделями участников не завершено")
                         + f" за {len(steps)} {_steps_word(len(steps))}"
                         + (f". Решение можно принять до {day_time(alert['decide_by'])}."
                            if alert.get("decide_by") else "."))
    else:
        lines.append(f"Обхода нет: допустимого маршрута не нашлось, лучший вариант — "
                     f"{wait.split(', ')[-1]}, "
                     f"прибытие {B0}+{num(dn['delay_hours'])} ч{B1}.")
    return render("\n".join(lines), html)


def _steps_word(n: int) -> str:
    """«за 7 шагов», «за 1 шаг», «за 3 шага»."""
    if n % 10 == 1 and n % 100 != 11:
        return "шаг"
    return "шага" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "шагов"


# ---------------- принятие, повтор, ручная смена маршрута ----------------

def _supersede(st, alert: dict, why: str):
    close_alert(st, alert, f"предложение устарело: {why}")
    th = st.alert_threat[alert["id"]]
    new = build_alert(st, th)
    if th.get("_key"):
        st.threat_alerts[th["_key"]] = new["id"]
    raise ApiError(409, "superseded", f"Предложение устарело ({why}). Новый вариант — {new['id']}")


def accept(st, alert_id: str, via: str, option_id: str | None = None, by: dict | None = None) -> dict:
    """Вызывать только под st.lock. option_id=None — рекомендованный вариант.
    by — кто принял {name, role}: вход сайта по Bearer, мини-приложение или бот; без него — None."""
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
    opts = st.alert_options.get(alert_id, {})
    oid = option_id or next((o["id"] for o in alert.get("options", []) if o["recommended"]), None)
    if oid not in opts:
        raise ApiError(404, "option_not_found", f"Варианта {option_id} у алерта {alert_id} нет")
    if oid == "wait" and option_id is not None:  # обход есть, а выбрано «ждать» — это отклонение
        raise ApiError(422, "use_reject", "«Ждать» — это отклонение предложения: POST /alerts/{id}/reject")
    chosen = opts[oid]
    rer = [i for i in chosen["items"] if i["action"] == "reroute"]
    pub = next((o for o in alert.get("options", []) if o["id"] == oid), {})
    if pub.get("decide_by") and st.clock.event_ts() > parse(pub["decide_by"]):
        if N.refresh_availability(st, alert):
            st.emit("alert.updated", alert)
        raise ApiError(409, "decide_by_passed",
                       f"Окно решения закрыто {day_time(pub['decide_by'])}: вариант «{pub['title']}» недоступен, "
                       f"грузы уже не успевают на паром")

    # 0. алерт считали от маршрутов, которые с тех пор могли смениться (другое решение, ручная смена)
    for it in chosen["items"]:
        sh = st.shipments.get(it["shipment_id"])
        if sh is None or sh["route"]["id"] != it["from_route"]["id"]:
            _supersede(st, alert, f"маршрут груза {it['shipment_id']} уже изменён")

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
        if st.weather.closure(s["from"], s["departure"], st.meta["wave_limit_m"]) or \
                ctx.edge_blocked_at(f"e-{s['from']}-{s['to']}", s["departure"]):
            _supersede(st, alert, f"рейс {sid} закрыт")
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
        set_route(st, sh, copy.deepcopy(it["to_route"]), copy.deepcopy(chosen["risks"][sh["id"]]),
                  rerouted=True)
        b = reissue_pass(st, sh, ts)
        if b:
            blocks.append(b)

    # 6. Decision с замороженными числами; stats — сумма Decision
    st.seq["decision"] += 1
    decision = {"id": f"dec-{st.seq['decision']:03d}", "alert_id": alert_id, "ts": ts, "accepted_via": via,
                "accepted_by": copy.deepcopy(by),
                "items": [{"shipment_id": i["shipment_id"], "saved_hours": i["saved_hours"],
                           "saved_rub": i["saved_rub"], "co2_delta_kg": i["co2_delta_kg"],
                           "sailing_id": i["sailing_id"]} for i in rer],
                # служебное, в ответ не попадает: CO₂ исходных маршрутов — база для stats.co2_saved_pct
                "_co2_plan_kg": round(sum(internal[i["shipment_id"]]["co2_plan"] for i in rer), 1)}
    st.decisions.append(decision)
    if chosen["items"] is not alert["items"]:  # принят не рекомендованный вариант — алерт показывает принятое
        alert["items"] = copy.deepcopy(chosen["items"])
        alert["totals"] = totals_of(alert["items"], {k: v["co2_plan"] for k, v in internal.items()})
        for o in alert["options"]:
            o["recommended"] = o["id"] == oid
    alert.update(status="accepted", accepted_at=ts, accepted_via=via, accepted_by=copy.deepcopy(by))
    alert["card"] = build_card(st, alert)
    close_overlapping(st, alert_shipments(alert), NOTE_DECIDED, skip=alert_id)

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
    if new_s != old_s:
        if new_s:
            if ctx.free_t(new_s) < sh["weight_t"]:
                raise ApiError(409, "no_capacity", f"На рейсе {new_s} нет места")
            st.sailings[new_s]["booked_t"] += sh["weight_t"]
        # груз ушёл со старого рейса — бронь снимается всегда, в том числе при уходе на сушу
        if old_s and st.sailings[old_s]["status"] == "scheduled":
            st.sailings[old_s]["booked_t"] -= sh["weight_t"]
    set_route(st, sh, copy.deepcopy(new_route), copy.deepcopy(alt["risk"]),
              rerouted=route_id != st.plan_routes[sid]["id"])
    reissue_pass(st, sh, iso(st.clock.event_ts()))
    # открытые алерты по этому грузу больше не актуальны
    close_overlapping(st, {sid}, "маршрут груза изменён вручную", keep={sid})
    st.emit("shipment.updated", sh)
    st.emit("stats.updated", st.stats())
    return copy.deepcopy(sh)


def plan_new_shipment(st, body: dict) -> dict:
    g = st.graph
    for n in (body["origin"], body["destination"]):
        if n not in g.nodes:
            raise ApiError(422, "node_not_found", f"Пункта {n} нет в графе")
    ctx = st.ctx()
    st.seq["shipment"] += 1
    sid = f"sh-{st.seq['shipment']:02d}"
    # из допустимых путей — с самым ранним прибытием по расписанию (не по сумме базовых часов:
    # иначе паромный маршрут проигрывает суше даже тогда, когда рейс уходит раньше)
    best = None
    for path in g.paths(body["origin"], body["destination"], banned_edges(st)):
        legs, problems = build_legs(ctx, path, st.sim_now, None, body["weight_t"], body["cargo_type"])
        if not problems:
            r = make_route(ctx, f"r-{sid}-plan", legs, body["weight_t"])
            if best is None or route_end(r) < route_end(best):
                best = r
    if best is None:
        st.seq["shipment"] -= 1
        raise ApiError(422, "no_route", "Допустимого маршрута по расписанию нет")
    route = best
    sh = {"id": sid, "title": body["title"], "cargo_type": body["cargo_type"], "weight_t": body["weight_t"],
          "owner_tg_id": st.meta.get("owner_tg_id"), "origin": body["origin"],
          "destination": body["destination"], "stage": "planned", "risk_level": "low", "rerouted": False,
          "display_status": "planned", "position": None, "current_leg": None, "route": route,
          "planned_eta": iso(route_end(route)), "eta": iso(route_end(route)),
          "risk": {"miss_probability": 0, "level": "low", "departure_shift_h": 0, "arrival_delay_h": 0,
                   "factors": []},
          "pass_id": None, "pass_state": "none", "manual": True}
    # место на паромах маршрута бронируется сразу: иначе сценарий переполнит рейс
    for leg in route["legs"]:
        if leg.get("sailing_id"):
            st.sailings[leg["sailing_id"]]["booked_t"] += body["weight_t"]
    st.shipments[sid] = sh
    st.plan_routes[sid] = copy.deepcopy(route)
    refresh_shipment(st, sh)
    st.emit("shipment.updated", sh)
    st.emit("stats.updated", st.stats())
    return copy.deepcopy(sh)
