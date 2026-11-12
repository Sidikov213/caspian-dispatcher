"""Два понятия времени.

sim_now  — фиксированное «сейчас» сценария (DEMO_NOW). По нему считаются прогноз, рейсы, задержки,
           положение грузов. Не меняется, поэтому числа сценария не плывут.
event_ts — метка события (accepted_at, ts блока, выдача пропуска) = DEMO_NOW + реально прошедшее
           время с последнего reset. Записи реестра идут по порядку с разным временем.

В тестах и в gen_mocks — FixedClock: event_ts задаётся руками, прогон воспроизводится байт в байт.
"""
import time
from datetime import datetime, timedelta

from .util import parse


class Clock:
    def __init__(self, sim_now: str | datetime):
        self.sim_now: datetime = parse(sim_now)
        self.reset()

    def reset(self) -> None:
        self._t0 = time.monotonic()

    def event_ts(self) -> datetime:
        return self.sim_now + timedelta(seconds=int(time.monotonic() - self._t0))


class FixedClock(Clock):
    """event_ts не идёт сам; `at` можно выставить перед действием."""

    def reset(self) -> None:
        self.at: datetime = self.sim_now

    def set(self, at: str | datetime) -> None:
        self.at = parse(at)

    def event_ts(self) -> datetime:
        return self.at
