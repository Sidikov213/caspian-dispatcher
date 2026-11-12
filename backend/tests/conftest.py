import os
import tempfile
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["BOT_TOKEN"] = ""      # тесты никогда не ходят в настоящий Telegram
os.environ["LLM_API_KEY"] = ""
os.environ["WEATHER_MODE"] = "synthetic"  # тесты не ходят в сеть
os.environ["DEMO_NOW"] = ""
os.environ["ACCOUNTS_PATH"] = os.path.join(tempfile.mkdtemp(prefix="caspian-accounts-"), "accounts.json")  # не data/
os.environ["DEVICES_PATH"] = os.path.join(tempfile.mkdtemp(prefix="caspian-devices-"), "devices.json")  # не data/
os.environ["FIREBASE_CREDENTIALS"] = ""   # тесты не шлют настоящие пуши
os.environ["PREDICTOR"] = "formula"      # старые тесты — на формуле; CatBoost проверяется явно (test_model.py)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app import main  # noqa: E402
from app.clock import FixedClock  # noqa: E402
from app.config import SCENARIO_ANCHOR as DEMO_NOW  # noqa: E402  12 ноя 14:00 МСК
from app.state import State  # noqa: E402

KEY = {"X-API-Key": main.API_KEY or "caspian-dev-key"}


@pytest.fixture
def st() -> State:
    """Отдельное состояние с полностью фиксированными часами."""
    return State(clock=FixedClock(DEMO_NOW))


@pytest.fixture
def client():
    main.state.clock = FixedClock(DEMO_NOW)
    main.state.users_path = None      # тесты не пишут data/users.json
    main.state.users.clear()
    main.state.reset()
    with TestClient(main.app, headers=KEY) as c:
        yield c
    main.state.reset()
