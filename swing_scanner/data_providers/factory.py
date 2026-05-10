"""Provider factory.

Centralizes the ``MARKET_DATA_PROVIDER`` -> concrete provider mapping so
the rest of the app (``app.py``, scheduler, tests) only depends on the
:class:`MarketDataProvider` contract and never imports a specific vendor.

Defaults to ``yfinance`` because it is keyless and works for both NSE
(``RELIANCE.NS``) and US (``AAPL``) symbols out of the box.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from swing_scanner.data_providers.base import MarketDataProvider
from swing_scanner.data_providers.cache import CachedProvider
from swing_scanner.data_providers.dhan_provider import DhanProvider
from swing_scanner.data_providers.mock_provider import MockProvider
from swing_scanner.data_providers.yfinance_provider import YFinanceProvider

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from swing_scanner.config import Settings


SUPPORTED_PROVIDERS = ("yfinance", "dhan", "mock")
DEFAULT_PROVIDER = "yfinance"


def build_provider(settings: "Settings") -> MarketDataProvider:
    """Instantiate the provider selected by ``settings.market_data_provider``.

    Unknown values fall back to the default with a warning rather than
    crashing the scheduler — matches the rest of the codebase's
    "log-and-degrade" posture for recoverable config issues.
    """
    name = (settings.market_data_provider or DEFAULT_PROVIDER).strip().lower()

    if name not in SUPPORTED_PROVIDERS:
        print(
            f"Unknown MARKET_DATA_PROVIDER={name!r}; "
            f"falling back to {DEFAULT_PROVIDER!r}. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}."
        )
        name = DEFAULT_PROVIDER

    if name == "dhan":
        provider: MarketDataProvider = DhanProvider(
            client_id=settings.dhan_client_id,
            access_token=settings.dhan_access_token,
        )
    elif name == "mock":
        provider = MockProvider()
    else:  # yfinance / default
        provider = YFinanceProvider()

    # Wrap with the in-memory TTL cache when enabled. MockProvider is
    # deterministic and cheap, so caching it adds no value.
    ttl = getattr(settings, "scan_cache_ttl", 0) or 0
    if ttl > 0 and name != "mock":
        provider = CachedProvider(provider, ttl_seconds=ttl)
    return provider
