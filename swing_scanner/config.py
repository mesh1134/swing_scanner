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

    # Gemini model used by the analyst layer AND by the Gemini news
    # client (when news_source=gemini). 2.5-flash is the current best
    # flash-tier model - strong instruction following with grounding
    # support, comfortably inside free-tier limits for this workload.
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # News source: gemini (default, uses Google Search grounding via
    # the existing Gemini key - no extra vendor), perplexity (requires
    # Perplexity API credits), or none (skip the news layer entirely).
    news_source: str = os.getenv("NEWS_SOURCE", "gemini")

    # Selects which Strategy implementation analyzes each symbol.
    # See swing_scanner.strategies.registry for supported values.
    scan_strategy: str = os.getenv("SCAN_STRATEGY", "swing")

    # TTL (seconds) for the in-memory candle cache wrapping the provider.
    # 0 disables caching. Defaults to 600s (10 min) - enough to absorb
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

    # Max worker threads for the per-symbol scan loop. Each symbol does
    # a candle fetch + (optionally) a Gemini news call + a Gemini analyst
    # call - all I/O bound, so threads cut wall-clock dramatically. Set
    # to 1 to force fully sequential execution. Defaults to 8 (enough
    # parallelism for typical 16-symbol watchlists without overwhelming
    # the Gemini free-tier RPM cap).
    scan_max_workers: int = max(1, int(os.getenv("SCAN_MAX_WORKERS", "8") or 8))

    # Path to the SQLite database for persistence. If empty, persistence
    # is disabled. Defaults to "scanner.db" in the working directory.
    scan_db_path: str = os.getenv("SCAN_DB_PATH", "scanner.db")

    perplexity_api_key: str = os.getenv("PERPLEXITY_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
