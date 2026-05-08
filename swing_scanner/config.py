import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    angel_one_api_key: str = os.getenv("ANGEL_ONE_API_KEY", "")
    angel_one_client_id: str = os.getenv("ANGEL_ONE_CLIENT_ID", "")
    angel_one_mpin: str = os.getenv("ANGEL_ONE_MPIN", "")
    angel_one_totp_secret: str = os.getenv("ANGEL_ONE_TOTP_SECRET", "")
    perplexity_api_key: str = os.getenv("PERPLEXITY_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
