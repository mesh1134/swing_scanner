from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    angel_one_api_key: str = os.getenv("ANGEL_ONE_API_KEY", "")
    angel_one_client_code: str = os.getenv("ANGEL_ONE_CLIENT_CODE", "")
    angel_one_access_token: str = os.getenv("ANGEL_ONE_ACCESS_TOKEN", "")
    perplexity_api_key: str = os.getenv("PERPLEXITY_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
