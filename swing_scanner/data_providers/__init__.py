"""Market data provider abstraction layer.

Exposes a common :class:`MarketDataProvider` interface so the rest of the
application (analysis, scheduler, AI, delivery) stays decoupled from whichever
broker/vendor supplies OHLCV candles.
"""

from swing_scanner.data_providers.base import Candle, MarketDataProvider
from swing_scanner.data_providers.cache import CachedProvider
from swing_scanner.data_providers.dhan_provider import DhanProvider
from swing_scanner.data_providers.factory import (
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
    build_provider,
)
from swing_scanner.data_providers.mock_provider import MockProvider
from swing_scanner.data_providers.yfinance_provider import YFinanceProvider

__all__ = [
    "Candle",
    "MarketDataProvider",
    "DhanProvider",
    "MockProvider",
    "YFinanceProvider",
    "CachedProvider",
    "build_provider",
    "SUPPORTED_PROVIDERS",
    "DEFAULT_PROVIDER",
]
