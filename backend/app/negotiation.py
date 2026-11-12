"""Согласование перевозки с цифровыми моделями участников и «окно спасения».

Прототип многостороннего согласования с криптографически проверяемым журналом. Участники — простые
детерминированные модели (обычный код, без LLM), каждая отвечает на заявку системы:

  ferry   — паром: хватает ли свободного места на рейсе;
  port    — порт: загрузка причала после переноса не выше порога;
  customs — таможня: документы и пропуска грузов готовы;
  rail    — железная дорога: переадресация успевает к окончанию приёма на паром.

Шаг: {actor, action, result: ok | reject | counter, detail, ts, block_index}. reject — участник
отклонил заявку, counter — система скорректировала заявку (встречное предложение), ok — подтверждено.
Каждый шаг пишется отдельной записью в журнал (ledger, event «negotiation»): doc_hash записи —
SHA-256 от содержимого шага, поэтому цепочка хэшей проверяется как раньше.

Кто получает место, когда его не хватает, решает `allocate`: набор грузов, который помещается на рейс
и даёт максимум спасённых груз-часов (при равенстве — максимум расчётной экономии в ₽, затем по номеру).

Работает только у сценариев с флагом `_negotiate` (пресет ice_north_tight): главный сценарий не меняется.
"""
import hashlib
import json
from itertools import combinations

from . import dispatcher as D
from .graph import KIND_FERRY
from .ledger import append_block, verify_chain
from .schedule import route_end
from .util import day_time, hours, num, parse

PORT_LOAD_LIMIT = 0.9      # порог загрузки причала у модели порта
EXACT_LIMIT = 12           # до стольких грузов — полный перебор наборов, дальше — жадно
ACTORS = ("port", "ferry", "customs", "rail")


def nums(ids) -> str:
    """«№01 и №03»."""
    names = [f"№{i[3:]}" for i in ids]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " и " + names[-1]


def titled(st, ids) -> str:
    """«№01 Зерно 60 т и №03 Оборудование 20 т»."""
    parts = [f"№{i[3:]} {st.shipments[i]['title']} {num(st.shipments[i]['weight_t'])} т" for i in ids]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " и " + parts[-1]


# ---------------- кто получает место на рейсе ----------------

def _saved(st, base: dict, cand: dict | None) -> tuple[float, float]:
    """(спасённые часы, расчётная экономия ₽) груза на маршруте cand против ожидания; без cand — нули."""
    if cand is None:
        return 0.0, 0.0
    item, _, _ = D._item(st, base, cand, st.ctx())   # отдельный контекст: резервов не оставляет
    return item["saved_hours"], item["saved_rub"]


def allocate(st, bases: list[dict], banned: set[str]) -> dict | None:
    """Если лучший обход нескольких грузов — один рейс и места на нём не хватает, выбрать, кто едет.

    Правило: набор грузов, который помещается по весу и даёт максимум спасённых груз-часов. Ценность
    места для груза — спасённые часы на этом рейсе минус спасённые часы на его лучшем обходе без этого
    рейса (у кого запасной обход хуже, тому место нужнее). При равенстве — больше расчётная экономия
    в ₽, затем меньшие номера грузов. None — места хватает всем, порядок расчёта не меняется.
    """
    want: dict[str, list[tuple[dict, dict]]] = {}
    for b in bases:
        c = D._pick(st, b, st.ctx(), banned, None)
        if c and c["sailing_id"]:
            want.setdefault(c["sailing_id"], []).append((b, c))
    for sid, pairs in want.items():
        free = st.ctx().free_t(sid)
        need = sum(b["sh"]["weight_t"] for b, _ in pairs)
        if need <= free:
            continue
        rows = []
        for b, c in pairs:
            without = st.ctx()
            without.extra_booked[sid] = st.sailings[sid]["capacity_t"]   # как будто рейса нет
            fb = D._pick(st, b, without, banned, None)
            h, rub = _saved(st, b, c)
            fh, frub = _saved(st, b, fb)
            rows.append({"id": b["sh"]["id"], "w": b["sh"]["weight_t"], "hours": h, "rub": rub,
                         "gain_h": h - fh, "gain_rub": rub - frub})
        rows.sort(key=lambda r: r["id"])
        best, best_key = (), (0.0, 0.0)
        if len(rows) <= EXACT_LIMIT:
            for k in range(1, len(rows) + 1):
                for combo in combinations(rows, k):   # по возрастанию номеров: при равенстве — первый
                    if sum(r["w"] for r in combo) > free:
                        continue
                    key = (sum(r["gain_h"] for r in combo), sum(r["gain_rub"] for r in combo))
                    if key > best_key:
                        best, best_key = combo, key
        else:
            left, picked = free, []
            for r in sorted(rows, key=lambda r: (-r["gain_h"] / r["w"], -r["gain_rub"] / r["w"], r["id"])):
                if r["w"] <= left:
                    picked.append(r)
                    left -= r["w"]
            best = tuple(sorted(picked, key=lambda r: r["id"]))
        selected = [r["id"] for r in best]
        return {"sailing_id": sid, "free_t": free, "requested_t": need,
                "requested": [r["id"] for r in rows], "selected": selected,
                "selected_t": sum(r["w"] for r in best),
                "left": [r["id"] for r in rows if r["id"] not in selected],
                "saved_hours_selected": sum(r["hours"] for r in best),
                "saved_hours_requested": sum(r["hours"] for r in rows)}
    return None


# ---------------- срок решения ----------------

def diverge_start(item: dict) -> str | None:
    """Начало первого этапа нового маршрута, которого нет в прежнем: до этого момента груз ещё можно
    направить по обходу."""
    if item["action"] != "reroute":
        return None
    old = [leg["edge_id"] for leg in item["from_route"]["legs"]]
    for i, leg in enumerate(item["to_route"]["legs"]):
        if i >= len(old) or old[i] != leg["edge_id"]:
            return leg["planned_start"]
    return None


def decide_by_of(items: list[dict]) -> str | None:
    """Срок решения варианта: момент, после которого груз уже не успевает на паром обхода —
    отправление рейса минус оформление и доезд, с учётом расписания поездов и окончания приёма.
    Это отправление последнего поезда, успевающего к окончанию приёма. Вариант без парома — None."""
    starts = [diverge_start(i) for i in items if i["action"] == "reroute" and i["sailing_id"]]
    starts = [s for s in starts if s]
    return min(starts, key=parse) if starts else None


def set_deadlines(st, alert: dict, options: dict) -> None:
    for o in alert["options"]:
        o["decide_by"] = decide_by_of(options[o["id"]]["items"]) if o["id"] != "wait" else None
        o["available"] = True
    rec = next((o for o in alert["options"] if o["recommended"]), None)
    alert["decide_by"] = rec["decide_by"] if rec else None


def refresh_availability(st, alert: dict) -> bool:
    """Пометить варианты, срок которых прошёл. True — что-то изменилось."""
    if alert.get("status") != "new":
        return False
    now, changed = st.clock.event_ts(), False
    for o in alert.get("options", []):
        if o.get("decide_by") and o.get("available", True) and now > parse(o["decide_by"]):
            o["available"] = False
            changed = True
    return changed


# ---------------- шаги согласования ----------------

def _step_hash(alert_id: str, n: int, step: dict) -> str:
    payload = {"alert_id": alert_id, "n": n, **{k: step[k] for k in ("actor", "action", "result", "detail", "ts")}}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ferry(st, alloc: dict | None, rer: list[dict], sid: str) -> list[tuple]:
    s = st.sailings[sid]
    lab = D._label(st, sid, "паром")
    free = st.ctx().free_t(sid)
    ids = [i["shipment_id"] for i in rer if i["sailing_id"] == sid]
    take = sum(st.shipments[i]["weight_t"] for i in ids)
    when = f"{lab} {st.graph.nodes[s['from']]['name']} → {st.graph.nodes[s['to']]['name']}, {day_time(s['departure'])}"
    out = []
    if alloc and alloc["sailing_id"] == sid:
        n = len(alloc["requested"])
        out.append(("ferry", f"Заявка на {num(alloc['requested_t'])} т: {D.cargo_word(n)}, {when}", "reject",
                    f"Свободно {num(alloc['free_t'])} т из нужных {num(alloc['requested_t'])} т: "
                    f"не хватает {num(alloc['requested_t'] - alloc['free_t'])} т"))
        out.append(("ferry", f"Встречное предложение: {num(alloc['selected_t'])} т", "counter",
                    f"Система сократила заявку до {titled(st, alloc['selected'])}: так спасено больше "
                    f"груз-часов ({num(alloc['saved_hours_selected'])} из {num(alloc['saved_hours_requested'])}). "
                    f"{nums(alloc['left'])} на этот рейс не попадает"))
    ok = take <= free
    out.append(("ferry", f"Бронь {num(take)} т: {nums(ids)}", "ok" if ok else "reject",
                f"Место подтверждено, после брони свободно {num(free - take)} т" if ok
                else f"Свободно {num(free)} т из нужных {num(take)} т"))
    return out


def _port(st, alert: dict, rer: list[dict], sid: str) -> tuple:
    node = st.sailings[sid]["from"]
    name = st.graph.nodes[node]["name"]
    pl = alert.get("port_load") or {"before": D.congestion(st, node), "after": D.congestion(st, node)}
    take = sum(st.shipments[i["shipment_id"]]["weight_t"] for i in rer if i["sailing_id"] == sid)
    ok = pl["after"] <= PORT_LOAD_LIMIT
    return ("port", f"Причал порта {name}: обработка {num(take)} т", "ok" if ok else "reject",
            f"Загрузка причала {round(pl['before'] * 100)}% → {round(pl['after'] * 100)}%, "
            f"{'ниже порога' if ok else 'выше порога'} {round(PORT_LOAD_LIMIT * 100)}%")


def _customs(st, rer: list[dict]) -> tuple:
    ids = [i["shipment_id"] for i in rer]
    broken = verify_chain(st.ledger)
    bad = []
    for sid in ids:
        sh = st.shipments[sid]
        p = st.passes.get(sh["pass_id"]) if sh["pass_id"] else None
        block = next((b for b in st.ledger if p and b["hash"] == p["block_hash"]), None)
        if (p is None or p["status"] != "active" or block is None or block["doc_hash"] != p["doc_hash"]
                or (broken is not None and block["index"] >= broken)):
            bad.append(sid)
    if bad:
        return ("customs", f"Готовность документов: {nums(ids)}", "reject",
                f"Нет действующего пропуска или запись о выдаче изменена: {nums(bad)}")
    return ("customs", f"Готовность документов: {nums(ids)}", "ok",
            "Пропуска действуют, хэши документов совпадают с записями журнала. Документы не меняются: "
            "после принятия пропуска переоформляются на новый пункт")


def _name(st, node: str) -> str:
    """Название узла из графа без пояснений: «Самур (граница)» → «Самур», «Баку / Алят» → «Баку»."""
    return st.graph.nodes[node]["name"].split(" (")[0].split(" /")[0]


def _rail(st, rer: list[dict]) -> list[tuple]:
    """Переадресация по суше: грузы группируются по первому новому этапу и ветке нового маршрута.
    Все названия — из графа, по этапам нового маршрута груза."""
    groups: dict[tuple, list[dict]] = {}
    for it in rer:
        old = [leg["edge_id"] for leg in it["from_route"]["legs"]]
        n = next((i for i, x in enumerate(it["to_route"]["legs"]) if i >= len(old) or old[i] != x["edge_id"]), None)
        if n is not None:
            leg = it["to_route"]["legs"][n]
            key = (leg["edge_id"], leg["planned_start"], it["sailing_id"], it["to_route"]["branch"])
            groups.setdefault(key, []).append((it, leg, n))
    out = []
    for (_, _, sid, branch), pairs in groups.items():
        it, leg, n = pairs[0]
        ids = [p[0]["shipment_id"] for p in pairs]
        a, b = _name(st, leg["from"]), _name(st, leg["to"])
        new_legs = it["to_route"]["legs"][n:]
        borders = [x["from"] for x in new_legs if st.graph.nodes[x["from"]]["type"] == "border"]
        if branch == "west" and borders:   # груз уходит на западную ветку: называем по погранпереходам маршрута
            action = (f"Переадресация {nums(ids)} на западную ветку "
                      f"({' — '.join(_name(st, x) for x in borders)})")
            last = max(i for i, x in enumerate(new_legs) if x["from"] == borders[-1])
            path = [new_legs[0]["from"]] + [x["to"] for x in new_legs[:last]]
            out.append(("rail", action, "ok",
                        f"Маршрут {' → '.join(_name(st, x) for x in path)}: отправление "
                        f"{day_time(leg['planned_start'])}, прибытие +{num(it['delay_vs_plan_h'])} ч к плану"))
            continue
        action = f"Переадресация {nums(ids)}: {a} → {b}"
        if sid and st.graph.kind(leg["edge_id"]) != KIND_FERRY:
            s = st.sailings[sid]
            ready = parse(leg["planned_end"]) + D.H(st.meta["handling_h"]["ferry_before_h"])
            spare = hours(ready, s["cutoff"])
            ok = spare >= 0
            out.append(("rail", action, "ok" if ok else "reject",
                        f"Отправление {day_time(leg['planned_start'])}, прибытие {day_time(leg['planned_end'])}; "
                        f"окончание приёма на {D._label(st, sid, 'паром')} — {day_time(s['cutoff'])}, "
                        + (f"запас {num(spare)} ч" if ok else f"опоздание {num(-spare)} ч")))
        else:
            via = D.via_title(st, it["to_route"])
            out.append(("rail", action, "ok",
                        f"{via}: отправление {day_time(leg['planned_start'])}, "
                        f"прибытие +{num(it['delay_vs_plan_h'])} ч к плану"))
    return out


def negotiate(st, alert: dict, alloc: dict | None) -> list[dict]:
    """Шаги согласования рекомендованного варианта. Каждый шаг — запись в журнале."""
    rer = [i for i in alert["items"] if i["action"] == "reroute"]
    if not rer:
        return []
    raw: list[tuple] = []
    sailings = list(dict.fromkeys(i["sailing_id"] for i in rer if i["sailing_id"]))
    for sid in sailings:
        raw += _ferry(st, alloc, rer, sid)
        raw.append(_port(st, alert, rer, sid))
    raw.append(_customs(st, rer))
    raw += _rail(st, rer)

    ts = alert["created_at"]
    first = rer[0]["shipment_id"]
    node = st.sailings[sailings[0]]["from"] if sailings else rer[0]["to_route"]["legs"][-1]["to"]
    steps = []
    for n, (actor, action, result, detail) in enumerate(raw, 1):
        step = {"actor": actor, "action": action, "result": result, "detail": detail, "ts": ts}
        block = append_block(st.ledger, ts, "negotiation", first, node, _step_hash(alert["id"], n, step))
        block.update(alert_id=alert["id"], actor=actor, result=result, action=action)   # вне хэша: всё это в doc_hash
        step["block_index"] = block["index"]
        st.emit("ledger.appended", block)
        steps.append(step)
    return steps


def agreed(steps: list[dict]) -> bool:
    """Согласовано: последний ответ каждого участника — ok."""
    last = {s["actor"]: s["result"] for s in steps}
    return bool(steps) and all(r == "ok" for r in last.values())
