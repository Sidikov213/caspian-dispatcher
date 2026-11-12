"""Настройки из backend/.env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
MOCK_DIR = DATA_DIR / "mock"
SEED_PATH = DATA_DIR / "seed.json"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("API_KEY", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")

# Пропуска в файлах моков подписаны этим публичным ключом, чтобы их можно было разобрать без .env.
# Живой сервер подписывает пропуска PASS_SECRET (JWT_SECRET из .env, если задан).
MOCK_JWT_SECRET = "caspian-mock-only-not-a-secret"
PASS_SECRET = JWT_SECRET or MOCK_JWT_SECRET

# «Сейчас» сценария (sim_now). Пусто — при каждом reset текущее время, отброшенное до часа,
# и сид сдвигается к нему. Задано (UTC, напр. 2026-11-12T11:00:00Z) — ручная фиксация.
DEMO_NOW = os.getenv("DEMO_NOW", "").strip() or None

# Якорь сценария: «сейчас» в docs/DEMO_SCENARIO.md, 12 ноя 14:00 МСК. На нём построены seed.json,
# моки и тесты; живой сервер сдвигает все времена сида на sim_now − SCENARIO_ANCHOR.
SCENARIO_ANCHOR = "2026-11-12T11:00:00Z"

# Погода: live — Open-Meteo Marine (кэш в файл, при сбое — кэш); synthetic — синтетический прогноз,
# сеть не трогаем (страховка на защиту: плохая погода или нет интернета).
WEATHER_MODE = os.getenv("WEATHER_MODE", "live").strip().lower()
WEATHER_CACHE_PATH = DATA_DIR / "weather_cache.json"

# Привязки Telegram (/start) переживают перезапуск сервера.
USERS_PATH = DATA_DIR / "users.json"

# Предиктор срыва стыковки: catboost (классификатор на синтетической истории) или formula.
# Нет модели или не импортируется catboost — откат на формулу с записью в лог.
PREDICTOR = os.getenv("PREDICTOR", "catboost").strip().lower()
MODEL_PATH = DATA_DIR / "model.cbm"               # классификатор срыва — используется сервером
SHIFT_MODEL_PATH = DATA_DIR / "model_shift.cbm"   # регрессор сдвига — только проверка, в расчёт не входит
MODEL_REPORT_PATH = DATA_DIR / "model_report.json"

# Аккаунты логиста и экспедитора (регистрация и вход). Не в git; переживают demo/reset и перезапуск.
ACCOUNTS_PATH = Path(os.getenv("ACCOUNTS_PATH", "").strip() or DATA_DIR / "accounts.json")

# Telegram: токен бота (бот и проверка initData мини-приложения), публичный адрес (кнопка меню и
# «Открыть пульт» в боте ведут на PUBLIC_URL/tg/), название демо-кабинета в приветствии и шапке.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
DEMO_COMPANY = os.getenv("DEMO_COMPANY", "").strip() or "Каспий Логистик"

# Пуши в мобильное приложение (FCM): путь к JSON-ключу сервисного аккаунта Firebase (не в git).
# Пусто — пуши выключены, токены устройств всё равно принимаются. Устройства переживают reset.
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS", "").strip()
DEVICES_PATH = Path(os.getenv("DEVICES_PATH", "").strip() or DATA_DIR / "devices.json")
MINIAPP_DIR = BASE_DIR / "app" / "miniapp"
