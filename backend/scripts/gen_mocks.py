"""Генератор data/seed.json и data/mock/*.json.

1. Сид: узлы, рёбра, рейсы, грузы с плановыми маршрутами, документы, пропуска, реестр, параметры.
   Поправили расстояние, тариф или рейс в таблицах ниже — перезапустили скрипт.
2. Сверка: независимый расчёт по формулам docs/DEMO_SCENARIO.md (CALC, ROUTES) и тот же набор
   17 чисел, посчитанный движком (app/dispatcher.py), сравниваются с числами сценария.
3. Моки: движок прогоняет демо с фиксированными часами — initial → инвойс №05 → storm → accepted,
   и каждый ответ пишется в data/mock/ через Pydantic-модели контракта. Поэтому файлы моков
   совпадают с тем, что отдаёт сервер.

Запуск из backend/:  python scripts/gen_mocks.py
Время сценария — московское (UTC+3), в JSON — UTC.
"""
import asyncio
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import models as M  # noqa: E402
from app.config import DATA_DIR, MOCK_DIR, MOCK_JWT_SECRET  # noqa: E402
from app.documents import doc_hash  # noqa: E402
from app.ledger import append_block, verify_chain  # noqa: E402
from app.weather import WEATHER_BASE  # noqa: E402

MSK = timezone(timedelta(hours=3))



def T(day: int, h: int, m: int = 0) -> datetime:
    return datetime(2026, 11, day, h, m, tzinfo=MSK)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def hours(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600


NOW = T(12, 14)               # «сейчас» в демо
ACCEPT_TS = T(12, 14, 32)     # «Уже принято, 14:32»
DOC05_TS = T(12, 13, 50)      # инвойс №05 снимают до шторма
HOUR_COST = 125               # ₽/т·ч, условная стоимость часа задержки
WAVE_LIMIT = 2.5              # м, предел для парома
OWNER_TG_ID = 100000001       # демо-логист; настоящий id привяжет /users/link

# ---------------- Узлы ----------------
NODES = [
    # id, name, country, type, lat, lon, congestion
    ("moscow", "Москва", "RU", "city", 55.75, 37.62, 0.40),
    ("samara", "Самара", "RU", "station", 53.20, 50.15, 0.35),
    ("saratov", "Саратов", "RU", "station", 51.53, 46.03, 0.35),
    ("astrakhan", "Астрахань", "RU", "port", 46.35, 48.04, 0.62),
    ("olya", "Оля", "RU", "port", 45.78, 47.55, 0.50),
    ("makhachkala", "Махачкала", "RU", "port", 42.98, 47.50, 0.55),
    ("samur", "Самур (граница)", "RU/AZ", "border", 41.63, 48.43, 0.45),
    ("baku", "Баку / Алят", "AZ", "port", 39.95, 49.41, 0.50),
    ("astara", "Астара (граница)", "AZ/IR", "border", 38.43, 48.87, 0.55),
    ("rasht", "Решт", "IR", "station", 37.28, 49.58, 0.40),
    ("anzali", "Энзели", "IR", "port", 37.47, 49.46, 0.58),
    ("amirabad", "Амирабад", "IR", "port", 36.85, 53.37, 0.45),
    ("aktau", "Актау", "KZ", "port", 43.65, 51.16, 0.50),
    ("incheh", "Инче-Бурун (граница)", "TM/IR", "border", 37.45, 54.72, 0.40),
    ("tehran", "Тегеран", "IR", "city", 35.69, 51.39, 0.50),
    ("bandar_abbas", "Бендер-Аббас", "IR", "port", 27.18, 56.27, 0.60),
    ("mumbai", "Мумбаи (Нава-Шева)", "IN", "port", 18.95, 72.95, 0.55),
]
NODE = {n[0]: n for n in NODES}

# ---------------- Рёбра ----------------
# вид: (mode, ₽/т·км, г CO₂/т·км)
KINDS = {
    "rail": ("rail", 2.2, 20),
    "ferry": ("sea", 1.6, 50),   # каспийский паром
    "road": ("road", 4.0, 75),
    "ocean": ("sea", 0.5, 15),   # океанское судно
}
EDGE_DEFS = [
    # from, to, вид, ветка, км, часы
    ("moscow", "astrakhan", "rail", "transcaspian", 1400, 40),
    ("samara", "astrakhan", "rail", "transcaspian", 1000, 29),
    ("saratov", "astrakhan", "rail", "transcaspian", 560, 16),
    ("astrakhan", "olya", "rail", "transcaspian", 70, 2),
    ("astrakhan", "makhachkala", "rail", "transcaspian", 490, 14),
    ("astrakhan", "anzali", "ferry", "transcaspian", 1150, 48),
    ("olya", "anzali", "ferry", "transcaspian", 1100, 46),
    ("olya", "amirabad", "ferry", "transcaspian", 1250, 52),
    ("makhachkala", "anzali", "ferry", "transcaspian", 650, 34),
    ("aktau", "baku", "ferry", "transcaspian", 450, 20),
    ("anzali", "rasht", "road", "transcaspian", 40, 1),
    ("rasht", "tehran", "road", "transcaspian", 320, 5),
    ("amirabad", "tehran", "road", "transcaspian", 300, 6),
    ("tehran", "bandar_abbas", "road", "transcaspian", 1140, 18),
    ("bandar_abbas", "mumbai", "ocean", "transcaspian", 1900, 72),
    ("makhachkala", "samur", "rail", "west", 200, 6),
    ("samur", "baku", "rail", "west", 210, 6),
    ("baku", "astara", "rail", "west", 320, 10),
    ("astara", "rasht", "road", "west", 170, 4),
    ("moscow", "aktau", "rail", "east", 2600, 74),
    ("aktau", "incheh", "rail", "east", 1200, 34),
    ("incheh", "tehran", "rail", "east", 650, 18),
]
EDGES: dict[str, dict] = {}
for f, t, kind, branch, km, h in EDGE_DEFS:
    mode, rate, co2 = KINDS[kind]
    eid = f"e-{f}-{t}"
    EDGES[eid] = {"id": eid, "from": f, "to": t, "mode": mode, "branch": branch,
                  "distance_km": km, "base_hours": h,
                  "cost_rub_per_t": round(km * rate, 2), "co2_g_per_tkm": co2}

# ---------------- Рейсы ----------------
SAILING_DEFS = [
    # id, from, to, отправление, часов до него окончание приёма, в пути, вместимость, занято, статус
    ("sl-ast-anz-1112", "astrakhan", "anzali", T(12, 10), 4, 48, 1800, 1650, "departed"),
    ("sl-ast-anz-1114", "astrakhan", "anzali", T(14, 10), 4, 48, 1800, 1310, "scheduled"),  # паром А
    ("sl-ast-anz-1116", "astrakhan", "anzali", T(16, 10), 4, 48, 1800, 640, "scheduled"),   # паром Б
    ("sl-mkh-anz-1113", "makhachkala", "anzali", T(13, 6), 4, 34, 1200, 1150, "scheduled"),
    ("sl-mkh-anz-1115", "makhachkala", "anzali", T(15, 6), 4, 34, 1200, 760, "scheduled"),  # паром М
    ("sl-mkh-anz-1117", "makhachkala", "anzali", T(17, 6), 4, 34, 1200, 300, "scheduled"),
]
SAILINGS = {}
for sid, f, t, dep, cut, dur, cap, booked, st in SAILING_DEFS:
    SAILINGS[sid] = {"id": sid, "from": f, "to": t, "departure": iso(dep),
                     "cutoff": iso(dep - timedelta(hours=cut)), "duration_h": dur,
                     "capacity_t": cap, "booked_t": booked, "status": st, "cancel_reason": None}
FERRY_A, FERRY_B, FERRY_M = "sl-ast-anz-1114", "sl-ast-anz-1116", "sl-mkh-anz-1115"


# ---------------- Маршруты ----------------
def tail_from_anzali(arr: datetime) -> list:
    t = arr + timedelta(hours=12)  # обработка и таможня в Энзели
    return [("e-anzali-rasht", t, None)] + tail_from_rasht(t + timedelta(hours=1))


def tail_from_rasht(t: datetime) -> list:
    bandar = t + timedelta(hours=5 + 18)
    return [("e-rasht-tehran", t, None),
            ("e-tehran-bandar_abbas", t + timedelta(hours=5), None),
            ("e-bandar_abbas-mumbai", bandar + timedelta(hours=12), None)]  # 12 ч в порту


def build_route(rid: str, spec: list, weight: float, branch: str) -> dict:
    legs, cost, co2 = [], 0.0, 0.0
    for i, (eid, start, sid) in enumerate(spec):
        e = EDGES[eid]
        dur = SAILINGS[sid]["duration_h"] if sid else e["base_hours"]
        end = start + timedelta(hours=dur)
        status = "done" if end <= NOW else "active" if start <= NOW else "pending"
        legs.append({"index": i, "edge_id": eid, "from": e["from"], "to": e["to"], "mode": e["mode"],
                     "sailing_id": sid, "planned_start": iso(start), "planned_end": iso(end),
                     "predicted_delay_h": 0, "status": status})
        cost += e["cost_rub_per_t"] * weight
        co2 += weight * e["distance_km"] * e["co2_g_per_tkm"] / 1000
    total_h = hours(parse(legs[0]["planned_start"]), parse(legs[-1]["planned_end"]))
    return {"id": rid, "legs": legs, "total_hours": total_h, "total_cost_rub": round(cost),
            "total_co2_kg": round(co2, 1), "branch": branch}


def route_end(r: dict) -> datetime:
    return parse(r["legs"][-1]["planned_end"])


# ---------------- Риск ----------------
def level(p: float) -> str:
    return "high" if p >= 0.6 else "medium" if p >= 0.3 else "low"


def risk(p, factors, shift=0, delay=0) -> dict:
    return {"miss_probability": p, "level": level(p), "departure_shift_h": shift,
            "arrival_delay_h": delay,
            "factors": [{"name": n, "label": lbl, "impact_hours": h} for n, lbl, h in factors]}


def ru(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def low_ast(p):
    return risk(p, [("wave_height", f"Волна {ru(WEATHER_BASE['astrakhan'])} м", 0),
                    ("port_congestion", "Загрузка порта 62%", 1),
                    ("customs_queue", "Очередь на таможне", 1)])



# ---------------- Грузы ----------------
def position(route: dict, stage: str, origin: str):
    if stage == "planned":
        n = NODE[origin]
        return {"lat": n[4], "lon": n[5]}, None
    for leg in route["legs"]:
        if leg["status"] == "active":
            s, e = parse(leg["planned_start"]), parse(leg["planned_end"])
            k = hours(s, NOW) / hours(s, e)
            a, b = NODE[leg["from"]], NODE[leg["to"]]
            return {"lat": round(a[4] + (b[4] - a[4]) * k, 4),
                    "lon": round(a[5] + (b[5] - a[5]) * k, 4)}, leg["index"]
    n = NODE[route["legs"][-1]["to"]]
    return {"lat": n[4], "lon": n[5]}, None


def shipment(base: dict, route: dict, rk: dict, *, rerouted=False, planned_eta=None,
             eta_shift=0.0, pass_id=None) -> dict:
    pos, cur = position(route, base["stage"], base["origin"])
    planned_eta = planned_eta or iso(route_end(route))
    return {**{k: base[k] for k in ("id", "title", "cargo_type", "weight_t", "owner_tg_id",
                                    "origin", "destination", "stage")},
            "risk_level": rk["level"], "rerouted": rerouted,
            "display_status": M.display_status_of(base["stage"], rk["level"], rerouted),
            "position": pos, "current_leg": cur, "route": route,
            "planned_eta": planned_eta,
            "eta": iso(parse(planned_eta) + timedelta(hours=eta_shift)),
            "risk": rk, "pass_id": pass_id, "pass_state": "active" if pass_id else "none"}


BASES = [
    # id, title, cargo_type, вес, откуда, куда, этап
    ("sh-01", "Зерно", "grain", 60, "moscow", "mumbai", "in_transit"),
    ("sh-02", "Металл", "metal", 40, "samara", "mumbai", "in_transit"),
    ("sh-03", "Оборудование", "equipment", 20, "saratov", "mumbai", "in_transit"),
    ("sh-04", "Текстиль", "textile", 25, "baku", "mumbai", "in_transit"),
    ("sh-05", "Удобрения", "fertilizer", 30, "astrakhan", "anzali", "planned"),
]
BASE = {b[0]: dict(zip(("id", "title", "cargo_type", "weight_t", "origin", "destination", "stage"), b),
                   owner_tg_id=OWNER_TG_ID) for b in BASES}

FIRST_LEG = {"sh-01": ("e-moscow-astrakhan", T(12, 4), None),
             "sh-02": ("e-samara-astrakhan", T(12, 9), None),
             "sh-03": ("e-saratov-astrakhan", T(12, 12), None)}
P_LOW = {"sh-01": 0.07, "sh-02": 0.06, "sh-03": 0.05}
AFFECTED = ["sh-01", "sh-02", "sh-03"]

ROUTES = {}
for sid in AFFECTED:
    w = BASE[sid]["weight_t"]
    first = FIRST_LEG[sid]
    ROUTES[sid] = {
        "plan": build_route(f"r-{sid}-plan", [first, ("e-astrakhan-anzali", T(14, 10), FERRY_A),
                                              *tail_from_anzali(T(16, 10))], w, "transcaspian"),
        # поезд идёт дальше, Астрахань → Махачкала, 14 ч; паром М 15 ноя 06:00
        "mkh": build_route(f"r-{sid}-mkh", [first, ("e-astrakhan-makhachkala", T(13, 20), None),
                                            ("e-makhachkala-anzali", T(15, 6), FERRY_M),
                                            *tail_from_anzali(T(16, 16))], w, "transcaspian"),
        # западная ветка: две новые границы по 24 ч
        "west": build_route(f"r-{sid}-west", [first, ("e-astrakhan-makhachkala", T(13, 20), None),
                                              ("e-makhachkala-samur", T(14, 10), None),
                                              ("e-samur-baku", T(15, 16), None),
                                              ("e-baku-astara", T(15, 22), None),
                                              ("e-astara-rasht", T(17, 8), None),
                                              *tail_from_rasht(T(17, 12))], w, "west"),
    }
ROUTES["sh-04"] = {"plan": build_route("r-sh-04-plan", [("e-baku-astara", T(12, 8), None),
                                                        ("e-astara-rasht", T(13, 18), None),
                                                        *tail_from_rasht(T(13, 22))], 25, "west")}
ROUTES["sh-05"] = {"plan": build_route("r-sh-05-plan", [("e-astrakhan-anzali", T(16, 10), FERRY_B)],
                                       30, "transcaspian")}

# ---------------- Расчёт экономии (формулы DEMO_SCENARIO) ----------------
DO_NOTHING_H = hours(parse(SAILINGS[FERRY_A]["departure"]), parse(SAILINGS[FERRY_B]["departure"]))  # 48
CALC = {}
for sid in AFFECTED:
    w = BASE[sid]["weight_t"]
    plan, mkh = ROUTES[sid]["plan"], ROUTES[sid]["mkh"]
    alt_delay = hours(route_end(plan), route_end(mkh))                  # 6
    loss = DO_NOTHING_H * w * HOUR_COST                                  # задержка при бездействии
    residual = alt_delay * w * HOUR_COST                                 # остаточная задержка
    surcharge = mkh["total_cost_rub"] - plan["total_cost_rub"]           # доплата за перевозку
    CALC[sid] = {"w": w, "alt_delay": alt_delay, "loss": loss, "residual": residual,
                 "surcharge": surcharge, "saved_rub": round(loss - residual - surcharge),
                 "saved_hours": DO_NOTHING_H - alt_delay,
                 "co2_plan": plan["total_co2_kg"], "co2_alt": mkh["total_co2_kg"],
                 "co2_delta": round(mkh["total_co2_kg"] - plan["total_co2_kg"], 1)}

TOT_SAVED_H = sum(c["saved_hours"] for c in CALC.values())
TOT_SAVED_RUB = sum(c["saved_rub"] for c in CALC.values())
TOT_LOSS = sum(c["loss"] for c in CALC.values())
TOT_ALT = sum(c["residual"] + c["surcharge"] for c in CALC.values())
TOT_CO2 = round(sum(c["co2_delta"] for c in CALC.values()), 1)
TOT_CO2_PCT = round(TOT_CO2 / sum(c["co2_plan"] for c in CALC.values()) * 100, 1)
TOT_W = sum(c["w"] for c in CALC.values())


# ---------------- Документы, пропуска, реестр ----------------
DOC_FIELDS = {
    "sh-01": ("ООО «Волга-Агро»", "Shree Grain Imports Pvt Ltd", "Пшеница продовольственная 3 класса",
              "1001 99", 60000, 15000, "USD", "RU"),
    "sh-02": ("ООО «СамараМеталлТрейд»", "Bharat Steel Traders", "Прокат стальной горячекатаный",
              "7208 51", 40000, 28000, "USD", "RU"),
    "sh-03": ("ООО «СарЭнергоМаш»", "Pune Engineering Works Ltd", "Насосное оборудование",
              "8413 70", 20000, 96000, "USD", "RU"),
    "sh-04": ("Baku Textile LLC", "Mumbai Fabrics Co.", "Ткани хлопчатобумажные",
              "5208 52", 25000, 62000, "USD", "AZ"),
    "sh-05": ("ООО «АстраханьАгроХим»", "Компания «Кешт Гостар Гилян»", "Удобрения азотные (карбамид)",
              "3102 10", 30000, 10500, "USD", "RU"),
}
FIELD_NAMES = ("seller", "buyer", "goods", "hs_code", "weight_kg", "value", "currency", "origin_country")
CHECKPOINT = {"sh-01": "astrakhan", "sh-02": "astrakhan", "sh-03": "astrakhan",
              "sh-04": "astara", "sh-05": "astrakhan"}
VALID_UNTIL = T(30, 0)


def document(sid: str, status: str) -> dict:
    fields = dict(zip(FIELD_NAMES, DOC_FIELDS[sid]))
    w = BASE[sid]["weight_t"]
    return {"id": f"doc-{sid[3:]}", "shipment_id": sid, "type": "invoice",
            "source_lang": "fa" if sid == "sh-05" else "ru",
            "image_url": f"mock://invoice-{sid}.jpg", "fields": fields,
            "checks": [{"name": "required_fields", "ok": True, "note": "Все обязательные поля заполнены"},
                       {"name": "weight_match", "ok": True,
                        "note": f"Вес {fields['weight_kg']:,.0f} кг совпадает с заявкой ({w:g} т)".replace(",", " ")},
                       {"name": "hs_code", "ok": True, "note": f"Код ТН ВЭД {fields['hs_code']}"}],
            "status": status, "hash": doc_hash(fields) if status == "confirmed" else None}


def make_pass(pid: str, sid: str, block: dict) -> dict:
    token = jwt.encode({"pid": pid, "sid": sid, "cp": block["checkpoint_node"],
                        "doc_hash": block["doc_hash"], "block_hash": block["hash"],
                        "exp": int(VALID_UNTIL.timestamp())}, MOCK_JWT_SECRET, algorithm="HS256")
    return {"id": pid, "shipment_id": sid, "checkpoint_node": block["checkpoint_node"], "token": token,
            "doc_hash": block["doc_hash"], "block_hash": block["hash"],
            "valid_until": iso(VALID_UNTIL), "status": "active"}


DOCS = {sid: document(sid, "confirmed") for sid in ("sh-01", "sh-02", "sh-03", "sh-04")}
DOC05_DRAFT = document("sh-05", "draft")

CHAIN: list[dict] = []
PASSES: dict[str, dict] = {}
for i, sid in enumerate(("sh-01", "sh-02", "sh-03", "sh-04")):
    b = append_block(CHAIN, iso(T(11, 10 + i)), "issued", sid, CHECKPOINT[sid], DOCS[sid]["hash"])
    PASSES[f"pass-{sid[3:]}"] = make_pass(f"pass-{sid[3:]}", sid, b)
assert verify_chain(CHAIN) is None


def ship_initial(sid):
    r = ROUTES[sid]["plan"]
    if sid in AFFECTED:
        rk = low_ast(P_LOW[sid])
    elif sid == "sh-04":
        rk = risk(0.11, [("border_queue", "Очередь на границе Астара", 2),
                         ("customs_queue", "Очередь на таможне", 1)])
    else:
        rk = risk(0.09, [("wave_height", f"Волна {ru(WEATHER_BASE['astrakhan'])} м", 0),
                         ("port_congestion", "Загрузка порта 62%", 1)])
    pid = f"pass-{sid[3:]}" if sid != "sh-05" else None
    return shipment(BASE[sid], r, rk, pass_id=pid)


IDS = list(BASE)


# ---------------- Сид для движка ----------------
SEED_META = {
    "now": iso(NOW), "timezone_note": "время сценария — МСК (UTC+3), в JSON — UTC",
    "hour_cost_rub_per_t": HOUR_COST, "wave_limit_m": WAVE_LIMIT,
    "co2_g_per_tkm": {k: v[2] for k, v in KINDS.items()},
    "rate_rub_per_tkm": {k: v[1] for k, v in KINDS.items()},
    # паромные рёбра: нужен рейс из расписания; остальные морские — океанское судно без расписания
    "ferry_edges": [e for e, d in EDGES.items() if d["co2_g_per_tkm"] == KINDS["ferry"][2]
                    and d["mode"] == "sea"],
    "handling_h": {"ferry_before_h": 8, "ferry_after_h": 12, "ocean_before_h": 12, "border_h": 24},
    # поезд Астрахань → Махачкала ходит раз в сутки (МСК); остальные плечи — по готовности
    "rail_departures_h": {"e-astrakhan-makhachkala": [hours(NOW, T(12, 20))]},  # 20:00 МСК = +6 ч
    "customs_h": 1,                     # обычная очередь на таможне в порту, ч
    "port_capacity_t_per_day": 2000,      # для строки «загрузка порта до → после»
    "ferry_forbidden_cargo": ["explosives"],
    "sailing_labels": {FERRY_A: "паром А", FERRY_B: "паром Б", FERRY_M: "паром М"},
    "via_names": {"makhachkala": "Махачкалу", "olya": "Олю", "astrakhan": "Астрахань",
                  "aktau": "Актау", "baku": "Баку",
                  "samur": "Самур", "astara": "Астару"},
    "pass_valid_until": iso(VALID_UNTIL),
    "owner_tg_id": OWNER_TG_ID,
}
SEED = {"meta": SEED_META, "nodes": None, "edges": list(EDGES.values()),
        "sailings": copy.deepcopy(list(SAILINGS.values())),
        "shipments": None, "documents": list(DOCS.values()),
        # закэшированный результат распознавания демо-инвойса (запасной путь вместо vision-LLM)
        "demo_drafts": {"sh-05": DOC05_DRAFT},
        "passes": None, "ledger": CHAIN[:4]}



# ---------------- Сверка ----------------
def reference_numbers() -> dict:
    """17 чисел независимым расчётом по формулам сценария."""
    c1 = CALC["sh-01"]
    return {
        "№01 бездействие, ₽": c1["loss"], "№01 остаточная, ₽": c1["residual"],
        "№01 доплата, ₽": c1["surcharge"], "№01 экономия, ₽": c1["saved_rub"],
        "№02 экономия, ₽": CALC["sh-02"]["saved_rub"], "№03 экономия, ₽": CALC["sh-03"]["saved_rub"],
        "№01 CO₂ план, кг": c1["co2_plan"], "№01 CO₂ Махачкала, кг": c1["co2_alt"],
        "№01 CO₂ %": round(c1["co2_delta"] / c1["co2_plan"] * 100, 1),
        "Итого груз-часы": TOT_SAVED_H, "Итого экономия, ₽": TOT_SAVED_RUB,
        "Бездействие 3 груза, ₽": TOT_LOSS, "Махачкала 3 груза, ₽": TOT_ALT,
        "CO₂ 3 груза, кг": TOT_CO2, "CO₂ 3 груза, %": TOT_CO2_PCT,
        "Бездействие, ч": DO_NOTHING_H, "Через Махачкалу, ч": c1["alt_delay"],
    }


def engine_numbers(st, alert: dict) -> dict:
    """Те же 17 чисел, посчитанные движком по алерту."""
    hc = st.meta["hour_cost_rub_per_t"]
    internal = st.alert_internal[alert["id"]]
    item = {i["shipment_id"]: i for i in alert["items"]}
    c = {}
    for sid in AFFECTED:
        it, w = item[sid], st.shipments[sid]["weight_t"]
        c[sid] = {"loss": internal[sid]["loss"], "residual": it["delay_vs_plan_h"] * w * hc,
                  "surcharge": it["to_route"]["total_cost_rub"] - it["from_route"]["total_cost_rub"],
                  "saved_rub": it["saved_rub"], "co2_plan": it["from_route"]["total_co2_kg"],
                  "co2_alt": it["to_route"]["total_co2_kg"], "co2_delta": it["co2_delta_kg"],
                  "alt_delay": it["delay_vs_plan_h"]}
    c1 = c["sh-01"]
    return {
        "№01 бездействие, ₽": c1["loss"], "№01 остаточная, ₽": c1["residual"],
        "№01 доплата, ₽": c1["surcharge"], "№01 экономия, ₽": c1["saved_rub"],
        "№02 экономия, ₽": c["sh-02"]["saved_rub"], "№03 экономия, ₽": c["sh-03"]["saved_rub"],
        "№01 CO₂ план, кг": c1["co2_plan"], "№01 CO₂ Махачкала, кг": c1["co2_alt"],
        "№01 CO₂ %": round(c1["co2_delta"] / c1["co2_plan"] * 100, 1),
        "Итого груз-часы": alert["totals"]["saved_hours"], "Итого экономия, ₽": alert["totals"]["saved_rub"],
        "Бездействие 3 груза, ₽": alert["do_nothing"]["loss_rub"],
        "Махачкала 3 груза, ₽": sum(internal[s]["alt_cost"] for s in AFFECTED),
        "CO₂ 3 груза, кг": alert["totals"]["co2_delta_kg"],
        "CO₂ 3 груза, %": alert["totals"]["co2_delta_pct"],
        "Бездействие, ч": alert["do_nothing"]["delay_hours"], "Через Махачкалу, ч": c1["alt_delay"],
    }


SCENARIO_DOC = {  # числа прямо из docs/DEMO_SCENARIO.md
    "№01 бездействие, ₽": 360000, "№01 остаточная, ₽": 45000, "№01 доплата, ₽": 16680,
    "№01 экономия, ₽": 298320, "№02 экономия, ₽": 198880, "№03 экономия, ₽": 99440,
    "№01 CO₂ план, кг": 13590, "№01 CO₂ Махачкала, кг": 12678, "№01 CO₂ %": -6.7,
    "Итого груз-часы": 126, "Итого экономия, ₽": 596640, "Бездействие 3 груза, ₽": 720000,
    "Махачкала 3 груза, ₽": 123360, "CO₂ 3 груза, кг": -1824, "CO₂ 3 груза, %": -6.9,
    "Бездействие, ч": 48, "Через Махачкалу, ч": 6,
}


# ---------------- Запись ----------------
def ser(model, obj):
    return model.model_validate(obj).model_dump(mode="json", by_alias=True)


def dump(name: str, obj, model=None, many=False):
    """Мок проходит модель контракта и пишется так же, как его сериализует сервер."""
    if model is not None:
        obj = [ser(model, o) for o in obj] if many else ser(model, obj)
    path = MOCK_DIR / f"{name}.json" if name != "seed" else DATA_DIR / "seed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def snapshot(st, suffix: str):
    dump(f"shipments{suffix}", st.shipments_list(), M.Shipment, many=True)
    dump(f"alternatives{suffix}", {sid: [ser(M.AlternativeOut, a) for a in st.alternatives(sid)]
                                   for sid in st.shipments})
    dump(f"stats{suffix}", st.stats(), M.StatsOut)
    dump(f"alerts{suffix}", st.alerts_list(), M.Alert, many=True)
    dump(f"sailings{suffix}", st.sailings_list(None, None), M.Sailing, many=True)
    dump(f"ledger{suffix}", st.ledger_list(), M.Block, many=True)
    dump(f"passes{suffix}", list(st.passes.values()), M.Pass, many=True)
    dump(f"weather{suffix}", st.weather_out(), M.WeatherOut)


def run_engine() -> dict:
    """Демо-прогон движком с фиксированными часами. Пропуска в моках — публичным ключом моков."""
    from app import state as state_mod
    from app.clock import FixedClock
    state_mod.PASS_SECRET = MOCK_JWT_SECRET
    from app.predictor import FormulaPredictor
    from app.weather import SyntheticForecast
    # моки всегда на формуле: не зависят ни от обученной модели, ни от установленного catboost
    st = state_mod.State(DATA_DIR / "seed.json", clock=FixedClock(iso(NOW)), forecast=SyntheticForecast(),
                         predictor=FormulaPredictor())

    dump("graph", st.graph_out(), M.GraphOut)
    dump("scenario_presets", st.presets(), M.PresetOut, many=True)
    dump("documents", list(st.documents.values()), M.Document, many=True)
    snapshot(st, "")

    st.clock.set(DOC05_TS)                       # инвойс №05 снимают до шторма
    draft = st.upload_document("sh-05")
    dump("document_draft", draft, M.Document)
    confirmed = asyncio.run(st.confirm(draft["id"], draft["fields"]))
    dump("document_confirm", confirmed, M.DocumentConfirmOut)
    dump("ledger.doc", st.ledger_list(), M.Block, many=True)

    st.clock.set(NOW)
    out = asyncio.run(st.run_scenario("storm_north"))
    dump("scenario_storm_north", out, M.ScenarioCreateOut)
    numbers = engine_numbers(st, out["alert"])
    snapshot(st, ".storm")

    st.clock.set(ACCEPT_TS)                      # «Уже принято, 14:32»
    acc = asyncio.run(st.accept(out["alert"]["id"], "web"))
    dump("accept", acc, M.AcceptOut)
    dump("decision", acc["decision"], M.Decision)
    snapshot(st, ".accepted")
    return numbers


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for f in MOCK_DIR.glob("*.json"):
        f.unlink()
    SEED.update(nodes=[dict(zip(("id", "name", "country", "type", "lat", "lon", "congestion"), n))
                       for n in NODES],
                shipments=[ship_initial(s) for s in IDS], passes=list(PASSES.values()))
    M.GraphOut.model_validate({"nodes": SEED["nodes"], "edges": SEED["edges"]})
    dump("seed", SEED)
    eng = run_engine()

    ref = reference_numbers()
    bad = 0
    print(f"{'':4}{'':28}{'формулы':>12}{'движок':>12}{'сценарий':>12}")
    for name, want in SCENARIO_DOC.items():
        ok = abs(ref[name] - want) < 1e-6 and abs(eng[name] - want) < 1e-6
        bad += not ok
        print(f"{'OK ' if ok else 'ERR'} {name:28}{ref[name]:>12g}{eng[name]:>12g}{want:>12g}")
    print(f"\nМоки записаны в {MOCK_DIR}, сид — {DATA_DIR / 'seed.json'}")
    if bad:
        sys.exit(f"{bad} расхождений со сценарием")


if __name__ == "__main__":
    main()
