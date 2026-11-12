import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from . import backend, llm
from .config import settings
from .keyboards import BTN_ABOUT, BTN_ASK, BTN_MY, BTN_NEW, main_menu

router = Router()
log = logging.getLogger(__name__)

# ====== Меняется под кейс за 5 минут ======
PROJECT_NAME = "Название проекта"
ABOUT_TEXT = "Коротко: какую проблему решаем и для кого."
ITEM_SCHEMA = '{"category": "строка", "description": "строка", "address": "строка или null", "urgency": "low|medium|high"}'
# ==========================================


class NewItem(StatesGroup):
    waiting_text = State()


@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await backend.register_user(m.from_user.id, m.from_user.full_name)
    await m.answer(f"👋 Привет, {m.from_user.first_name}! Это <b>{PROJECT_NAME}</b>.\n{ABOUT_TEXT}",
                   reply_markup=main_menu)


@router.message(F.text == BTN_ABOUT)
async def about(m: Message):
    await m.answer(f"<b>{PROJECT_NAME}</b>\n{ABOUT_TEXT}")


@router.message(Command("reset"))
async def reset(m: Message, state: FSMContext):
    await state.clear()
    llm.reset(m.from_user.id)
    await m.answer("🧹 Контекст очищен.", reply_markup=main_menu)


@router.message(F.text == BTN_ASK)
async def ask_hint(m: Message):
    await m.answer("Просто напишите вопрос — я отвечу. /reset — начать заново.")


# --- Заявка: свободный текст -> ИИ структурирует -> бэкенд ---
@router.message(F.text == BTN_NEW)
async def new_item(m: Message, state: FSMContext):
    await state.set_state(NewItem.waiting_text)
    await m.answer("Опишите своими словами (можно одним сообщением) — ИИ сам разложит по полям.")


@router.message(NewItem.waiting_text, F.text)
async def new_item_text(m: Message, state: FSMContext):
    await state.clear()
    await m.bot.send_chat_action(m.chat.id, "typing")
    data = await llm.extract(m.text, ITEM_SCHEMA)
    data["source_text"] = m.text
    try:
        item = await backend.create_item(m.from_user.id, data)
    except Exception:
        log.exception("create_item failed")
        await m.answer("⚠️ Не удалось сохранить, попробуйте ещё раз.", reply_markup=main_menu)
        return
    fields = "\n".join(f"• <b>{k}</b>: {v}" for k, v in data.items() if k != "source_text")
    await m.answer(f"✅ Заявка №{item.get('id', '—')} принята\n{fields}", reply_markup=main_menu)


@router.message(F.text == BTN_MY)
async def my_items(m: Message):
    items = await backend.list_items(m.from_user.id)
    if not items:
        await m.answer("Заявок пока нет.")
        return
    lines = [f"№{i.get('id')} · {i.get('category', '—')} · {i.get('status', 'new')}" for i in items[-10:]]
    await m.answer("📋 Ваши заявки:\n" + "\n".join(lines))


# --- Админка ---
@router.message(Command("stats"), F.from_user.id.in_(settings.admin_ids))
async def stats(m: Message):
    items = await backend.list_items()
    users = await backend.all_user_ids()
    await m.answer(f"👥 Пользователей: {len(users)}\n📝 Заявок: {len(items)}")


@router.message(Command("broadcast"), F.from_user.id.in_(settings.admin_ids))
async def broadcast(m: Message):
    text = m.text.removeprefix("/broadcast").strip()
    if not text:
        await m.answer("Использование: /broadcast текст")
        return
    sent = 0
    for uid in await backend.all_user_ids():
        try:
            await m.bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await m.answer(f"📣 Отправлено: {sent}")


# --- Всё остальное — в ИИ ---
@router.message(F.text)
async def free_chat(m: Message):
    await m.bot.send_chat_action(m.chat.id, "typing")
    await m.answer(await llm.ask(m.from_user.id, m.text))
