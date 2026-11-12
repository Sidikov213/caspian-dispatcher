"""Alert.card — компактная карточка алерта для клиентов (сайт, приложение, мини-приложение).

Собирается кодом из тех же данных, что Alert.text / items / options / accepted_* — без LLM и без
новой логики: только готовые строки по разделу 9 CLAUDE.md. Alert.text не меняется.

Описание угрозы (заголовок, период, рейс, метрики, охват) фиксируется при создании алерта;
при принятии, отклонении и закрытии пересобираются только decision.
"""
import copy

from . import hazards as HZ
from .util import cargo_word, day_only, day_time, num, time_only

VIA_LABEL = {"web": "сайт", "telegram": "Telegram"}


def _short(name: str) -> str:
    return name.split(" (")[0].split(" /")[0]


def _hours(h: float) -> str:
    return f"+{num(h)} ч" if h > 0 else ("0 ч" if h == 0 else f"−{num(-h)} ч")


def _cut(title: str) -> str:
    return title.split(" (")[0]


def decision(alert: dict) -> dict | None:
    st_ = alert["status"]
    if st_ == "accepted":
        opt = next((o for o in alert.get("options", []) if o.get("recommended")), None)
        title = _cut(opt["title"]) if opt else "Ждать следующий рейс"
        delay = opt["delay_vs_plan_h"] if opt else alert["do_nothing"]["delay_hours"]
        via = alert.get("accepted_via")
        by = alert.get("accepted_by")
        return {"status": "accepted", "title": title, "detail": f"{_hours(delay)} к плану", "via": via,
                "via_label": VIA_LABEL.get(via), "accepted_by_name": by["name"] if by else None}
    if st_ == "rejected":
        return {"status": "rejected", "title": "Ждать следующий рейс",
                "detail": f"{_hours(alert['do_nothing']['delay_hours'])} к плану",
                "via": None, "via_label": None, "accepted_by_name": None}
    return None


def build_card(st, alert: dict) -> dict:
    from . import dispatcher as D   # здесь: dispatcher импортирует этот модуль

    old = alert.get("card")
    if old:                          # описание угрозы уже собрано — обновляется только решение
        card = copy.deepcopy(old)
        card["decision"] = decision(alert)
        return card

    sc = st.alert_threat.get(alert["id"]) or {}
    internal = st.alert_internal.get(alert["id"]) or {}
    hz = alert.get("hazard") or D.hazard_of(sc)
    items = alert["items"]
    n = len(items)

    period = None
    if sc.get("start") and sc.get("end"):
        s0, s1 = sc["start"], sc["end"]
        period = (f"{day_time(s0)}–{time_only(s1)}" if day_only(s0) == day_only(s1)
                  else f"{day_time(s0)} – {day_time(s1)}")

    sid = sc.get("_sailing") or next((v["from_sailing"] for v in internal.values()), None)
    route = None
    if sid and sid in st.sailings:
        s = st.sailings[sid]
        lab = D._label(st, sid, sid)
        route = {"sailing_label": lab[:1].upper() + lab[1:],
                 "from": _short(st.graph.nodes[s["from"]]["name"]), "to": _short(st.graph.nodes[s["to"]]["name"]),
                 "departure": day_time(s["departure"])}

    closure = [f["impact_hours"] for i in items
               for f in st.shipments[i["shipment_id"]]["risk"]["factors"] if f["name"] in ("ice", "wave_height")]
    node = (sc.get("affected_nodes") or [None])[0]
    wave = (sc.get("params") or {}).get("wave_height_m") or sc.get("_peak")
    metrics = HZ.card_metrics(
        hz, closure_h=max(closure) if closure and max(closure) > 0 else None, wave_m=wave,
        wave_limit=st.meta["wave_limit_m"],
        port_load=round(D.congestion(st, node) * 100) if node in st.graph.nodes else None,
        customs_h=D.customs_h(st, node) if node in st.graph.nodes else None)

    return {
        "kind": hz,
        "headline": HZ.headline(sc) if sc else alert["title"],
        "subtitle": f"{cargo_word(n)} под риском" if n else "грузов под риском нет",
        "period": period,
        "metrics": metrics,
        "route": route,
        "impact": {"shipments": n,
                   "weight_t": sum(st.shipments[i["shipment_id"]]["weight_t"] for i in items),
                   "max_risk_pct": round(max((v["p"] for v in internal.values()), default=0) * 100)},
        "note": HZ.note_of(hz),
        "decision": decision(alert),
    }
