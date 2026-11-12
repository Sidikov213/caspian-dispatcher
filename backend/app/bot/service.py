"""Логика бота без aiogram: что делает каждое нажатие и что ответить. Вызывает движок напрямую.

Действия идут через те же функции state, что и HTTP-роуты (accept под общим asyncio.Lock),
после каждого — events.flush: уведомитель бота и WebSocket получают изменения одинаково.
"""
from collections.abc import Awaitable, Callable

from ..errors import ApiError
from . import texts as T
from .keyboards import options_kb, retry_kb

STALE = "Это сообщение из прошлого прогона демо — актуальные алерты придут заново"


class BotService:
    def __init__(self, st, flush: Callable[[], Awaitable[None]]):
        self.st = st
        self.flush = flush

    # ---------------- пользователи и экраны ----------------

    def link(self, tg_id: int, name: str) -> str:
        self.st.link_user(tg_id, name)
        return T.welcome(name)

    def shipments(self):
        ships = self.st.shipments_list()  # для демо все грузы принадлежат каждому привязанному
        return T.shipments_message(self.st, ships), retry_kb(self.st.epoch, ships)

    def weather(self) -> str:
        return T.weather_message(self.st)

    # ---------------- алерт ----------------

    def _alert(self, epoch: int, aid: str):
        if epoch != self.st.epoch:
            return None, STALE
        a = self.st.alerts.get(aid)
        if a is None:
            return None, "Алерт не найден"
        if a["status"] != "new":
            return None, T.already(a)
        return a, None

    async def accept(self, epoch: int, aid: str, option_id: str | None = None, by: str | None = None) -> str:
        """by — имя пользователя Telegram: попадает в Alert.accepted_by и Decision.accepted_by."""
        a, msg = self._alert(epoch, aid)
        if a is None:
            return msg
        try:
            out = await self.st.accept(aid, "telegram", option_id,
                                       {"name": by, "role": "logist"} if by else None)
        except ApiError as e:
            await self.flush()
            if e.code == "superseded":
                return "Предложение устарело. Пересчитал — новое сообщение ниже"
            return e.message
        await self.flush()
        if out["already_accepted"]:
            return T.already(self.st.alerts[aid])
        return "Принято ✅"

    async def reject(self, epoch: int, aid: str) -> str:
        a, msg = self._alert(epoch, aid)
        if a is None:
            return msg
        await self.st.reject(aid)
        await self.flush()
        return "Отклонено: груз ждёт следующий рейс"

    def options(self, epoch: int, aid: str):
        """(текст, клавиатура) или (короткий ответ, None)."""
        a, msg = self._alert(epoch, aid)
        if a is None:
            return msg, None
        return T.options_message(a), options_kb(epoch, a)

    # ---------------- пропуск ----------------

    async def retry(self, epoch: int, sid: str) -> str:
        if epoch != self.st.epoch:
            return STALE
        try:
            out = await self.st.retry_pass(sid)
        except ApiError as e:
            return e.message
        finally:
            await self.flush()
        return T.retry_done(self.st, out)
