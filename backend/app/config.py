"""Настройки из backend/.env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
MOCK_DIR = DATA_DIR / "mock"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("API_KEY", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")

# Пропуска в моках подписаны этим публичным ключом, чтобы /passes/verify работал на моках.
# Настоящие пропуска подписываются JWT_SECRET из .env.
MOCK_JWT_SECRET = "caspian-mock-only-not-a-secret"
