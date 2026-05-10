"""Yahoo Finance market data provider.

Wraps the ``yfinance`` library so the scanner can pull free OHLCV history
for both NSE equities (``RELIANCE.NS``, ``INFY.NS``) and US equities
(``AAPL``, ``MSFT``). Output is normalized into the shared :class:`Candle`
dataclass so the analysis, AI, scheduler, and Telegram layers stay
vendor-agnostic.

No API key is required.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from swing_scanner.data_providers.base import Candle, MarketDataProvider

try:  # pragma: no cover - import guard
    import yfinance as yf  # type: ignore
except ImportError:  # pragma: no cover
    yf = None  # type: ignore


# Friendly interval aliases -> yfinance ``interval`` strings.
_INTERVAL_ALIASES: dict[str, str] = {
    "daily": "1d",
    "day": "1d",
    "d": "1d",
    "1d": "1d",
    "weekly": "1wk",
    "w": "1wk",
    "1w": "1wk",
    "1wk": "1wk",
    "monthly": "1mo",
    "m": "1mo",
    "1mo": "1mo",
    "1": "1m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "60m",
    "1h": "60m",
}

# yfinance restricts intraday history depth; map our daily-lookback hint
# to a sensible ``period`` when the caller asks for intraday bars.
_INTRADAY_INTERVALS = {"1m", "5m", "15m", "30m", "60m"}


class YFinanceProvider(MarketDataProvider):
    """Market data provider backed by Yahoo Finance via ``yfinance``."""

    def __init__(self, session: Optional[Any] = None) -> None:
        # ``session`` lets tests inject a fake; production passes nothing
        # and yfinance manages its own HTTP client.
        self._session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_candles(
        self,
        symbol: str,
        interval: str = "daily",
        lookback_days: int = 30,
    ) -> list[Candle]:
        if yf is None:
            print(
                f"yfinance fetch skipped for {symbol}: 'yfinance' package not installed."
            )
            return []

        yf_symbol = symbol.strip()
        if not yf_symbol:
            print("yfinance fetch skipped: empty symbol.")
            return []

        yf_interval = _INTERVAL_ALIASES.get(interval.strip().lower(), "1d")
        period = self._compute_period(yf_interval, lookback_days)

        try:
            ticker = yf.Ticker(yf_symbol, session=self._session) if self._session else yf.Ticker(yf_symbol)
            df = ticker.history(
                period=period,
                interval=yf_interval,
                auto_adjust=False,
                actions=False,
            )
        except Exception as exc:  # network/library failures
            print(f"yfinance error for {symbol}: {exc}")
            return []

        if df is None or getattr(df, "empty", True):
            print(
                f"yfinance returned no data for {symbol} "
                f"(interval={yf_interval}, period={period}). "
                "Check the symbol (NSE tickers need a '.NS' suffix) or lookback."
            )
            return []

        return self._normalize(df, symbol)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_period(yf_interval: str, lookback_days: int) -> str:
        """Choose a yfinance ``period`` that covers ``lookback_days``.

        yfinance caps intraday history (~60d for 1m/5m/15m/30m/60m) so we
        clamp accordingly; daily/weekly/monthly use a ``Nd`` window.
        """
        days = max(int(lookback_days), 1)
        if yf_interval in _INTRADAY_INTERVALS:
            days = min(days, 60)
            return f"{days}d"
        # Pad daily window so weekends/holidays still leave enough bars.
        return f"{max(days, 5)}d"

    def _normalize(self, df: Any, symbol: str) -> list[Candle]:
        try:
            required = ("Open", "High", "Low", "Close", "Volume")
            if not all(col in df.columns for col in required):
                print(
                    f"yfinance malformed frame for {symbol}: missing OHLCV columns "
                    f"(got {list(df.columns)})."
                )
                return []

            candles: list[Candle] = []
            for ts, row in df.iterrows():
                try:
                    close = float(row["Close"])
                except (TypeError, ValueError):
                    continue
                # yfinance occasionally yields NaN rows on holidays; skip them.
                if close != close:  # NaN check without importing math
                    continue

                candles.append(
                    Candle(
                        timestamp=_format_timestamp(ts),
                        open=_safe_float(row.get("Open")),
                        high=_safe_float(row.get("High")),
                        low=_safe_float(row.get("Low")),
                        close=close,
                        volume=_safe_float(row.get("Volume")),
                    )
                )
            return candles
        except Exception as exc:  # pragma: no cover - defensive
            print(f"yfinance normalize error for {symbol}: {exc}")
            return []


def _safe_float(value: Any) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if f != f:  # NaN
        return 0.0
    return f


def _format_timestamp(value: Any) -> str:
    """yfinance returns pandas Timestamps; render as ISO for human logs."""
    try:
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        # pandas.Timestamp implements .strftime / .to_pydatetime
        if hasattr(value, "to_pydatetime"):
            return value.to_pydatetime().strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M:%S")
    except (AttributeError, ValueError, OSError):
        pass
    return str(value)
