"""Abstract market data provider contract.

Any concrete provider (Dhan, mock, future brokers) implements
:meth:`MarketDataProvider.fetch_candles` and returns a list of
:class:`Candle` objects. Keeping this layer minimal lets the analysis
pipeline stay agnostic of vendor SDKs.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Candle:
    """Normalized OHLCV candle used across the analysis pipeline."""

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataProvider(ABC):
    """Abstract base class for all market data providers."""

    @abstractmethod
    def fetch_candles(
        self,
        symbol: str,
        interval: str = "daily",
        lookback_days: int = 30,
    ) -> list[Candle]:
        """Return a list of :class:`Candle` for ``symbol``.

        Implementations must never raise on recoverable errors (missing
        credentials, expired tokens, network hiccups, empty responses) –
        instead they should log and return an empty list so the scan loop
        can continue to the next symbol.
        """
