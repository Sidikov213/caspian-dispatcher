"""Тексты бота — шаблоны. Формат чисел и подписи строго по разделу 9 CLAUDE.md:
«+18 ч», «298 тыс ₽», «−6,7% CO₂», «82%», «12 ноя, 14:30»; базы сравнения — «к плану» и
«против ожидания следующего рейса»; до наступления события — «расчётная экономия».
"""
from html import escape

from .. import dispatcher as D

from ..util import cargo_dative, cargo_word, day_time, hours, k_rub, num, parse, signed, time_only

STATUS = {"planned": ("⚪", "Запланирован"), "in_transit": ("🔵", "В пути"),
          "at_risk": ("🔴", "Под риском"), "rerouted": ("🟢", "Перестроен"), "delivered": ("✅", "Доставлен")}
VIA = {"web": "с сайта", "telegram": "из Telegram"}

BTN_SHIPMENTS = "📦 Мои грузы"
BTN_WEATHER = "🌊 Погода на Каспии"
FOOTER = "<i>Расписание и загрузка портов — демо-данные</i>"


# ---------------- числа ----------------

def h(x: float) -> str:
    """«+18 ч», «−3 ч», «0 ч»."""
    return ("+" if x > 0 else "") + signed(x, 0 if float(x).is_integer() else 1) + " ч" if x else "0 ч"


def pct(p: float) -> str:
    return f"{round(p * 100)}%"


def co2_pct(x: float) -> str:
    return f"{signed(x)}% CO₂"


def ship_no(sid: str) -> str:
    return "№" + sid.split("-")[-1]


def node_name(st, nid: str) -> str:
    return st.graph.nodes[nid]["name"].split(" (")[0]


# ---------------- приветствие ----------------

def welcome(name: str) -> str:
    return (f"👋 {escape(name)}, это <b>Каспийский диспетчер</b>.\n\n"
            "Я вижу угрозы на 48 часов вперёд: шторм, затор в порту, очередь на таможне. Если у груза "
            "сорвётся стыковка с паромом, пришлю готовое решение с часами, рублями и CO₂. "
            "Решение принимаете вы — кнопкой «Принять».\n\n"
            "Внизу кнопки «Мои грузы» и «Погода на Каспии».")


def hint() -> str:
    return ("Я отвечаю на кнопки: «📦 Мои грузы» и «🌊 Погода на Каспии». Алерты с решениями "
            "приходят сами. Свободные вопросы заработают, когда к боту подключат ИИ.")


# ---------------- алерт ----------------

def alert_message(st, alert: dict) -> str:
    """Заголовок отдельной строкой, текст — тот же шаблон движка, что и Alert.text, но с разметкой."""
    icon = "🔴" if alert["severity"] == "high" else "🟠"
    sc = st.alert_threat.get(alert["id"])   # угроза, по которой создан алерт: прогноз или сценарий
    internal = st.alert_internal.get(alert["id"])
    body = (D.alert_text(st, sc, alert, internal, html=True) if sc is not None and internal is not None
            else escape(alert["text"]))
    return f"<b>{icon} {escape(alert['title'])}</b>\n\n{body}"


def alert_suffix(alert: dict) -> str:
    st_ = alert["status"]
    if st_ == "accepted":
        return f"✅ Принято в {time_only(alert['accepted_at'])} {VIA.get(alert['accepted_via'], '')}".rstrip()
    if st_ == "rejected":
        return "✖️ Отклонено: груз ждёт следующий рейс"
    if st_ == "superseded":
        if alert.get("status_note") == "угроза снята":
            return "✅ Угроза снята — решение не нужно"
        return "⌛ Предложение устарело — актуальное ниже"
    return ""


def already(alert: dict) -> str:
    """Короткий ответ на нажатие по обработанному алерту."""
    st_ = alert["status"]
    if st_ == "accepted":
        return f"Уже принято в {time_only(alert['accepted_at'])} {VIA.get(alert['accepted_via'], '')}".rstrip()
    if st_ == "rejected":
        return "Предложение уже отклонено"
    return "Предложение устарело, актуальное — в новом сообщении"


def options_message(alert: dict) -> str:
    """До трёх вариантов, у каждого две строки: «к плану» и «против ожидания следующего рейса»."""
    wait = next((o for o in alert["options"] if o["id"] == "wait"), None)
    wait_h = wait["delay_vs_plan_h"] if wait else alert["do_nothing"]["delay_hours"]
    lines = [f"<b>Варианты по алерту</b> · {cargo_word(len(alert['items']))}", ""]
    for n, o in enumerate(alert["options"], 1):
        star = " ⭐ рекомендуем" if o["recommended"] else ""
        lines.append(f"<b>{n}. {escape(o['title'])}</b>{star}")
        lines.append(f"   Прибытие {h(o['delay_vs_plan_h'])} к плану")
        if o["id"] == "wait":
            lines.append("   Это и есть ожидание следующего рейса, "
                         f"задержка обойдётся в {k_rub(alert['do_nothing']['loss_rub'])}")
        else:
            faster = wait_h - o["delay_vs_plan_h"]
            lines.append(f"   На {num(faster)} ч быстрее ожидания следующего рейса · "
                         f"расчётная экономия {k_rub(o['saved_rub'])}")
        lines.append("")
    lines.append("Выбор принимает вариант для всех грузов алерта.")
    return "\n".join(lines)


def _goes(n: int) -> str:
    return "идёт" if n == 1 else "идут"


def _records(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} запись"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} записи"
    return f"{n} записей"


def checkpoint_name(st, nid: str) -> str:
    kind = {"port": "порт", "border": "пункт пропуска", "station": "станцию"}.get(st.graph.nodes[nid]["type"], "")
    return f"{kind} {node_name(st, nid)}".strip()


def route_line(st, sids: list[str], via: str, sailing_id: str | None, delay: float) -> str:
    """«№01, №02, №03 идут через Махачкалу, паром М, 15 ноя, 06:00, прибытие +6 ч к плану»."""
    parts = [f"{', '.join(ship_no(s) for s in sids)} {_goes(len(sids))} {via[:1].lower() + via[1:]}"]
    if sailing_id:
        parts.append(f"{D._label(st, sailing_id)}, {day_time(st.sailings[sailing_id]['departure'])}")
    parts.append(f"прибытие {h(delay)} к плану")
    return ", ".join(parts)


def accept_summary(st, result: dict) -> str:
    """Итог: строка на грузы с одинаковым маршрутом, строка про пропуска, про реестр, про расчётную
    экономию. Технических id пропусков и хэшей нет."""
    alert, ships, blocks = result["alert"], result["shipments"], result["blocks"]
    t = alert["totals"]
    sailing_of = {i["shipment_id"]: i["sailing_id"] for i in alert["items"]}
    groups: dict[tuple, list[str]] = {}
    for sh in ships:
        key = (D.via_title(st, sh["route"]), sailing_of.get(sh["id"]), hours(sh["planned_eta"], sh["eta"]))
        groups.setdefault(key, []).append(sh["id"])
    lines = ["<b>✅ Решение принято</b>", ""]
    lines += [escape(route_line(st, sids, *key)) for key, sids in groups.items()]

    pending = [sh for sh in ships if sh["pass_state"] == "reissue_pending"]
    done = [sh for sh in ships if sh["pass_state"] != "reissue_pending" and sh["pass_id"]]
    cps: dict[str, list[str]] = {}
    for sh in done:
        cps.setdefault(st.passes[sh["pass_id"]]["checkpoint_node"], []).append(sh["id"])
    parts = []
    if len(cps) == 1:
        word = "Пропуск переоформлен" if len(done) == 1 else "Пропуска переоформлены"
        who = f" ({', '.join(ship_no(sh['id']) for sh in done)})" if pending else ""
        parts.append(f"{word} на {checkpoint_name(st, next(iter(cps)))}{who}")
    elif cps:
        parts.append("Пропуска переоформлены: " + "; ".join(
            f"{', '.join(ship_no(s) for s in sids)} — на {checkpoint_name(st, cp)}" for cp, sids in cps.items()))
    if pending:
        parts.append(f"⚠️ {', '.join(ship_no(sh['id']) for sh in pending)}: пропуск ожидает переоформления, "
                     "старый действует — «Мои грузы» → «Повторить»")
    if parts:
        lines.append("; ".join(parts))

    broken = st.ledger_verify()["broken_at"]
    chain = "цепочка цела" if broken is None else f"цепочка нарушена на записи №{broken}"
    lines.append(f"Реестр: {_records(len(blocks))} о переоформлении, {chain}" if blocks
                 else "Реестр: записи появятся после переоформления пропусков")
    lines.append(f"<b>Расчётная экономия по {cargo_dative(len(ships))}: {num(t['saved_hours'])} груз-часов, "
                 f"{k_rub(t['saved_rub'])}, {co2_pct(t['co2_delta_pct'])}</b>")
    return "\n".join(lines)


def no_proposal_ack(alert: dict) -> str:
    return f"✅ Принято к сведению в {time_only(alert['accepted_at'])}: грузы ждут следующий рейс"


# ---------------- грузы ----------------

def shipment_line(st, sh: dict) -> str:
    icon, label = STATUS[sh["display_status"]]
    head = (f"{icon} <b>{ship_no(sh['id'])} {escape(sh['title'])}</b>, {num(sh['weight_t'])} т · "
            f"{node_name(st, sh['origin'])} → {node_name(st, sh['destination'])}")
    tail = label
    if sh["display_status"] == "at_risk":
        tail += f" {pct(sh['risk']['miss_probability'])}"
        if sh["rerouted"]:
            tail += " · маршрут изменён"
    delay = hours(sh["planned_eta"], sh["eta"])
    eta = f"прибытие {day_time(sh['eta'])}" + (f", {h(delay)} к плану" if delay else "")
    return f"{head}\n   {tail} · {eta}"


def shipments_message(st, ships: list[dict]) -> str:
    lines = ["<b>📦 Мои грузы</b>", ""]
    for sh in ships:
        lines.append(shipment_line(st, sh))
    pending = [sh for sh in ships if sh["pass_state"] == "reissue_pending"]
    if pending:
        lines.append("")
        for sh in pending:
            lines.append(f"⚠️ {ship_no(sh['id'])}: маршрут изменён, пропуск ожидает переоформления")
    lines += ["", FOOTER]
    return "\n".join(lines)


def retry_done(st, result: dict) -> str:
    p, sh = result["pass"], result["shipment"]
    return f"✅ {ship_no(sh['id'])}: пропуск переоформлен на {checkpoint_name(st, p['checkpoint_node'])}, старый отозван"


# ---------------- погода ----------------

def weather_message(st) -> str:
    w = st.weather_out()
    limit = st.meta["wave_limit_m"]
    age = max(0, round(hours(w["updated_at"], st.clock.real_now()) * 60))
    lines = ["<b>🌊 Погода на Каспии</b>", f"Предел волны для парома — {signed(limit)} м", ""]
    for pt in w["points"]:
        nxt = pt["forecast"][:48]
        peak = max(nxt, key=lambda f: f["wave_height_m"])
        flag = "🔴" if peak["wave_height_m"] >= limit else "🟢"
        lines.append(f"{flag} <b>{node_name(st, pt['node_id'])}</b>: сейчас {signed(pt['wave_height_m'])} м, "
                     f"за 48 ч до {signed(peak['wave_height_m'])} м ({day_time(peak['ts'])})")
    stale = " ⚠️" if w["stale"] or age > 60 else ""
    lines += ["", f"Погода обновлена {age} мин назад{stale}", FOOTER]
    return "\n".join(lines)


def ts_of(alert: dict):
    return parse(alert["accepted_at"]) if alert.get("accepted_at") else None
