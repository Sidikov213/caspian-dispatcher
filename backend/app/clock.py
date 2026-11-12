"""Два понятия времени.

sim_now  — «сейчас» сценария. По нему считаются прогноз, рейсы, задержки, положение грузов.
           Без DEMO_NOW: при каждом reset = текущее время UTC, отброшенное до начала часа (10:52 → 10:00),
           и весь сид сдвигается к нему (state.py), поэтому шторм всегда через 36 ч, паром А через 44 ч.
           С DEMO_NOW: зафиксировано руками.
event_ts — метка события (accepted_at, ts блока, выдача пропуска). Без DEMO_NOW — настоящее время,
           с DEMO_NOW — DEMO_NOW + реально прошедшее с последнего reset.

Отбрасываем до часа, а не округляем к ближайшему: так event_ts никогда не раньше sim_now.
В тестах и в gen_mocks — FixedClock: event_ts задаётся руками, прогон воспроизводится байт в байт.
"""
import time
from datetime import datetime, timedelta, timezone

from .util import parse


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


class Clock:
    def __init__(self, demo_now: str | datetime | None = None, now=utcnow):
        self.fixed = parse(demo_now) if demo_now else None
        self._now = now
        self.reset()

    def reset(self) -> None:
        self._t0 = time.monotonic()
        self.sim_now: datetime = self.fixed or floor_hour(self._now())

    def event_ts(self) -> datetime:
        if self.fixed is None:
            return max(self._now(), self.sim_now)
        return self.sim_now + timedelta(seconds=int(time.monotonic() - self._t0))

    def real_now(self) -> datetime:
        """Настоящее время — для «Погода обновлена N мин назад»."""
        return self._now() if self.fixed is None else self.event_ts()


class FixedClock(Clock):
    """sim_now задан, event_ts не идёт сам; `at` можно выставить перед действием."""

    def __init__(self, sim_now: str | datetime):
        super().__init__(sim_now)

    def reset(self) -> None:
        self.sim_now = self.fixed
        self.at: datetime = self.sim_now

    def set(self, at: str | datetime) -> None:
        self.at = parse(at)

    def event_ts(self) -> datetime:
        return self.at

    def real_now(self) -> datetime:
        return self.sim_now
