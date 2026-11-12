"""Проверка перед показом (GET /api/demo/check, лог при старте и reset).

Прогоняет storm_north на копии исходного состояния (как сразу после reset, тот же sim_now и тот же
прогноз погоды), живое состояние не трогает. Сверяет ключевые числа с эталоном DEMO_SCENARIO.md и,
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
EXPECTED = {"departure_shift_h": 18, "do_nothing_h": 48, "mkh_delay_h": 6,
            "saved_hours": 126, "saved_rub": 596640, "recommended": "mkh"}
NEED_T = 120


def _check(name: str, label: str, expected, actual) -> dict:
    ok = actual == expected if isinstance(expected, str) else (
        actual is not None and abs(float(actual) - float(expected)) < 1e-6)
    return {"name": name, "label": label, "expected": expected, "actual": actual, "ok": ok}


def run_check(st) -> dict:
    from .state import State  # здесь, чтобы не было циклического импорта
    cp = State(st.seed_path, clock=FixedClock(st.sim_now), predictor=st.predictor, forecast=st.forecast)
    out = D.run_scenario(cp, "storm_north")
    alert, sc = out["alert"], out["scenario"]
    items = {i["shipment_id"]: i for i in alert["items"]}
    rec = next((o for o in alert["options"] if o["recommended"]), None)
    mkh = next((o for o in alert["options"] if o["id"] == "mkh"), None)

    checks = []
    for sid, want in EXPECTED_RISK.items():
        risk = cp.shipments[sid]["risk"]
        checks.append(_check(f"risk_{sid}", f"Риск №{sid[3:]}", want, round(risk["miss_probability"] * 100)))
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
    problems = [] if ok else explain(cp, sc, checks, items)
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
        if c["name"].startswith("risk_") and not c["ok"]:
            sid = c["name"][5:]
            labels = ", ".join(f["label"] for f in cp.shipments[sid]["risk"]["factors"])
            out.append(f"риск №{sid[3:]} {c['actual']}% вместо {c['expected']}%: факторы — {labels}")
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
    if res["ok"]:
        log.info("Проверка демо (%s): числа сценария сходятся — 82/74/68%%, +18 ч, +48 ч, +6 ч, "
                 "126 груз-ч, 596 640 ₽, через Махачкалу (%s)", when, src)
    else:
        diff = "; ".join(f"{c['label']}: {c['actual']} вместо {c['expected']}" for c in res["checks"] if not c["ok"])
        log.warning("Проверка демо (%s): РАСХОЖДЕНИЕ — %s. Почему: %s (%s)", when, diff,
                    "; ".join(res["problems"]), src)
    return res
