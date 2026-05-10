import os
from dataclasses import dataclass

# Load .env lazily so Settings() picks up credentials even when the app
# isn't started via a process manager that pre-populates the environment.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - python-dotenv is optional at runtime
    pass


@dataclass(frozen=True)
class Settings:
    # Selects which MarketDataProvider implementation the scanner uses.
    # See swing_scanner.data_providers.factory for supported values.
    # Defaults to "yfinance" because it is keyless and covers NSE + US.
    market_data_provider: str = os.getenv("MARKET_DATA_PROVIDER", "yfinance")

    # DhanHQ credentials (only required when MARKET_DATA_PROVIDER=dhan).
    dhan_client_id: str = os.getenv("DHAN_CLIENT_ID", "")
    dhan_access_token: str = os.getenv("DHAN_ACCESS_TOKEN", "")
    # Finnhub key (only required when MARKET_DATA_PROVIDER=finnhub).
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")

    # TTL (seconds) for the in-memory candle cache wrapping the provider.
    # 0 disables caching. Defaults to 600s (10 min) — enough to absorb
    # duplicate fetches across back-to-back scans without serving stale
    # data into a swing-trade decision.
    scan_cache_ttl: int = int(os.getenv("SCAN_CACHE_TTL", "600") or 0)

    # When true, run_scan prints per-symbol indicator state for every scan.
    # Accepts: 1, true, yes, on (case-insensitive). Defaults to false.
    scan_debug: bool = os.getenv("SCAN_DEBUG", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    perplexity_api_key: str = os.getenv("PERPLEXITY_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
