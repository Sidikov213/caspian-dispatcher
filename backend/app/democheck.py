"""Проверка перед показом (GET /api/demo/check, лог при старте и reset).

Прогоняет storm_north на копии исходного состояния (как сразу после reset, тот же sim_now и тот же
прогноз погоды), живое состояние не трогает. Сверяет ключевые числа с эталоном DEMO_SCENARIO.md
(вероятности — с допуском ±5 п. п. и порядком №01 > №02 > №03, остальное точно), проверяет, что до
сценария ни один груз не «Под риском» (начальное состояние спокойное), и,
если что-то разошлось, объясняет почему: волна, место на пароме, порт после шторма.
"""
import logging

from . import dispatcher as D
from .clock import FixedClock
from .util import day_time, hours, parse, ru

log = logging.getLogger("caspian")

SAILING_A = "sl-ast-anz-1114"
SAILING_M = "sl-mkh-anz-1115"
EXPECTED_RISK = {"sh-01": 82, "sh-02": 74, "sh-03": 68}
RISK_TOLERANCE_PP = 5   # вероятность даёт модель: допуск ±5 п. п. и порядок №01 > №02 > №03
EXPECTED = {"departure_shift_h": 18, "do_nothing_h": 48, "mkh_delay_h": 6,
            "saved_hours": 126, "saved_rub": 596640, "recommended": "mkh"}
NEED_T = 120


def _check(name: str, label: str, expected, actual, tol: float = 1e-6) -> dict:
    ok = actual == expected if isinstance(expected, str) else (
        actual is not None and abs(float(actual) - float(expected)) <= tol)
    return {"name": name, "label": label, "expected": expected, "actual": actual, "ok": ok}


def forecast_quiet(cp) -> dict:
    """Создал ли наблюдатель алерт на текущей погоде до сценария. Не ошибка (шторм бывает и настоящий),
    но проверка говорит об этом прямо: порт, волна, рейс. ok всегда True."""
    found = []
    for a in cp.alerts.values():
        if a.get("source") != "forecast" or a["status"] != "new":
            continue
        th = cp.alert_threat[a["id"]]
        port = cp.graph.nodes[th["affected_nodes"][0]]["name"].split(" (")[0]
        s = cp.sailings[th["_sailing"]]
        found.append(f"{port}: волна до {ru(th['_peak'])} м к отправлению "
                     f"{cp.meta.get('sailing_labels', {}).get(s['id'], s['id'])} ({day_time(s['departure'])}), "
                     f"грузов {len(a['items'])} — {a['id']}")
    actual = "0 алертов по прогнозу" if not found else f"{len(found)} по прогнозу: " + "; ".join(found)
    return {"name": "forecast_quiet",
            "label": "До сценария наблюдатель не создаёт алертов по прогнозу (если создал — это настоящая угроза)",
            "expected": "0 алертов по прогнозу", "actual": actual, "ok": True}


def calm_start(cp) -> tuple[dict, list[str]]:
    """До сценария ни один груз не «Под риском» (на текущей погоде и активном предикторе).
    Возвращает (проверка, причины провала)."""
    bad, problems = [], []
    for sid, sh in sorted(cp.shipments.items()):
        if sh["display_status"] != "at_risk":
            continue
        bad.append(sid)
        res, fi = D.predict_route(cp, sh, sh["route"])
        why = f"риск {round(sh['risk']['miss_probability'] * 100)}%"
        if fi is not None:
            port = sh["route"]["legs"][fi]["from"]
            name = cp.graph.nodes[port]["name"].split(" (")[0]
            f = res.features
            why += (f", волна в порту {name} {ru(f['wave_height_m'])} м (предел {ru(cp.meta['wave_limit_m'])} м), "
                    f"ветер {ru(f['wind_ms'], 0)} м/с, загрузка {round(f['port_congestion'] * 100)}%, "
                    f"запас {ru(f['buffer_hours'], 0)} ч")
        else:
            why += ", сухопутный маршрут"
        problems.append(f"№{sid[3:]} под риском до сценария: {why} (предиктор {cp.predictor.name})")
    top = max(cp.shipments.values(), key=lambda s: s["risk"]["miss_probability"])
    actual = f"{len(bad)} под риском (макс. риск №{top['id'][3:]} {round(top['risk']['miss_probability'] * 100)}%)"
    check = {"name": "calm_start", "label": "Начальное состояние спокойное: до сценария ни один груз не «Под риском»",
             "expected": "0 под риском", "actual": actual, "ok": not bad}
    return check, problems


def run_check(st) -> dict:
    from .state import State  # здесь, чтобы не было циклического импорта
    cp = State(st.seed_path, clock=FixedClock(st.sim_now), predictor=st.predictor, forecast=st.forecast)
    calm, calm_problems = calm_start(cp)
    quiet = forecast_quiet(cp)
    out = D.run_scenario(cp, "storm_north")
    alert, sc = out["alert"], out["scenario"]
    items = {i["shipment_id"]: i for i in alert["items"]}
    rec = next((o for o in alert["options"] if o["recommended"]), None)
    mkh = next((o for o in alert["options"] if o["id"] == "mkh"), None)

    checks = [quiet, calm]
    pct = {sid: round(cp.shipments[sid]["risk"]["miss_probability"] * 100) for sid in EXPECTED_RISK}
    for sid, want in EXPECTED_RISK.items():
        checks.append(_check(f"risk_{sid}", f"Риск №{sid[3:]}, % (±{RISK_TOLERANCE_PP} п. п.)", want, pct[sid],
                             RISK_TOLERANCE_PP))
    order = " > ".join(str(pct[s]) for s in EXPECTED_RISK)
    checks.append({"name": "risk_order", "label": "Порядок рисков №01 > №02 > №03", "expected": "№01 > №02 > №03",
                   "actual": order, "ok": pct["sh-01"] > pct["sh-02"] > pct["sh-03"]})
    checks += [
        _check("departure_shift_h", "Отправление позже планового рейса, ч", EXPECTED["departure_shift_h"],
               cp.shipments["sh-01"]["risk"]["departure_shift_h"]),
        _check("do_nothing_h", "Ничего не делать, ч", EXPECTED["do_nothing_h"], alert["do_nothing"]["delay_hours"]),
        _check("mkh_delay_h", "Через Махачкалу к плану, ч", EXPECTED["mkh_delay_h"],
               mkh["delay_vs_plan_h"] if mkh else None),
        _check("saved_hours", "Расчётная экономия, груз-часы", EXPECTED["saved_hours"], alert["totals"]["saved_hours"]),
        _check("saved_rub", "Расчётная экономия, ₽", EXPECTED["saved_rub"], alert["totals"]["saved_rub"]),
        _check("recommended", "Рекомендованный вариант", EXPECTED["recommended"], rec["id"] if rec else None),
    ]
    ok = all(c["ok"] for c in checks)
    problems = [] if ok else calm_problems + explain(
        cp, sc, [c for c in checks if c["name"] not in ("calm_start", "forecast_quiet")], items)
    w = cp.weather_out()
    return {"ok": ok, "sim_now": cp.sim_now.isoformat().replace("+00:00", "Z"),
            "weather": {"source": w["source"], "stale": w["stale"], "updated_at": w["updated_at"]},
            "checks": checks, "problems": problems}


def explain(cp, sc: dict, checks: list[dict], items: dict) -> list[str]:
    bad = {c["name"] for c in checks if not c["ok"]}
    lim = cp.meta["wave_limit_m"]
    out = []
    m = cp.sailings.get(SAILING_M)
    if m and bad & {"mkh_delay_h", "recommended", "saved_hours", "saved_rub"}:
        dep = parse(m["departure"])
        wave = cp.weather.wave(m["from"], dep)
        free = m["capacity_t"] - m["booked_t"]
        if wave >= lim:
            out.append(f"волна в Махачкале {ru(wave)} м в момент отправления парома М ({day_time(dep)}), "
                       f"предел {ru(lim)} м — вариант через Махачкалу отпал")
        if free < NEED_T:
            out.append(f"на пароме М свободно {free:g} т из нужных {NEED_T} т — вариант отпал")
        if m["status"] != "scheduled":
            out.append(f"паром М в статусе {m['status']}")
    if bad & {"departure_shift_h", "do_nothing_h", "saved_hours", "saved_rub"}:
        end = parse(sc["end"])
        calm = cp.weather.first_calm("astrakhan", end, lim)
        if calm is None or calm != end:
            when = day_time(calm) if calm else "не в горизонте прогноза"
            out.append(f"волна в Астрахани после шторма {ru(cp.weather.base_wave('astrakhan', end))} м: "
                       f"порт открывается {when} вместо {day_time(end)}")
        a = cp.sailings.get(SAILING_A)
        if a and hours(cp.sim_now, a["departure"]) != 44:
            out.append(f"паром А уходит через {hours(cp.sim_now, a['departure']):g} ч вместо 44 ч")
    for c in checks:
        if c["name"].startswith("risk_sh") and not c["ok"]:
            sid = c["name"][5:]
            labels = ", ".join(f["label"] for f in cp.shipments[sid]["risk"]["factors"])
            out.append(f"риск №{sid[3:]} {c['actual']}% вместо {c['expected']}±{RISK_TOLERANCE_PP}% "
                       f"(предиктор {cp.predictor.name}): факторы — {labels}")
        if c["name"] == "risk_order" and not c["ok"]:
            out.append(f"порядок рисков нарушен: {c['actual']} (предиктор {cp.predictor.name})")
    if not out:
        out.append("причина не определена: смотрите алерт после POST /api/scenarios storm_north")
    return out


def log_check(st, when: str) -> dict:
    try:
        res = run_check(st)
    except Exception:
        log.exception("Проверка демо (%s) упала", when)
        return {"ok": False}
    src = f"погода: {res['weather']['source']}{', устарела' if res['weather']['stale'] else ''}"
    quiet = next(c["actual"] for c in res["checks"] if c["name"] == "forecast_quiet")
    if not quiet.startswith("0 "):
        log.warning("Проверка демо (%s): наблюдатель нашёл угрозу в настоящем прогнозе до сценария — %s", when, quiet)
    if res["ok"]:
        risk = "/".join(str(c["actual"]) for c in res["checks"] if c["name"].startswith("risk_sh"))
        calm = next(c["actual"] for c in res["checks"] if c["name"] == "calm_start")
        log.info("Проверка демо (%s): начальное состояние спокойное — %s; числа сценария сходятся — риск %s%% (%s), "
                 "+18 ч, +48 ч, +6 ч, 126 груз-ч, 596 640 ₽, через Махачкалу (%s)", when, calm, risk,
                 st.predictor.name, src)
    else:
        diff = "; ".join(f"{c['label']}: {c['actual']} вместо {c['expected']}" for c in res["checks"] if not c["ok"])
        log.warning("Проверка демо (%s): РАСХОЖДЕНИЕ — %s. Почему: %s (%s)", when, diff,
                    "; ".join(res["problems"]), src)
    return res
