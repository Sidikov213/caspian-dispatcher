"""Клавиатуры. В callback_data — номер прогона демо (state.epoch): после reset старые кнопки не сработают
на новые алерты с теми же id. Формат: «действие:прогон:аргумент[:вариант]», не длиннее 64 байт."""
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
                           WebAppInfo)

from .. import config

from .texts import BTN_SHIPMENTS, BTN_WEATHER

ACCEPT, OPTIONS, REJECT, CHOOSE, RETRY = "a", "o", "r", "c", "p"

main_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_SHIPMENTS), KeyboardButton(text=BTN_WEATHER)]],
    resize_keyboard=True,
)


def cb(action: str, epoch: int, arg: str, extra: str | None = None) -> str:
    return ":".join([action, str(epoch), arg] + ([extra] if extra else []))


def parse_cb(data: str) -> tuple[str, int, str, str | None]:
    parts = data.split(":")
    return parts[0], int(parts[1]), parts[2], parts[3] if len(parts) > 3 else None


def alert_kb(epoch: int, alert: dict) -> InlineKeyboardMarkup:
    has_route = any(o["id"] != "wait" for o in alert.get("options", []))
    # «Открыть пульт» — мини-приложение на вкладке «Решения»; только если задан PUBLIC_URL
    pult = ([[InlineKeyboardButton(text="📱 Открыть пульт", web_app=WebAppInfo(url=f"{config.PUBLIC_URL}/tg/?tab=decisions"))]]
            if config.PUBLIC_URL else [])
    if not has_route:  # предложения нет — только подтвердить, что увидели
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Понятно, ждём рейс", callback_data=cb(ACCEPT, epoch, alert["id"]))]] + pult)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=cb(ACCEPT, epoch, alert["id"]))],
        [InlineKeyboardButton(text="🔀 Другие варианты", callback_data=cb(OPTIONS, epoch, alert["id"])),
         InlineKeyboardButton(text="✖️ Отклонить", callback_data=cb(REJECT, epoch, alert["id"]))],
    ] + pult)


def options_kb(epoch: int, alert: dict) -> InlineKeyboardMarkup:
    rows = []
    for n, o in enumerate(alert["options"], 1):
        if o["id"] == "wait":
            rows.append([InlineKeyboardButton(text=f"{n}. Ждать следующий рейс",
                                              callback_data=cb(REJECT, epoch, alert["id"]))])
        else:
            rows.append([InlineKeyboardButton(text=f"{n}. Выбрать" + (" ⭐" if o["recommended"] else ""),
                                              callback_data=cb(CHOOSE, epoch, alert["id"], o["id"]))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def retry_kb(epoch: int, ships: list[dict]) -> InlineKeyboardMarkup | None:
    rows = [[InlineKeyboardButton(text=f"🔁 Повторить №{sh['id'].split('-')[-1]}",
                                  callback_data=cb(RETRY, epoch, sh["id"]))]
            for sh in ships if sh["pass_state"] == "reissue_pending"]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
