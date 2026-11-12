"""GET /api/data-sources: откуда система берёт данные и насколько они настоящие.

Типы: real — настоящие данные (прогноз, архив, публикации), modeled — смоделированы для демо
(в продакшене их дают порт и оператор парома), synthetic — сгенерированы (история стыковок для модели).
Плюс факты о коридоре из сида и сводка ретроспективной симуляции из data/backtest.json.
"""
import json
import logging

from .config import DATA_DIR
from .modelinfo import load_report

log = logging.getLogger("caspian")
BACKTEST_PATH = DATA_DIR / "backtest.json"


def load_backtest(path=BACKTEST_PATH) -> dict | None:
    """Сводка ретроспективной симуляции без длинных списков окон и рейсов."""
    try:
        bt = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        log.exception("backtest.json не читается")
        return None
    ports = {p: {k: v for k, v in s.items() if k != "window_list"} for p, s in bt["ports"].items()}
    sv = {k: v for k, v in bt["sailings"].items() if k != "closed_list"}
    return {**{k: bt[k] for k in ("title", "note", "source", "fetched_at", "period", "wave_limit_m", "schedule")},
            "ports": ports, "sailings": sv, "chart": "/backtest.png"}


def data_sources(st) -> dict:
    meta = st.meta
    weather = st.weather_out()
    report = load_report() or {}
    bt = load_backtest()
    ports = [n for n in st.graph.nodes.values() if n.get("facts")]
    port_sources = sorted({u for n in ports for u in n.get("sources") or []})
    sources = [
        {"id": "forecast", "title": "Прогноз волны и ветра",
         "provides": "Почасовая высота волны (Open-Meteo Marine) и ветер (Open-Meteo Forecast) на 7 дней в точках "
                     "моря у портов, обновление раз в 30 мин. Алерты строятся по ближайшим 48 ч",
         "type": "real", "url": "https://open-meteo.com/en/docs/marine-weather-api",
         "updated_at": weather.get("updated_at"),
         "note": None if weather.get("source") == "open-meteo" else f"сейчас источник: {weather.get('source')}"},
        {"id": "geography", "title": "География и расстояния",
         "provides": "Координаты портов, станций и переходов; длины рёбер графа сверены с длиной пути по "
                     "координатам (расхождение больше 15% исправлено, кроме ребра Энзели — Решт)",
         "type": "real", "url": "https://www.openstreetmap.org/", "updated_at": None, "note": None},
        {"id": "ports", "title": "Параметры портов",
         "provides": "Махачкала: незамерзающий, осадка до 4,5 м, грузооборот 2025 — 3,22 млн т, загрузка 64%. "
                     "Астрахань: замерзающий, выход по Волго-Каспийскому каналу ≈188 км",
         "type": "real", "url": port_sources[0] if port_sources else None, "urls": port_sources,
         "updated_at": "2026-06-09", "note": "загрузка остальных портов — оценка для демо"},
        {"id": "ice", "title": "Ледовая обстановка",
         "provides": "Главный сценарий ice_north: лёд на Волго-Каспийском канале, Астрахань и Оля закрыты "
                     "для отправления паромов; флаг льда идёт в модель (признак ice) и в расчёт закрытия порта",
         "type": "modeled", "url": "https://mintrans.gov.ru/file/396731", "updated_at": None,
         "note": ICE_NOTE},
        {"id": "sailings", "title": "Расписание и вместимость рейсов",
         "provides": "Паромы Астрахань и Махачкала → Энзели раз в 48 ч, вместимость и бронь",
         "type": "modeled", "url": None, "updated_at": None,
         "note": "демо-данные; в продакшене — оператор парома и порт"},
        {"id": "positions", "title": "Положение грузов",
         "provides": "Где груз сейчас — по плановым временам этапов маршрута",
         "type": "modeled", "url": None, "updated_at": None,
         "note": "демо-данные; в продакшене — трекинг перевозчиков"},
        {"id": "history", "title": "История стыковок для модели",
         "provides": f"Обучающая выборка классификатора срыва стыковки (CatBoost)"
                     + (f", {report['classifier']['n_train'] + report['classifier']['n_test']:,} стыковок".replace(",", " ")
                        if report.get("classifier") else ""),
         "type": "synthetic", "url": None, "updated_at": report.get("trained_at"),
         "note": "сгенерирована scripts/gen_history.py; метрики показывают работу конвейера, не точность"},
        {"id": "wave_history", "title": "Историческая волна для симуляции",
         "provides": "Почасовая высота волны за 12 месяцев у Астрахани, Оли и Махачкалы (архив Open-Meteo Marine) "
                     "— ретроспективная симуляция на исторической погоде, рейсы условные",
         "type": "real", "url": "https://open-meteo.com/en/docs/marine-weather-api",
         "updated_at": bt["fetched_at"] if bt else None, "note": None if bt else "симуляция ещё не запускалась"},
    ]
    return {"sources": sources, "corridor_facts": meta.get("corridor_facts", []), "backtest": bt,
            "ice": ice_block(bt)}


ICE_NOTE = ("Сценарий задан вручную по историческим срокам ледокольных проводок, "
            "живого источника ледовой обстановки нет")
SRC_MINTRANS = "https://mintrans.gov.ru/file/396731"
SRC_MKH = "https://www.alta.ru/logistics_news/128638/"
SRC_PORTNEWS = "https://en.portnews.ru/news/359334"


def ice_block(bt: dict | None) -> dict:
    """Почему главный сценарий — лёд: факты о северном Каспии и вывод ретроспективы по волне."""
    facts = [
        {"text": "Астрахань — замерзающий порт: зимой ледокольная проводка судов", "source": SRC_MINTRANS},
        {"text": "Выход в море — по Волго-Каспийскому морскому каналу, 101,5 мили (≈188 км)", "source": SRC_MINTRANS},
        {"text": "Ледокольные проводки сезона 2022/23: с 6 декабря 2022 по 7 марта 2023, 690 судов",
         "source": SRC_PORTNEWS},
        {"text": "Махачкала — единственный незамерзающий глубоководный порт России на Каспии", "source": SRC_MKH},
    ]
    conclusion = None
    if bt:
        p = bt["ports"]
        conclusion = (f"За 12 месяцев ({bt['period']['start']} — {bt['period']['end']}) волна от "
                      f"{str(bt['wave_limit_m']).replace('.', ',')} м не была ни в одном порту: максимум у Астрахани "
                      f"{str(p['astrakhan']['max_wave_m']).replace('.', ',')} м, у Махачкалы "
                      f"{str(p['makhachkala']['max_wave_m']).replace('.', ',')} м. Реальный риск северного Каспия — "
                      "лёд, поэтому главный сценарий — лёд, а шторм — стресс-тест.")
    return {"title": "Почему главный сценарий — лёд", "facts": facts, "note": ICE_NOTE, "conclusion": conclusion}
