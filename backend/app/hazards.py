"""Тексты по типу угрозы (hazard) — одно место для заголовков, текста алерта, факторов, бота и карточки.

hazard: ice | storm | congestion | customs. Числа сюда приходят готовыми, здесь только слова.
Для льда — без слов «волна» и «шторм»: лёд на Волго-Каспийском канале, канал закрыт для проводки.
Шторм остаётся стресс-тестом: подпись STRESS_NOTE в списке сценариев и в карточке алерта.
"""
import json
from datetime import datetime

from .config import DATA_DIR
from .util import MSK, num, parse, ru

HAZARDS = ("ice", "storm", "congestion", "customs")

ICON = {"ice": "🧊", "storm": "🌊", "congestion": "🚢", "customs": "🛃"}
LABEL = {"ice": "Лёд", "storm": "Шторм", "congestion": "Затор в порту", "customs": "Очередь на таможне"}
# Подзаголовок угрозы в карточке и на сайте («Прогноз шторма / через 36 ч»).
KICKER = {"ice": "Ледовая обстановка", "storm": "Прогноз шторма", "congestion": "Затор в порту",
          "customs": "Очередь на таможне"}

# Ледокольные проводки в Волго-Каспийском канале обычно начинаются в начале декабря (6.12.2022).
ICE_SEASON_START = (12, 6)


def _backtest_max_astrakhan() -> float:
    """Максимум волны у Астрахани за 12 месяцев из ретроспективной симуляции (data/backtest.json)."""
    try:
        bt = json.loads((DATA_DIR / "backtest.json").read_text(encoding="utf-8"))
        return float(bt["ports"]["astrakhan"]["max_wave_m"])
    except (OSError, ValueError, KeyError, TypeError):
        return 1.44


def stress_note() -> str:
    return (f"Стресс-тест: за 12 месяцев волна у Астрахани не превышала "
            f"{ru(_backtest_max_astrakhan(), 2)} м")


def note_of(hazard: str | None) -> str | None:
    """Подпись сценария: у шторма — стресс-тест, у остальных нет."""
    return stress_note() if hazard == "storm" else None


def early_ice(ts) -> bool:
    """Лёд раньше обычного начала проводок (6 декабря) — «раннее ледообразование»."""
    d = parse(ts).astimezone(MSK)
    return (d.month, d.day) < ICE_SEASON_START and d.month >= 10


def headline(sc: dict) -> str:
    """Короткий заголовок угрозы — название сценария или угрозы наблюдателя."""
    return sc["title"]


def alert_head(sc: dict, span: str, lead: str, *, wave_limit: float, port_load: int | None = None,
               customs_h: float | None = None) -> str:
    """Первая строка текста алерта: когда и что случилось."""
    hz = sc.get("hazard") or ("storm" if sc["type"] == "storm" else sc["type"])
    if hz == "ice":
        early = ", раннее ледообразование" if early_ice(sc["start"]) else ""
        return (f"{lead}{span}, лёд на Волго-Каспийском канале{early}: канал закрыт для проводки, "
                f"порты Астрахань и Оля не отправляют паромы.")
    if hz == "storm":
        return f"{lead}{span}, волна до {ru(sc['params']['wave_height_m'])} м (предел парома {ru(wave_limit)} м)."
    return f"{lead}{span}, загрузка порта {port_load}%, таможня до {num(customs_h)} ч."


def closure_factor(reason: str | None, wave_max: float, hours_closed: float) -> dict:
    """Фактор «порт закрыт» в Risk.factors — назван по причине закрытия."""
    if reason == "ice":
        return {"name": "ice", "label": "Лёд: канал закрыт для проводки", "impact_hours": hours_closed}
    return {"name": "wave_height", "label": f"Волна {ru(wave_max)} м", "impact_hours": hours_closed}


def card_metrics(hz: str, *, closure_h: float | None, wave_m: float | None, wave_limit: float,
                 port_load: int | None, customs_h: float | None) -> list[dict]:
    """Готовые строки для карточки алерта: набор зависит от типа угрозы."""
    closed = [] if closure_h is None else [{"key": "closure_h", "label": "Закрытие порта",
                                            "value": f"{num(closure_h)} ч"}]
    if hz == "ice":
        return [{"key": "channel", "label": "Волго-Каспийский канал", "value": "закрыт для проводки"}] + closed
    if hz == "storm":
        return [{"key": "wave", "label": "Волна", "value": f"до {ru(wave_m or 0)} м"},
                {"key": "wave_limit", "label": "Предел парома", "value": f"{ru(wave_limit)} м"}] + closed
    out = []
    if port_load is not None:
        out.append({"key": "port_load", "label": "Загрузка порта", "value": f"{port_load}%"})
    if customs_h is not None:
        out.append({"key": "customs_h", "label": "Таможня", "value": f"до {num(customs_h)} ч"})
    return out


def now_msk() -> datetime:
    return datetime.now(MSK)
