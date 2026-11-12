"""Шина событий. Состояние копит события в outbox (state.emit), `flush` раздаёт их подписчикам:
WebSocket-хабу сайта и мобилки и уведомителю Telegram-бота.

flush вызывают и HTTP-роуты, и обработчики бота, поэтому принятие с сайта бот видит так же, как своё.
"""
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

Subscriber = Callable[[str, object], Awaitable[None]]
_subscribers: list[Subscriber] = []


def subscribe(fn: Subscriber) -> None:
    if fn not in _subscribers:
        _subscribers.append(fn)


def unsubscribe(fn: Subscriber) -> None:
    if fn in _subscribers:
        _subscribers.remove(fn)


async def publish(type_: str, payload) -> None:
    for fn in list(_subscribers):
        try:
            await fn(type_, payload)
        except Exception:  # сбой одного подписчика не должен ронять запрос
            log.exception("подписчик %s упал на %s", getattr(fn, "__qualname__", fn), type_)


async def flush(state) -> None:
    for type_, payload in state.drain_events():
        await publish(type_, payload)
