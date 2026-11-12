"""Роутер aiogram: тонкий слой над BotService."""
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from . import llm
from . import texts as T
from .keyboards import ACCEPT, CHOOSE, OPTIONS, REJECT, RETRY, main_menu, parse_cb
from .service import BotService


def build_router(service: BotService, settings) -> Router:
    r = Router()

    @r.message(CommandStart())
    async def start(m: Message):
        await m.answer(service.link(m.from_user.id, m.from_user.full_name), reply_markup=main_menu)

    @r.message(F.text == T.BTN_SHIPMENTS)
    async def shipments(m: Message):
        service.st.link_user(m.from_user.id, m.from_user.full_name)
        text, kb = service.shipments()
        await m.answer(text, reply_markup=kb)

    @r.message(F.text == T.BTN_WEATHER)
    async def weather(m: Message):
        await m.answer(service.weather())

    @r.callback_query(F.data.regexp(r"^[aorcp]:\d+:"))
    async def callbacks(q: CallbackQuery):
        action, epoch, arg, extra = parse_cb(q.data)
        if action == ACCEPT:
            await q.answer(await service.accept(epoch, arg, by=q.from_user.full_name))
        elif action == CHOOSE:
            await q.answer(await service.accept(epoch, arg, extra, by=q.from_user.full_name))
        elif action == REJECT:
            await q.answer(await service.reject(epoch, arg))
        elif action == OPTIONS:
            text, kb = service.options(epoch, arg)
            if kb is None:
                await q.answer(text)
            else:
                await q.answer()
                await q.message.answer(text, reply_markup=kb)
        elif action == RETRY:
            text = await service.retry(epoch, arg)
            await q.answer(text[:190])
            await q.message.answer(text)

    @r.message(F.text)
    async def free_text(m: Message):
        if settings.llm_enabled:
            await m.bot.send_chat_action(m.chat.id, ChatAction.TYPING)
            out = await llm.answer(service.st, settings, m.from_user.id, m.text)
            if out:
                await m.answer(escape(out), reply_markup=main_menu)
                return
        await m.answer(T.hint(), reply_markup=main_menu)

    return r
