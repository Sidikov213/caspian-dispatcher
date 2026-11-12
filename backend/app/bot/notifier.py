"""Уведомитель: подписан на шину событий.

alert.created → сообщение каждому привязанному пользователю с кнопками; бот запоминает, куда отправил.
alert.updated (accepted / rejected / superseded) → ровно одно редактирование каждого сообщения:
кнопки убраны, дописан итог («Принято в 14:32 с сайта»); после принятия — сообщение с итогом.
Неважно, где нажали «Принять»: сайт и бот приходят сюда одним и тем же событием.
"""
import asyncio
import logging
from collections import defaultdict

from . import texts as T
from .keyboards import alert_kb

# «caspian.bot» — тот же логгер, что у запуска бота: его настраивает main.py, INFO виден в консоли.
# Пишем только тип события, alert_id и число получателей — без текста сообщений и без chat_id.
log = logging.getLogger("caspian.bot")


class Notifier:
    def __init__(self, bot, st):
        self.bot = bot
        self.st = st
        self.sent: dict[tuple[int, str], list[tuple[int, int, str]]] = defaultdict(list)
        self.finalized: set[tuple[int, str]] = set()
        self.lock = asyncio.Lock()

    async def __call__(self, type_: str, payload) -> None:
        if type_ == "alert.created":
            await self.on_created(payload)
        elif type_ == "alert.updated":
            await self.on_updated(payload)

    async def on_created(self, alert: dict) -> None:
        key = (self.st.epoch, alert["id"])
        text = T.alert_message(self.st, alert)
        kb = alert_kb(self.st.epoch, alert)
        for uid in list(self.st.users):
            try:
                msg = await self.bot.send_message(uid, text, reply_markup=kb)
            except Exception:
                log.exception("не отправил алерт %s пользователю %s", alert["id"], uid)
                continue
            self.sent[key].append((uid, msg.message_id, text))
        log.info("Бот: алерт %s отправлен, получателей %d из %d", alert["id"], len(self.sent[key]),
                 len(self.st.users))

    async def on_updated(self, alert: dict) -> None:
        if alert["status"] == "new":
            return
        key = (self.st.epoch, alert["id"])
        async with self.lock:
            if key in self.finalized:
                return
            self.finalized.add(key)
        suffix = T.alert_suffix(alert)
        if alert["status"] == "accepted" and not any(i["action"] == "reroute" for i in alert["items"]):
            suffix = T.no_proposal_ack(alert)
        targets = self.sent.get(key, [])
        edited = 0
        for chat_id, message_id, text in targets:
            try:
                await self.bot.edit_message_text(f"{text}\n\n<b>{suffix}</b>", chat_id=chat_id,
                                                 message_id=message_id, reply_markup=None)
                edited += 1
            except Exception:
                log.exception("не отредактировал сообщение %s/%s", chat_id, message_id)
        if targets:
            log.info("Бот: алерт %s — сообщения отредактированы (%s), получателей %d из %d",
                     alert["id"], alert["status"], edited, len(targets))
        result = self.st.accept_results.get(alert["id"])
        if alert["status"] == "accepted" and result and result["shipments"]:
            summary = T.accept_summary(self.st, result)
            users, sent = list(self.st.users), 0
            for uid in users:
                try:
                    await self.bot.send_message(uid, summary)
                    sent += 1
                except Exception:
                    log.exception("не отправил итог пользователю %s", uid)
            log.info("Бот: итог принятия %s отправлен, получателей %d из %d", alert["id"], sent, len(users))
