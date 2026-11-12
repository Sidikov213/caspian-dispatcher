"""Настройки бота из backend/.env (загружает app.config)."""
import os
from dataclasses import dataclass

from .. import config as _app_config  # noqa: F401  — load_dotenv(backend/.env)


@dataclass
class BotSettings:
    bot_token: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


def load() -> BotSettings:
    return BotSettings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "openai/gpt-4o-mini"),
    )
