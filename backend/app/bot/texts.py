"""Тексты бота — шаблоны. Формат чисел и подписи строго по разделу 9 CLAUDE.md:
«+18 ч», «298 тыс ₽», «−6,7% CO₂», «82%», «12 ноя, 14:30»; базы сравнения — «к плану» и
«против ожидания следующего рейса»; до наступления события — «расчётная экономия».
"""
from html import escape

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

def alert_message(alert: dict) -> str:
    icon = "🔴" if alert["severity"] == "high" else "🟠"
    return f"<b>{icon} {escape(alert['title'])}</b>\n\n{escape(alert['text'])}"


def alert_suffix(alert: dict) -> str:
    st_ = alert["status"]
    if st_ == "accepted":
        return f"✅ Принято в {time_only(alert['accepted_at'])} {VIA.get(alert['accepted_via'], '')}".rstrip()
    if st_ == "rejected":
        return "✖️ Отклонено: груз ждёт следующий рейс"
    if st_ == "superseded":
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


def accept_summary(st, result: dict) -> str:
    alert, ships, blocks = result["alert"], result["shipments"], result["blocks"]
    t = alert["totals"]
    lines = [f"<b>✅ Решение принято: маршрут перестроен, {cargo_word(len(ships))}</b>", ""]
    for sh in ships:
        legs = sh["route"]["legs"]
        chain = " → ".join([node_name(st, legs[0]["from"])] + [node_name(st, leg["to"]) for leg in legs])
        delay = hours(sh["planned_eta"], sh["eta"])
        lines.append(f"🟢 <b>{ship_no(sh['id'])} {escape(sh['title'])}</b>: {chain}")
        lines.append(f"   Прибытие {day_time(sh['eta'])} · {h(delay)} к плану")
        if sh["pass_state"] == "reissue_pending":
            lines.append("   ⚠️ Пропуск ожидает переоформления — «Мои грузы» → «Повторить»")
        elif sh["pass_id"]:
            p = st.passes[sh["pass_id"]]
            lines.append(f"   Пропуск {p['id']} на пункт {node_name(st, p['checkpoint_node'])}")
    if blocks:
        lines += ["", "Реестр: " + ", ".join(f"запись №{b['index']} ({b['hash'][:8]})" for b in blocks)]
    lines += ["", f"Расчётная экономия по {cargo_dative(len(ships))}: {num(t['saved_hours'])} груз-часов, "
                  f"{k_rub(t['saved_rub'])}, {co2_pct(t['co2_delta_pct'])}"]
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
    return (f"✅ {ship_no(sh['id'])}: пропуск {p['id']} выпущен на пункт {node_name(st, p['checkpoint_node'])}, "
            "старый отозван")


# ---------------- погода ----------------

def weather_message(st) -> str:
    w = st.weather_out()
    limit = st.meta["wave_limit_m"]
    age = round(hours(w["updated_at"], st.sim_now) * 60)
    lines = ["<b>🌊 Погода на Каспии</b>", f"Предел волны для парома — {signed(limit)} м", ""]
    for pt in w["points"]:
        nxt = pt["forecast"][:48]
        peak = max(nxt, key=lambda f: f["wave_height_m"])
        flag = "🔴" if peak["wave_height_m"] >= limit else "🟢"
        lines.append(f"{flag} <b>{node_name(st, pt['node_id'])}</b>: сейчас {signed(pt['wave_height_m'])} м, "
                     f"за 48 ч до {signed(peak['wave_height_m'])} м ({day_time(peak['ts'])})")
    stale = " ⚠️" if age > 60 else ""
    lines += ["", f"Погода обновлена {age} мин назад{stale}", FOOTER]
    return "\n".join(lines)


def ts_of(alert: dict):
    return parse(alert["accepted_at"]) if alert.get("accepted_at") else None
