"""Пресеты сценариев. Время — часы от sim_now, чтобы сценарий жил вместе с DEMO_NOW.

ice_north — главный сценарий DEMO_SCENARIO.md: лёд на Волго-Каспийском канале, Астрахань и Оля не
отправляют паромы с +36 ч до +55 ч (рейс А через 44 ч ждёт открытия 11 ч); после — очередь судов
(загрузка 85%) и таможня 2 ч. Погоду не трогает: волна остаётся реальной, закрытие порта — флаг льда.
storm_north — стресс-тест (за 12 месяцев волна у Астрахани не превышала 1,44 м): волна выше 2,5 м
в Астрахани и Оле в том же окне, пик 3,4 м; те же очередь и таможня.
storm_full — шторм на всём море: закрыты все паромные рёбра, обход только по суше (западная ветка).
congestion_astrakhan — затор в порту Астрахань без погоды: загрузка 95%, таможня 6 ч.
"""
import copy

from .hazards import note_of
from .util import H, iso

PRESETS = {
    "ice_north": {
        "id": "scn-ice-north", "type": "ice", "hazard": "ice", "title": "Лёд на Северном Каспии",
        "blocked_edges": ["e-astrakhan-anzali", "e-olya-anzali", "e-olya-amirabad"],
        "affected_nodes": ["astrakhan", "olya"],
        "start_h": 36, "end_h": 55, "params": {"wave_height_m": None, "wind_ms": None},
        "overlay": None, "ice": {"nodes": ["astrakhan", "olya"]},
        "congestion": {"astrakhan": 0.85}, "customs_h": {"astrakhan": 2},
        # Волго-Каспийский канал (от Астрахани по Бахтемиру к морю) и северная акватория до Оли
        "zone": [[46.5, 47.85], [46.45, 48.3], [46.05, 48.25], [45.75, 48.75], [45.45, 49.6],
                 [44.95, 49.4], [45.0, 48.4], [45.55, 47.6], [46.1, 47.55]],
    },
    "storm_north": {
        "id": "scn-storm-north", "type": "storm", "hazard": "storm", "title": "Шторм на Северном Каспии",
        "blocked_edges": ["e-astrakhan-anzali", "e-olya-anzali", "e-olya-amirabad"],
        "affected_nodes": ["astrakhan", "olya"],
        "start_h": 36, "end_h": 55, "params": {"wave_height_m": 3.4, "wind_ms": 18},
        "overlay": {"storm_nodes": ["astrakhan", "olya"], "peak": 3.4,
                    "bumps": {"makhachkala": [0.7, 50, 12]}},
        "congestion": {"astrakhan": 0.85}, "customs_h": {"astrakhan": 2},
        # Северный Каспий: дельта Волги, Астрахань, Оля, до широты Махачкалы не доходит
        "zone": [[46.75, 47.55], [46.75, 49.6], [46.2, 51.2], [45.1, 51.0], [44.45, 50.1],
                 [44.55, 48.4], [45.3, 47.3], [46.1, 47.15]],
    },
    "storm_full": {
        "id": "scn-storm-full", "type": "storm", "hazard": "storm", "title": "Шторм на всём Каспии",
        "blocked_edges": ["e-astrakhan-anzali", "e-olya-anzali", "e-olya-amirabad",
                          "e-makhachkala-anzali", "e-aktau-baku"],
        "affected_nodes": ["astrakhan", "olya", "makhachkala", "aktau", "baku"],
        "start_h": 36, "end_h": 80, "params": {"wave_height_m": 4.1, "wind_ms": 22},
        "overlay": {"storm_nodes": ["astrakhan", "olya", "makhachkala", "aktau", "baku",
                                    "anzali", "amirabad"], "peak": 4.1},
        "congestion": {"astrakhan": 0.85, "makhachkala": 0.8}, "customs_h": {"astrakhan": 2},
        # всё море с портами по берегам
        "zone": [[46.9, 47.1], [47.25, 51.3], [46.3, 53.3], [44.2, 51.5], [42.5, 52.9], [40.0, 53.4],
                 [38.3, 54.1], [36.7, 54.0], [36.6, 52.2], [37.0, 50.2], [37.3, 49.0], [38.6, 48.7],
                 [40.4, 49.5], [41.6, 48.4], [43.0, 47.2], [44.6, 46.7]],
    },
    "congestion_astrakhan": {
        "id": "scn-congestion-astrakhan", "type": "congestion", "hazard": "congestion",
        "title": "Затор в порту Астрахань",
        "blocked_edges": [], "affected_nodes": ["astrakhan"],
        "start_h": 18, "end_h": 48, "params": {"wave_height_m": None, "wind_ms": None},
        "overlay": None,
        "congestion": {"astrakhan": 0.95}, "customs_h": {"astrakhan": 6},
        "zone": [[46.55, 47.75], [46.55, 48.35], [46.15, 48.35], [46.15, 47.75]],   # порт Астрахань
    },
}

MAIN_PRESET = "ice_north"
PRESET_LIST = [{"key": k, "title": v["title"], "hazard": v["hazard"], "main": k == MAIN_PRESET,
                "note": note_of(v["hazard"])} for k, v in PRESETS.items()]


def make_scenario(key: str, sim_now) -> dict:
    """Сценарий в форме контракта + служебные поля с подчёркиванием (в ответ не попадают)."""
    p = copy.deepcopy(PRESETS[key])
    return {"id": p["id"], "type": p["type"], "hazard": p["hazard"], "note": note_of(p["hazard"]),
            "title": p["title"],
            "blocked_edges": p["blocked_edges"], "affected_nodes": p["affected_nodes"],
            "start": iso(sim_now + H(p["start_h"])), "end": iso(sim_now + H(p["end_h"])),
            "starts_in_h": p["start_h"],
            "params": p["params"], "zone": p.get("zone"),
            "_preset": key, "_overlay": p["overlay"], "_congestion": p["congestion"],
            "_customs_h": p["customs_h"], "_ice": p.get("ice")}


def public(scenario: dict) -> dict:
    return {k: v for k, v in scenario.items() if not k.startswith("_")}
