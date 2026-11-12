import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
    backend_url: str = os.getenv("BACKEND_URL", "").rstrip("/")
    backend_token: str = os.getenv("BACKEND_TOKEN", "")
    system_prompt: str = os.getenv(
        "SYSTEM_PROMPT", "Ты — дружелюбный ассистент проекта. Отвечай кратко и по делу, на русском."
    )
    admin_ids: set[int] = field(
        default_factory=lambda: {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
    )


settings = Settings()
