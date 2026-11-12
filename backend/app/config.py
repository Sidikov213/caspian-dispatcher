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

# «Сейчас» сценария (sim_now): по нему идут все расчёты — прогноз, рейсы, задержки.
# 12 ноя 14:00 МСК = 11:00 UTC. Метки событий (event_ts) = DEMO_NOW + время с последнего reset.
DEMO_NOW = os.getenv("DEMO_NOW", "2026-11-12T11:00:00Z")
