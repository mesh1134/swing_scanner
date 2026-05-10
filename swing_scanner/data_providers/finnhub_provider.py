"""Finnhub market data provider.

Fetches OHLCV candles from the Finnhub REST API
(https://finnhub.io/docs/api/stock-candles) and normalizes them into the
shared :class:`Candle` dataclass so the analysis, AI, scheduler, and
Telegram layers can stay vendor-agnostic.

Credentials are read from the ``FINNHUB_API_KEY`` environment variable by
default but can be injected explicitly for tests.

NSE equities are addressed using Finnhub's ``<TICKER>.NS`` convention
(e.g. ``RELIANCE.NS``, ``INFY.NS``). Callers may pass either the bare NSE
ticker (``RELIANCE``) or the fully-qualified Finnhub symbol; both work.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from swing_scanner.data_providers.base import Candle, MarketDataProvider

try:  # pragma: no cover - import guard
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# Resolutions accepted by Finnhub's /stock/candle endpoint.
_VALID_RESOLUTIONS = {"1", "5", "15", "30", "60", "D", "W", "M"}


class FinnhubAuthError(RuntimeError):
    """Raised internally when the API key is missing."""


class FinnhubProvider(MarketDataProvider):
    """Market data provider backed by the Finnhub REST API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = FINNHUB_BASE_URL,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_candles(
        self,
        symbol: str,
        interval: str = "daily",
        lookback_days: int = 30,
    ) -> list[Candle]:
        """Fetch OHLCV candles for ``symbol``.

        ``interval`` accepts the same friendly aliases used elsewhere in
        the codebase (``"daily"``, ``"1d"``, ``"15"``, ``"60"``, ...) and
        is mapped to the Finnhub ``resolution`` parameter. Returns an
        empty list on any recoverable error.
        """
        if not self.api_key:
            print(
                f"Finnhub fetch skipped for {symbol}: FINNHUB_API_KEY not set."
            )
            return []
        if requests is None:
            print(
                f"Finnhub fetch skipped for {symbol}: 'requests' package not installed."
            )
            return []

        resolution = self._map_interval(interval)
        finnhub_symbol = self._resolve_symbol(symbol)
        now = int(datetime.now(tz=timezone.utc).timestamp())
        # Pad the window slightly so weekends/holidays still yield enough bars.
        from_ts = now - max(int(lookback_days), 1) * 86_400

        params = {
            "symbol": finnhub_symbol,
            "resolution": resolution,
            "from": from_ts,
            "to": now,
            "token": self.api_key,
        }

        try:
            resp = requests.get(
                f"{self.base_url}/stock/candle",
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            print(f"Finnhub network error for {symbol}: {exc}")
            return []

        if resp.status_code == 401 or resp.status_code == 403:
            print(
                f"Finnhub auth error for {symbol}: invalid or unauthorized API key "
                f"(HTTP {resp.status_code})."
            )
            return []
        if resp.status_code == 429:
            print(f"Finnhub rate limit hit for {symbol} (HTTP 429); skipping.")
            return []
        if resp.status_code >= 400:
            print(
                f"Finnhub HTTP {resp.status_code} for {symbol}: "
                f"{resp.text[:200]}"
            )
            return []

        try:
            payload = resp.json()
        except ValueError as exc:
            print(f"Finnhub returned non-JSON response for {symbol}: {exc}")
            return []

        return self._normalize(payload, symbol)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _map_interval(interval: str) -> str:
        if not interval:
            return "D"
        key = interval.strip().lower()
        if key in ("daily", "day", "d", "1d"):
            return "D"
        if key in ("weekly", "w", "1w"):
            return "W"
        if key in ("monthly", "m", "1mo"):
            return "M"
        # Bare minute counts: "1", "5", "15", "30", "60".
        if key.isdigit() and key in _VALID_RESOLUTIONS:
            return key
        # Fallback to daily for anything we don't recognise.
        return "D"

    @staticmethod
    def _resolve_symbol(symbol: str) -> str:
        """Map a friendly ticker to Finnhub's symbol convention.

        - ``"RELIANCE"`` -> ``"RELIANCE.NS"``
        - ``"RELIANCE.NS"`` -> unchanged
        - ``"NSE:RELIANCE"`` -> unchanged (already exchange-qualified)
        - US tickers like ``"AAPL"`` keep working because they have no dot
          and become ``"AAPL.NS"`` only if the caller wants NSE; to opt
          out, callers should pass the symbol explicitly with a dot or
          colon already present.
        """
        s = symbol.strip().upper()
        if not s:
            return s
        if "." in s or ":" in s:
            return s
        return f"{s}.NS"

    def _normalize(self, payload: Any, symbol: str) -> list[Candle]:
        if not isinstance(payload, dict):
            print(f"Finnhub malformed response for {symbol}: not a JSON object.")
            return []

        status = str(payload.get("s", "")).lower()
        if status == "no_data":
            return []
        if status and status != "ok":
            err = payload.get("error") or payload.get("message") or status
            print(f"Finnhub non-ok response for {symbol}: {err}")
            return []

        opens = payload.get("o") or []
        highs = payload.get("h") or []
        lows = payload.get("l") or []
        closes = payload.get("c") or []
        volumes = payload.get("v") or []
        timestamps = payload.get("t") or []

        if not isinstance(closes, list) or not closes:
            return []

        candles: list[Candle] = []
        for i in range(len(closes)):
            ts_raw = timestamps[i] if i < len(timestamps) else 0
            try:
                candles.append(
                    Candle(
                        timestamp=_format_timestamp(ts_raw),
                        open=float(opens[i]) if i < len(opens) else 0.0,
                        high=float(highs[i]) if i < len(highs) else 0.0,
                        low=float(lows[i]) if i < len(lows) else 0.0,
                        close=float(closes[i]),
                        volume=float(volumes[i]) if i < len(volumes) else 0.0,
                    )
                )
            except (TypeError, ValueError) as exc:
                print(f"Finnhub skipped malformed candle for {symbol} at idx {i}: {exc}")
                continue
        return candles


def _format_timestamp(value: Any) -> str:
    """Finnhub returns epoch seconds; render as ISO for human-readable logs."""
    try:
        if isinstance(value, (int, float)) and value > 0:
            return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        pass
    return str(value)
