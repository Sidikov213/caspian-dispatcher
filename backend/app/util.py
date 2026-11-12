"""Время, форматирование чисел и подписей. Время сценария — МСК, в JSON — UTC."""
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))
MONTHS = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s: str | datetime) -> datetime:
    if isinstance(s, datetime):
        return s
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def hours(a, b) -> float:
    return (parse(b) - parse(a)).total_seconds() / 3600


def H(x: float) -> timedelta:
    return timedelta(hours=x)


def ru(x: float, d: int = 1) -> str:
    """3.4 → «3,4»."""
    return f"{x:.{d}f}".replace(".", ",")


def signed(x: float, d: int = 1) -> str:
    """−1,8 с настоящим минусом."""
    return ru(x, d).replace("-", "−")


def k_rub(x: float) -> str:
    return f"{round(x / 1000)} тыс ₽"


def num(x: float) -> str:
    """48.0 → «48», 6.5 → «6,5»."""
    return f"{x:g}".replace(".", ",")


def day_time(dt) -> str:
    """«14 ноя, 10:00» по Москве."""
    d = parse(dt).astimezone(MSK)
    return f"{d.day} {MONTHS[d.month - 1]}, {d:%H:%M}"


def day_only(dt) -> str:
    d = parse(dt).astimezone(MSK)
    return f"{d.day} {MONTHS[d.month - 1]}"


def time_only(dt) -> str:
    return f"{parse(dt).astimezone(MSK):%H:%M}"


_CARGO_NOM = {1: "груз", 2: "груза", 3: "груза", 4: "груза"}
_CARGO_DAT = {1: "одному грузу", 2: "двум грузам", 3: "трём грузам", 4: "четырём грузам",
              5: "пяти грузам"}


def cargo_word(n: int) -> str:
    """«3 груза», «5 грузов»."""
    if n % 10 in _CARGO_NOM and n % 100 not in (11, 12, 13, 14):
        return f"{n} {_CARGO_NOM[n % 10]}"
    return f"{n} грузов"


def cargo_dative_words(n: int) -> str:
    """«по трём грузам»."""
    return _CARGO_DAT.get(n, f"{n} грузам")


def cargo_dative(n: int) -> str:
    """«по 3 грузам», «по 1 грузу»."""
    return f"{n} грузу" if n % 10 == 1 and n % 100 != 11 else f"{n} грузам"
