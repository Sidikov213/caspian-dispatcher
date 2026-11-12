"""Генератор data/seed.json и data/mock/*.json.

Все числа выводятся формулами из docs/DEMO_SCENARIO.md: поправили расстояние или тариф
в таблицах ниже — перезапустили скрипт, моки пересчитались.

Запуск из backend/:  python scripts/gen_mocks.py

Время сценария — московское (UTC+3), в JSON — UTC.
Фазы моков: initial (шторм не запущен) → storm (алерт) → accepted (через Махачкалу).
"""
import copy
import json
import math
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

# ---------------- Сценарий ----------------
STORM_START, STORM_END = T(14, 2), T(14, 21)
BLOCKED = ["e-astrakhan-anzali", "e-olya-anzali", "e-olya-amirabad"]
SCENARIO = {"id": "scn-storm-north", "type": "storm", "title": "Шторм на Северном Каспии",
            "blocked_edges": BLOCKED, "affected_nodes": ["astrakhan", "olya"],
            "start": iso(STORM_START), "end": iso(STORM_END),
            "params": {"wave_height_m": 3.4, "wind_ms": 18}}


# ---------------- Погода ----------------
WEATHER_BASE = {"astrakhan": 0.7, "olya": 0.8, "makhachkala": 1.0, "baku": 1.1,
                "aktau": 1.0, "anzali": 0.8, "amirabad": 0.7}
WIND = {"astrakhan": 6.5, "olya": 7.0, "makhachkala": 7.5, "baku": 8.0,
        "aktau": 7.0, "anzali": 5.5, "amirabad": 5.0}
H_START, H_END = hours(NOW, STORM_START), hours(NOW, STORM_END)  # 36, 55


def wave(node: str, h: float, storm: bool) -> float:
    i = list(WEATHER_BASE).index(node)
    calm = WEATHER_BASE[node] + 0.25 * math.sin(2 * math.pi * h / 24 + i)
    if not storm:
        return round(calm, 2)
    if node in ("astrakhan", "olya"):
        if H_START <= h <= H_END:  # выше предела ровно в окне шторма, пик 3,4 м
            return round(2.6 + 0.8 * math.sin(math.pi * (h - H_START) / (H_END - H_START)), 2)
        if H_START - 6 <= h < H_START:
            return round(calm + (2.45 - calm) * (h - (H_START - 6)) / 6, 2)
        if H_END < h <= H_END + 6:
            return round(2.45 - (2.45 - calm) * (h - H_END) / 6, 2)
    if node == "makhachkala":
        return round(calm + 0.7 * math.exp(-(((h - 50) / 12) ** 2)), 2)
    return round(calm, 2)


def weather(storm: bool) -> dict:
    pts = []
    for node in WEATHER_BASE:
        fc = [{"ts": iso(NOW + timedelta(hours=h)), "wave_height_m": wave(node, h, storm)}
              for h in range(168)]
        pts.append({"node_id": node, "wave_height_m": fc[0]["wave_height_m"],
                    "wind_ms": WIND[node], "forecast": fc})
    return {"updated_at": iso(NOW - timedelta(minutes=12)), "stale": False,
            "source": "open-meteo", "points": pts}


MKH_WAVE = wave("makhachkala", hours(NOW, T(15, 6)), True)  # волна в Махачкале при отправлении парома М
assert MKH_WAVE < WAVE_LIMIT


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


def storm_route(r: dict, delay: float) -> dict:
    """Плановый маршрут под штормом: морской участок заблокирован, дальше +delay ч, если рейс отменят."""
    r = copy.deepcopy(r)
    hit = False
    for leg in r["legs"]:
        if leg["edge_id"] in BLOCKED and leg["status"] == "pending":
            leg["status"] = "blocked"
            hit = True
        if hit:
            leg["predicted_delay_h"] = delay
    return r


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


def storm_risk(p):
    return risk(p, [("wave_height", "Волна 3,4 м", 11),
                    ("port_congestion", "Загрузка порта 85%", 5),
                    ("customs_queue", "Очередь на таможне", 2)], shift=18, delay=48)


def mkh_risk(p):
    return risk(p, [("wave_height", f"Волна в Махачкале {ru(MKH_WAVE)} м", 0),
                    ("port_congestion", "Загрузка порта 61%", 1),
                    ("customs_queue", "Очередь на таможне", 1)])


def west_risk(p):
    return risk(p, [("border_queue", "Очередь на погранпереходах Самур и Астара", 4),
                    ("customs_queue", "Таможня Азербайджана", 2)])


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
P_STORM = {"sh-01": 0.82, "sh-02": 0.74, "sh-03": 0.68}
P_LOW = {"sh-01": 0.07, "sh-02": 0.06, "sh-03": 0.05}
P_MKH = {"sh-01": 0.12, "sh-02": 0.11, "sh-03": 0.10}
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


def signed(x: float) -> str:
    return ru(x).replace("-", "−")


def k_rub(x: float) -> str:
    return f"{round(x / 1000)} тыс ₽"


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
DOC05 = document("sh-05", "confirmed")

CHAIN: list[dict] = []
PASSES: dict[str, dict] = {}
for i, sid in enumerate(("sh-01", "sh-02", "sh-03", "sh-04")):
    b = append_block(CHAIN, iso(T(11, 10 + i)), "issued", sid, CHECKPOINT[sid], DOCS[sid]["hash"])
    PASSES[f"pass-{sid[3:]}"] = make_pass(f"pass-{sid[3:]}", sid, b)
b5 = append_block(CHAIN, iso(DOC05_TS), "issued", "sh-05", "astrakhan", DOC05["hash"])
PASSES["pass-05"] = make_pass("pass-05", "sh-05", b5)
REISSUED_BLOCKS = []
for sid in AFFECTED:
    b = append_block(CHAIN, iso(ACCEPT_TS), "reissued", sid, "makhachkala", DOCS[sid]["hash"])
    REISSUED_BLOCKS.append(b)
    PASSES[f"pass-{sid[3:]}-r1"] = make_pass(f"pass-{sid[3:]}-r1", sid, b)
assert verify_chain(CHAIN) is None

# ---------------- Сборка фаз ----------------
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


def ship_storm(sid):
    if sid not in AFFECTED:
        return ship_initial(sid)
    r = storm_route(ROUTES[sid]["plan"], DO_NOTHING_H)
    return shipment(BASE[sid], r, storm_risk(P_STORM[sid]), eta_shift=DO_NOTHING_H,
                    pass_id=f"pass-{sid[3:]}")


def ship_accepted(sid):
    if sid not in AFFECTED:
        s = ship_initial(sid)
        if sid == "sh-05":  # в моках принятие идёт после съёмки инвойса №05
            s["pass_id"], s["pass_state"] = "pass-05", "active"
        return s
    plan_eta = iso(route_end(ROUTES[sid]["plan"]))
    return shipment(BASE[sid], ROUTES[sid]["mkh"], mkh_risk(P_MKH[sid]), rerouted=True,
                    planned_eta=plan_eta, eta_shift=CALC[sid]["alt_delay"],
                    pass_id=f"pass-{sid[3:]}-r1")


IDS = list(BASE)
SHIP = {ph: [f(s) for s in IDS] for ph, f in
        (("initial", ship_initial), ("storm", ship_storm), ("accepted", ship_accepted))}


def alt(route, rk, hours_, rub, co2, rec):
    return {"route": route, "risk": rk, "delta": {"hours": hours_, "rub": rub, "co2_kg": co2},
            "recommended": rec}


def alternatives(phase: str) -> dict:
    out = {}
    for sid in IDS:
        cur = next(s for s in SHIP[phase] if s["id"] == sid)
        if sid not in AFFECTED:
            out[sid] = [alt(cur["route"], cur["risk"], 0, 0, 0, True)]
            continue
        R, c = ROUTES[sid], CALC[sid]
        plan, mkh, west = R["plan"], R["mkh"], R["west"]
        west_d = (hours(route_end(plan), route_end(west)), west["total_cost_rub"] - plan["total_cost_rub"],
                  round(west["total_co2_kg"] - plan["total_co2_kg"], 1))
        a_mkh = (mkh, mkh_risk(P_MKH[sid]), c["alt_delay"], c["surcharge"], c["co2_delta"])
        a_west = (west, west_risk(0.15), *west_d)
        if phase == "initial":
            out[sid] = [alt(plan, low_ast(P_LOW[sid]), 0, 0, 0, True),
                        alt(*a_mkh, False), alt(*a_west, False)]
        else:
            out[sid] = [alt(*a_mkh, True),
                        alt(storm_route(plan, DO_NOTHING_H), storm_risk(P_STORM[sid]), DO_NOTHING_H, 0, 0, False),
                        alt(*a_west, False)]
    return out


def alert(status: str) -> dict:
    items = []
    for sid in AFFECTED:
        c = CALC[sid]
        items.append({"shipment_id": sid, "action": "reroute",
                      "from_route": storm_route(ROUTES[sid]["plan"], DO_NOTHING_H),
                      "to_route": ROUTES[sid]["mkh"], "sailing_id": FERRY_M,
                      "delay_vs_plan_h": c["alt_delay"], "saved_hours": c["saved_hours"],
                      "saved_rub": c["saved_rub"], "co2_delta_kg": c["co2_delta"]})
    text = (
        f"⚠️ Шторм на Северном Каспии: 14 ноя 02:00–21:00, волна до 3,4 м (предел парома {ru(WAVE_LIMIT)} м).\n"
        f"Под риском паром А Астрахань → Энзели (14 ноя, 10:00): 3 груза, {TOT_W:g} т.\n"
        f"Риск срыва стыковки до {round(max(P_STORM.values()) * 100)}%: отправление на 18 ч позже планового рейса.\n\n"
        f"Ничего не делать: если рейс А отменят, ждать рейс Б — прибытие +{DO_NOTHING_H:g} ч, "
        f"задержка обойдётся в {k_rub(TOT_LOSS)} по трём грузам.\n"
        f"Через Махачкалу (паром М, 15 ноя, 06:00): прибытие +{CALC['sh-01']['alt_delay']:g} ч к плану, "
        f"{k_rub(TOT_ALT)}.\n\n"
        f"Расчётная экономия по 3 грузам: {TOT_SAVED_H:g} груз-часов, {k_rub(TOT_SAVED_RUB)}, "
        f"{signed(TOT_CO2 / 1000)} т CO₂ ({signed(TOT_CO2_PCT)}%)."
    )
    return {"id": "alert-001", "scenario_id": SCENARIO["id"], "created_at": iso(NOW), "severity": "high",
            "title": "Шторм на Северном Каспии: 3 груза под риском", "text": text, "items": items,
            "totals": {"saved_hours": TOT_SAVED_H, "saved_rub": TOT_SAVED_RUB,
                       "co2_delta_kg": TOT_CO2, "co2_delta_pct": TOT_CO2_PCT},
            "do_nothing": {"delay_hours": DO_NOTHING_H, "loss_rub": TOT_LOSS},
            "port_load": {"node_id": "makhachkala", "before": 0.55, "after": 0.61},
            "status": status,
            "accepted_at": iso(ACCEPT_TS) if status == "accepted" else None,
            "accepted_via": "web" if status == "accepted" else None}


DECISION = {"id": "dec-001", "alert_id": "alert-001", "ts": iso(ACCEPT_TS), "accepted_via": "web",
            "items": [{"shipment_id": sid, "saved_hours": CALC[sid]["saved_hours"],
                       "saved_rub": CALC[sid]["saved_rub"], "co2_delta_kg": CALC[sid]["co2_delta"],
                       "sailing_id": FERRY_M} for sid in AFFECTED]}


def stats(phase):
    acc = phase == "accepted"
    return {"saved_hours": TOT_SAVED_H if acc else 0, "saved_rub": TOT_SAVED_RUB if acc else 0,
            "co2_saved_kg": -TOT_CO2 if acc else 0, "decisions": 1 if acc else 0,
            "shipments_total": len(IDS),
            "at_risk": sum(s["display_status"] == "at_risk" for s in SHIP[phase])}


def sailings(phase):
    out = copy.deepcopy(list(SAILINGS.values()))
    if phase == "accepted":
        for s in out:
            if s["id"] == FERRY_A:
                s["booked_t"] -= TOT_W
            if s["id"] == FERRY_M:
                s["booked_t"] += TOT_W
    return out


def passes(phase):
    ids = ["pass-01", "pass-02", "pass-03", "pass-04"]
    if phase == "accepted":
        ids += ["pass-05", "pass-01-r1", "pass-02-r1", "pass-03-r1"]
    out = [copy.deepcopy(PASSES[i]) for i in ids]
    if phase == "accepted":
        for p in out:
            if p["id"] in ("pass-01", "pass-02", "pass-03"):
                p["status"] = "reissued"
    return out


# ---------------- Запись ----------------
def dump(name: str, obj, model=None, many=False):
    if model is not None:  # моки обязаны проходить модели контракта
        for o in (obj if many else [obj]):
            model.model_validate(o)
    path = MOCK_DIR / f"{name}.json" if name != "seed" else DATA_DIR / "seed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for f in MOCK_DIR.glob("*.json"):
        f.unlink()
    graph = {"nodes": [dict(zip(("id", "name", "country", "type", "lat", "lon", "congestion"), n)) for n in NODES],
             "edges": list(EDGES.values())}
    dump("graph", graph, M.GraphOut)
    for ph, suf in (("initial", ""), ("storm", ".storm"), ("accepted", ".accepted")):
        dump(f"shipments{suf}", SHIP[ph], M.Shipment, many=True)
        alts = alternatives(ph)
        for v in alts.values():
            for a in v:
                M.AlternativeOut.model_validate(a)
        dump(f"alternatives{suf}", alts)
        dump(f"stats{suf}", stats(ph), M.StatsOut)
    dump("alerts", [])
    dump("alerts.storm", [alert("new")], M.Alert, many=True)
    dump("alerts.accepted", [alert("accepted")], M.Alert, many=True)
    dump("weather", weather(False), M.WeatherOut)
    dump("weather.storm", weather(True), M.WeatherOut)
    dump("scenario_presets", [{"key": "storm_north", "title": "Шторм на Северном Каспии"},
                              {"key": "storm_full", "title": "Шторм на всём море"},
                              {"key": "congestion_astrakhan", "title": "Затор в порту Астрахань"}],
         M.PresetOut, many=True)
    dump("scenario_storm_north", {"scenario": SCENARIO, "alert": alert("new")}, M.ScenarioCreateOut)
    dump("sailings", sailings("initial"), M.Sailing, many=True)
    dump("sailings.accepted", sailings("accepted"), M.Sailing, many=True)
    dump("ledger", CHAIN[:4], M.Block, many=True)
    dump("ledger.doc", CHAIN[:5], M.Block, many=True)
    dump("ledger.accepted", CHAIN, M.Block, many=True)
    dump("passes", passes("initial"), M.Pass, many=True)
    dump("passes.accepted", passes("accepted"), M.Pass, many=True)
    dump("documents", list(DOCS.values()), M.Document, many=True)
    dump("document_draft", DOC05_DRAFT, M.Document)
    dump("document_confirm", {"document": DOC05, "pass": PASSES["pass-05"], "block": CHAIN[4]},
         M.DocumentConfirmOut)
    dump("decision", DECISION, M.Decision)
    dump("accept", {"alert": alert("accepted"),
                    "shipments": [s for s in SHIP["accepted"] if s["id"] in AFFECTED],
                    "blocks": REISSUED_BLOCKS, "decision": DECISION, "already_accepted": False},
         M.AcceptOut)
    dump("seed", {"meta": {"now": iso(NOW), "timezone_note": "время сценария — МСК (UTC+3), в JSON — UTC",
                           "hour_cost_rub_per_t": HOUR_COST, "wave_limit_m": WAVE_LIMIT,
                           "co2_g_per_tkm": {k: v[2] for k, v in KINDS.items()},
                           "rate_rub_per_tkm": {k: v[1] for k, v in KINDS.items()}},
                  "nodes": graph["nodes"], "edges": graph["edges"], "sailings": sailings("initial"),
                  "shipments": SHIP["initial"], "documents": list(DOCS.values()),
                  "passes": passes("initial"), "ledger": CHAIN[:4]})

    # ---- сверка с DEMO_SCENARIO ----
    c1 = CALC["sh-01"]
    checks = [
        ("№01 бездействие, ₽", c1["loss"], 360000), ("№01 остаточная, ₽", c1["residual"], 45000),
        ("№01 доплата, ₽", c1["surcharge"], 16680), ("№01 экономия, ₽", c1["saved_rub"], 298320),
        ("№02 экономия, ₽", CALC["sh-02"]["saved_rub"], 198880),
        ("№03 экономия, ₽", CALC["sh-03"]["saved_rub"], 99440),
        ("№01 CO₂ план, кг", c1["co2_plan"], 13590), ("№01 CO₂ Махачкала, кг", c1["co2_alt"], 12678),
        ("№01 CO₂ %", round(c1["co2_delta"] / c1["co2_plan"] * 100, 1), -6.7),
        ("Итого груз-часы", TOT_SAVED_H, 126), ("Итого экономия, ₽", TOT_SAVED_RUB, 596640),
        ("Бездействие 3 груза, ₽", TOT_LOSS, 720000), ("Махачкала 3 груза, ₽", TOT_ALT, 123360),
        ("CO₂ 3 груза, кг", TOT_CO2, -1824), ("CO₂ 3 груза, %", TOT_CO2_PCT, -6.9),
        ("Бездействие, ч", DO_NOTHING_H, 48), ("Через Махачкалу, ч", c1["alt_delay"], 6),
    ]
    bad = 0
    for name, got, want in checks:
        ok = abs(got - want) < 1e-6
        bad += not ok
        print(f"{'OK ' if ok else 'ERR'} {name:28} {got:>12g}   ожидается {want:g}")
    print(f"\nМоки записаны в {MOCK_DIR}, сид — {DATA_DIR / 'seed.json'}")
    if bad:
        sys.exit(f"{bad} расхождений со сценарием")


if __name__ == "__main__":
    main()
