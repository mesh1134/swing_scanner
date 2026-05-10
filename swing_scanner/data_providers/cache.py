"""In-memory TTL cache wrapper for any :class:`MarketDataProvider`.

Wraps a concrete provider so repeated ``fetch_candles`` calls within the
TTL window reuse the previous response instead of re-hitting the vendor
API. This is intentionally lightweight (process-local, no disk) — it
exists to absorb duplicate fetches inside a single scan and across
back-to-back scans, not to be a durable store.
"""
from __future__ import annotations

import time
from typing import Tuple

from swing_scanner.data_providers.base import Candle, MarketDataProvider


_CacheKey = Tuple[str, str, int]


class CachedProvider(MarketDataProvider):
    """Decorator that memoizes ``fetch_candles`` results for ``ttl_seconds``."""

    def __init__(self, inner: MarketDataProvider, ttl_seconds: float = 600.0) -> None:
        self._inner = inner
        self._ttl = max(float(ttl_seconds), 0.0)
        self._store: dict[_CacheKey, tuple[float, list[Candle]]] = {}

    @property
    def inner(self) -> MarketDataProvider:
        """Expose the wrapped provider (useful for debug/logging)."""
        return self._inner

    def fetch_candles(
        self,
        symbol: str,
        interval: str = "daily",
        lookback_days: int = 30,
    ) -> list[Candle]:
        if self._ttl <= 0:
            return self._inner.fetch_candles(symbol, interval, lookback_days)

        key: _CacheKey = (symbol.strip().upper(), interval.strip().lower(), int(lookback_days))
        now = time.monotonic()
        hit = self._store.get(key)
        if hit is not None:
            ts, candles = hit
            if now - ts <= self._ttl and candles:
                return candles

        candles = self._inner.fetch_candles(symbol, interval, lookback_days)
        # Only cache non-empty responses; empty results usually indicate a
        # transient error and should be retried on the next call.
        if candles:
            self._store[key] = (now, candles)
        return candles

    def clear(self) -> None:
        self._store.clear()
