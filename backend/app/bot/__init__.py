"""Telegram-бот диспетчера (aiogram 3) внутри процесса бэкенда.

Polling — asyncio-задача в lifespan FastAPI. Бот вызывает функции движка напрямую, без HTTP,
и получает изменения (в том числе принятие с сайта) через шину событий app/events.py.
Если BOT_TOKEN пуст, сервер работает без бота и пишет об этом в лог.
"""
import asyncio
import logging
from dataclasses import dataclass

from .. import events
from .config import load
from .notifier import Notifier
from .service import BotService

log = logging.getLogger("caspian.bot")


@dataclass
class BotRuntime:
    bot: object
    dp: object
    task: asyncio.Task
    notifier: Notifier


async def start_bot(st) -> BotRuntime | None:
    settings = load()
    if not settings.bot_token:
        log.warning("BOT_TOKEN не задан — сервер работает без Telegram-бота")
        return None
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from .handlers import build_router

    try:
        bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    except Exception as e:  # токен неверного формата не должен ронять сервер
        log.error("BOT_TOKEN не подходит (%s) — сервер работает без Telegram-бота", e)
        return None
    service = BotService(st, lambda: events.flush(st))
    notifier = Notifier(bot, st)
    events.subscribe(notifier)
    dp = Dispatcher()
    dp.include_router(build_router(service, settings))

    async def run():
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot, handle_signals=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Telegram-бот остановился с ошибкой (проверьте BOT_TOKEN и сеть)")

    task = asyncio.create_task(run(), name="telegram-polling")
    log.info("Telegram-бот запущен (polling), ИИ для вопросов: %s",
             "включён" if settings.llm_enabled else "выключен — нет LLM_API_KEY")
    return BotRuntime(bot, dp, task, notifier)


async def stop_bot(rt: BotRuntime | None) -> None:
    if rt is None:
        return
    events.unsubscribe(rt.notifier)
    try:
        await rt.dp.stop_polling()
    except Exception:  # polling мог не начаться
        pass
    rt.task.cancel()
    try:
        await rt.task
    except (asyncio.CancelledError, Exception):
        pass
    await rt.bot.session.close()
