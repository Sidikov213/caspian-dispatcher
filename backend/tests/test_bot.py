"""Telegram-бот с подменённым Bot API: рассылка, принятие с двух платформ, повтор, superseded."""
import asyncio
import logging

import pytest

from app import events
from app.bot import start_bot
from app.bot import texts as T
from app.bot.config import BotSettings
from app.bot.handlers import build_router
from app.bot.keyboards import parse_cb
from app.bot.llm import answer as llm_answer
from app.bot.notifier import Notifier
from app.bot.service import STALE, BotService

FERRY_M = "sl-mkh-anz-1115"
USERS = {501: "Логист Аня", 502: "Логист Борис"}


class FakeMsg:
    def __init__(self, message_id):
        self.message_id = message_id


class FakeBot:
    """Записывает вызовы Bot API вместо Telegram."""

    def __init__(self):
        self.sent, self.edits, self._id = [], [], 100

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self._id += 1
        self.sent.append({"chat_id": chat_id, "text": text, "kb": reply_markup, "message_id": self._id})
        return FakeMsg(self._id)

    async def edit_message_text(self, text, chat_id=None, message_id=None, reply_markup=None, **kw):
        await asyncio.sleep(0)  # даём шанс гонке
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text, "kb": reply_markup})


@pytest.fixture
def bot_env(st):
    fake = FakeBot()
    notifier = Notifier(fake, st)
    events.subscribe(notifier)
    for uid, name in USERS.items():
        st.link_user(uid, name)
    service = BotService(st, lambda: events.flush(st))
    st.clock.set("2026-11-12T11:32:00Z")  # 14:32 МСК — метка принятия
    yield st, fake, service
    events.unsubscribe(notifier)


def storm(st):
    async def go():
        await st.run_scenario("storm_north")
        await events.flush(st)
    asyncio.run(go())


def buttons(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row]


def alert_msgs(fake, aid="alert-001"):
    return [m for m in fake.sent if m["kb"] is not None and any(aid in c for c in buttons(m["kb"]))]


# ---------------- рассылка ----------------

def test_alert_is_sent_to_every_linked_user(bot_env):
    st, fake, _ = bot_env
    storm(st)
    msgs = alert_msgs(fake)
    assert sorted(m["chat_id"] for m in msgs) == sorted(USERS)
    text = msgs[0]["text"]
    assert text.startswith("<b>🔴 Шторм на Северном Каспии: 3 груза под риском</b>\n\n14 ноя 02:00–21:00, волна")
    assert text.count("Шторм на Северном Каспии") == 1                 # заголовок не повторяется
    for part in ("Риск срыва стыковки до <b>82%</b>", "если рейс А отменят", "прибытие <b>+48 ч</b>",
                 "720 тыс ₽", "Через Махачкалу (паром М, 15 ноя, 06:00): прибытие <b>+6 ч</b> к плану",
                 "<b>Расчётная экономия по 3 грузам: 126 груз-часов, 597 тыс ₽",
                 "Загрузка порта Махачкала после переноса: 55% → 61%"):
        assert part in text, part
    assert text.count("\n\n") == 4                                    # заголовок + 4 блока
    site = st.alerts["alert-001"]["text"]                              # сайту — без разметки
    assert "<b>" not in site and "\x01" not in site and site.startswith("⚠️ Шторм на Северном Каспии: ")
    e = st.epoch
    assert buttons(msgs[0]["kb"]) == [f"a:{e}:alert-001", f"o:{e}:alert-001", f"r:{e}:alert-001"]
    assert [b.text for row in msgs[0]["kb"].inline_keyboard for b in row] == \
           ["✅ Принять", "🔀 Другие варианты", "✖️ Отклонить"]


# ---------------- принятие ----------------

def test_bot_and_site_accept_at_once_one_decision_one_edit(bot_env):
    st, fake, service = bot_env
    storm(st)

    async def site():
        try:
            return await st.accept("alert-001", "web")
        finally:
            await events.flush(st)

    async def both():
        return await asyncio.gather(service.accept(st.epoch, "alert-001"), site())

    bot_answer, site_out = asyncio.run(both())
    assert len(st.decisions) == 1
    assert st.sailings[FERRY_M]["booked_t"] == 760 + 120
    assert len(fake.edits) == len(USERS)                         # по одному на каждое сообщение
    assert {(e["chat_id"], e["message_id"]) for e in fake.edits} == \
           {(m["chat_id"], m["message_id"]) for m in alert_msgs(fake)}
    assert all(e["kb"] is None for e in fake.edits)
    via = st.alerts["alert-001"]["accepted_via"]
    suffix = "✅ Принято в 14:32 " + ("с сайта" if via == "web" else "из Telegram")
    assert all(suffix in e["text"] for e in fake.edits)
    if via == "web":
        assert bot_answer == "Уже принято в 14:32 с сайта" and site_out["already_accepted"] is False
    else:
        assert bot_answer == "Принято ✅" and site_out["already_accepted"] is True
    summaries = [m for m in fake.sent if m["text"].startswith("<b>✅ Решение принято")]
    assert sorted(m["chat_id"] for m in summaries) == sorted(USERS)
    s = summaries[0]["text"]
    assert s.split("\n") == [
        "<b>✅ Решение принято</b>", "",
        "№01, №02, №03 идут через Махачкалу, паром М, 15 ноя, 06:00, прибытие +6 ч к плану",
        "Пропуска переоформлены на порт Махачкала",
        "Реестр: 3 записи о переоформлении, цепочка цела",
        "<b>Расчётная экономия по 3 грузам: 126 груз-часов, 597 тыс ₽, −6,9% CO₂</b>"]
    assert "pass-" not in s


def test_site_accept_edits_bot_message(bot_env):
    st, fake, _ = bot_env
    storm(st)

    async def site():
        await st.accept("alert-001", "web")
        await events.flush(st)
    asyncio.run(site())
    assert len(fake.edits) == 2 and all("Принято в 14:32 с сайта" in e["text"] for e in fake.edits)


def test_repeated_click_is_short_answer(bot_env):
    st, fake, service = bot_env
    storm(st)
    assert asyncio.run(service.accept(st.epoch, "alert-001")) == "Принято ✅"
    n_edits, n_sent = len(fake.edits), len(fake.sent)
    assert asyncio.run(service.accept(st.epoch, "alert-001")) == "Уже принято в 14:32 из Telegram"
    assert asyncio.run(service.reject(st.epoch, "alert-001")) == "Уже принято в 14:32 из Telegram"
    assert service.options(st.epoch, "alert-001") == ("Уже принято в 14:32 из Telegram", None)
    assert (len(fake.edits), len(fake.sent), len(st.decisions)) == (n_edits, n_sent, 1)
    assert asyncio.run(service.accept(st.epoch - 1, "alert-001")) == STALE


def test_superseded_removes_buttons_and_sends_new_alert(bot_env):
    st, fake, service = bot_env
    storm(st)
    st.sailings[FERRY_M]["booked_t"] = 1150                     # место заняли
    ans = asyncio.run(service.accept(st.epoch, "alert-001"))
    assert ans.startswith("Предложение устарело")
    assert st.alerts["alert-001"]["status"] == "superseded" and not st.decisions
    old = {(m["chat_id"], m["message_id"]) for m in alert_msgs(fake, "alert-001")}
    assert {(e["chat_id"], e["message_id"]) for e in fake.edits} == old
    assert all(e["kb"] is None and "Предложение устарело" in e["text"] for e in fake.edits)
    new = alert_msgs(fake, "alert-002")
    assert sorted(m["chat_id"] for m in new) == sorted(USERS)
    assert asyncio.run(service.accept(st.epoch, "alert-001")) == T.already(st.alerts["alert-001"])
    assert asyncio.run(service.accept(st.epoch, "alert-002")) == "Принято ✅"
    assert len(st.decisions) == 1


def test_reject_edits_message(bot_env):
    st, fake, service = bot_env
    storm(st)
    assert asyncio.run(service.reject(st.epoch, "alert-001")).startswith("Отклонено")
    assert len(fake.edits) == 2 and all("Отклонено" in e["text"] for e in fake.edits)


# ---------------- другие варианты ----------------

def test_other_options_and_choice(bot_env):
    st, fake, service = bot_env
    storm(st)
    text, kb = service.options(st.epoch, "alert-001")
    assert text.count("к плану") == 3
    assert "На 42 ч быстрее ожидания следующего рейса · расчётная экономия 597 тыс ₽" in text
    assert "На 35 ч быстрее ожидания следующего рейса" in text
    assert "Это и есть ожидание следующего рейса" in text
    data = buttons(kb)
    e = st.epoch
    assert data == [f"c:{e}:alert-001:mkh", f"c:{e}:alert-001:west", f"r:{e}:alert-001"]
    _, epoch, aid, opt = parse_cb(data[1])
    assert asyncio.run(service.accept(epoch, aid, opt)) == "Принято ✅"
    assert {st.shipments[s]["route"]["id"].rsplit("-", 1)[-1] for s in ("sh-01", "sh-02", "sh-03")} == {"west"}
    assert st.stats()["saved_rub"] == st.alerts["alert-001"]["totals"]["saved_rub"] != 596640


# ---------------- мои грузы, повтор пропуска ----------------

def test_shipments_list_and_retry(bot_env):
    st, fake, service = bot_env
    text, kb = service.shipments()
    assert "🔵 <b>№01 Зерно</b>, 60 т · Москва → Мумбаи" in text and "⚪ <b>№05 Удобрения</b>" in text
    assert kb is None
    storm(st)
    text = service.shipments()[0]
    assert "🔴 <b>№01 Зерно</b>" in text and "Под риском 82%" in text
    st.arm_pass_failure()
    asyncio.run(service.accept(st.epoch, "alert-001"))
    text, kb = service.shipments()
    assert "🟢 <b>№01 Зерно</b>" in text and "+6 ч к плану" in text
    assert "⚠️ №01: маршрут изменён, пропуск ожидает переоформления" in text
    assert buttons(kb) == [f"p:{st.epoch}:sh-01"]
    summary = next(m["text"] for m in fake.sent if m["text"].startswith("<b>✅ Решение принято"))
    assert "Пропуска переоформлены на порт Махачкала (№02, №03); ⚠️ №01: пропуск ожидает переоформления" in summary
    assert "Реестр: 2 записи о переоформлении" in summary and "pass-" not in summary
    out = asyncio.run(service.retry(st.epoch, "sh-01"))
    assert out == "✅ №01: пропуск переоформлен на порт Махачкала, старый отозван"
    assert asyncio.run(service.retry(st.epoch, "sh-01")) == out  # повтор не выпускает новый
    assert service.shipments()[1] is None and len(st.decisions) == 1


def test_weather_message(bot_env):
    st, _, service = bot_env
    storm(st)
    text = service.weather()
    assert "🔴 <b>Астрахань</b>" in text and "до 3,4 м" in text and "🟢 <b>Махачкала</b>" in text
    assert "Погода обновлена 12 мин назад" in text and "демо-данные" in text


# ---------------- общее ----------------

def test_users_survive_reset_and_epoch_grows(bot_env):
    st, _, _ = bot_env
    e = st.epoch
    st.reset()
    assert set(st.users) == set(USERS) and st.epoch == e + 1


def test_formats_section9():
    from app.util import day_time, k_rub
    assert (T.h(18), T.h(-3), T.h(0), T.h(6.5)) == ("+18 ч", "−3 ч", "0 ч", "+6,5 ч")
    assert T.pct(0.82) == "82%" and T.co2_pct(-6.7) == "−6,7% CO₂"
    assert k_rub(298320) == "298 тыс ₽" and day_time("2026-11-12T11:30:00Z") == "12 ноя, 14:30"


def test_server_starts_without_token(st, caplog):
    with caplog.at_level(logging.WARNING):
        assert asyncio.run(start_bot(st)) is None
    assert "BOT_TOKEN не задан" in caplog.text


def test_router_builds_and_llm_off(st):
    from aiogram import Dispatcher
    settings = BotSettings(bot_token="", llm_base_url="x", llm_api_key="", llm_model="m")
    Dispatcher().include_router(build_router(BotService(st, lambda: events.flush(st)), settings))
    assert asyncio.run(llm_answer(st, settings, 1, "где мой груз?")) is None


def test_bad_token_does_not_crash(st, monkeypatch, caplog):
    monkeypatch.setenv("BOT_TOKEN", "not-a-token")
    with caplog.at_level(logging.ERROR):
        assert asyncio.run(start_bot(st)) is None
    assert "BOT_TOKEN" in caplog.text


# ---------------- лог отправки и правки ----------------

def test_bot_logs_send_and_edit_without_text(bot_env, caplog):
    import logging
    st, fake, service = bot_env
    with caplog.at_level(logging.INFO, logger="caspian.bot"):
        storm(st)
        asyncio.run(service.accept(st.epoch, "alert-001"))
    lines = [r.getMessage() for r in caplog.records if r.name == "caspian.bot" and r.levelno == logging.INFO]
    n = len(USERS)
    assert f"Бот: алерт alert-001 отправлен, получателей {n} из {n}" in lines
    assert f"Бот: алерт alert-001 — сообщения отредактированы (accepted), получателей {n} из {n}" in lines
    assert f"Бот: итог принятия alert-001 отправлен, получателей {n} из {n}" in lines
    joined = "\n".join(lines)
    assert "Махачкал" not in joined and all(str(uid) not in joined for uid in USERS)   # ни текста, ни chat_id
