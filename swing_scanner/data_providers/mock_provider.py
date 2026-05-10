"""Deterministic mock provider for tests and offline development."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from swing_scanner.data_providers.base import Candle, MarketDataProvider


class MockProvider(MarketDataProvider):
    """Generates a synthetic, deterministic OHLCV series.

    Useful for unit tests, CI, and running the scanner without live
    credentials. Produces ``lookback_days`` daily candles with a mild
    upward drift plus sinusoidal oscillation so indicators have signal.
    """

    def fetch_candles(
        self,
        symbol: str,
        interval: str = "daily",
        lookback_days: int = 60,
    ) -> list[Candle]:
        base = 1000.0 + (sum(ord(c) for c in symbol) % 500)
        now = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)
        candles: list[Candle] = []
        for i in range(lookback_days):
            ts = now - timedelta(days=lookback_days - 1 - i)
            drift = i * 0.4
            wave = math.sin(i / 3.0) * 8.0
            close = base + drift + wave
            open_ = close - 1.5
            high = close + 3.0
            low = close - 3.0
            volume = 500_000 + (i * 1_000)
            candles.append(
                Candle(
                    timestamp=ts.strftime("%Y-%m-%d %H:%M:%S"),
                    open=round(open_, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=float(volume),
                )
            )
        return candles
