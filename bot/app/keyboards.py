from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_ASK = "💬 Спросить ИИ"
BTN_NEW = "📝 Оставить заявку"
BTN_MY = "📋 Мои заявки"
BTN_ABOUT = "ℹ️ О проекте"

main_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_ASK), KeyboardButton(text=BTN_NEW)],
              [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_ABOUT)]],
    resize_keyboard=True,
)
