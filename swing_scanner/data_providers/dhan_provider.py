"""DhanHQ market data provider.

Wraps the official ``dhanhq`` SDK so the rest of the codebase can stay on
the :class:`MarketDataProvider` contract. Credentials are read from the
environment (``DHAN_CLIENT_ID`` / ``DHAN_ACCESS_TOKEN``) by default but
can be injected explicitly for testing.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Optional

from swing_scanner.data_providers.base import Candle, MarketDataProvider

# Import SDK defensively so the package still loads in environments where
# dhanhq is not installed yet (CI, docs builds, tooling).
try:  # pragma: no cover - import guard
    from dhanhq import dhanhq  # type: ignore
except ImportError:  # pragma: no cover
    dhanhq = None  # type: ignore

try:  # pragma: no cover - newer SDK versions expose a context object
    from dhanhq import DhanContext  # type: ignore
except ImportError:  # pragma: no cover
    DhanContext = None  # type: ignore


# Minimal symbol -> NSE security id map for common large caps. Dhan's
# historical endpoints require the numeric security id rather than the
# ticker. Callers can also pass a numeric security id directly as
# ``symbol`` and we'll use it verbatim.
NSE_EQUITY_SECURITY_IDS: dict[str, str] = {
    "RELIANCE": "2885",
    "INFY": "1594",
    "TCS": "11536",
    "HDFCBANK": "1333",
    "ICICIBANK": "4963",
    "SBIN": "3045",
    "ITC": "1660",
    "LT": "11483",
    "AXISBANK": "5900",
    "KOTAKBANK": "1922",
    "HINDUNILVR": "1394",
    "BHARTIARTL": "10604",
    "WIPRO": "3787",
    "MARUTI": "10999",
    "ASIANPAINT": "236",
}


class DhanAuthError(RuntimeError):
    """Raised internally when credentials are missing or token expired."""


class DhanProvider(MarketDataProvider):
    """Market data provider backed by the DhanHQ SDK."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> None:
        self.client_id = client_id or os.getenv("DHAN_CLIENT_ID", "")
        self.access_token = access_token or os.getenv("DHAN_ACCESS_TOKEN", "")
        self._client: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_candles(
        self,
        symbol: str,
        interval: str = "daily",
        lookback_days: int = 30,
    ) -> list[Candle]:
        """Fetch OHLCV candles for an NSE equity symbol.

        ``interval`` currently supports ``"daily"`` (historical daily) and
        any integer-minute string like ``"1"``, ``"5"``, ``"15"`` for
        intraday. Returns an empty list on any recoverable error.
        """
        try:
            client = self._get_client()
        except DhanAuthError as exc:
            print(f"Dhan fetch skipped for {symbol}: {exc}")
            return []

        security_id = self._resolve_security_id(symbol)
        if not security_id:
            print(f"Dhan fetch skipped: unknown NSE security id for {symbol!r}.")
            return []

        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=lookback_days)
        from_date = from_dt.strftime("%Y-%m-%d")
        to_date = to_dt.strftime("%Y-%m-%d")

        try:
            if interval.lower() in ("daily", "day", "1d", "d"):
                raw = client.historical_daily_data(
                    security_id=security_id,
                    exchange_segment="NSE_EQ",
                    instrument_type="EQUITY",
                    from_date=from_date,
                    to_date=to_date,
                    expiry_code=0,
                )
            else:
                minute_interval = int(interval) if interval.isdigit() else 15
                raw = client.intraday_minute_data(
                    security_id=security_id,
                    exchange_segment="NSE_EQ",
                    instrument_type="EQUITY",
                    from_date=from_date,
                    to_date=to_date,
                    interval=minute_interval,
                )
        except Exception as exc:  # network/SDK failures
            print(f"Dhan API error for {symbol}: {exc}")
            return []

        return self._normalize(raw, symbol)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not (self.client_id and self.access_token):
            raise DhanAuthError(
                "missing DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN in environment."
            )
        if dhanhq is None:
            raise DhanAuthError(
                "dhanhq SDK not installed (`pip install dhanhq`)."
            )
        # Prefer the newer DhanContext API when available, fall back to the
        # legacy two-argument constructor for older SDK releases.
        try:
            if DhanContext is not None:
                ctx = DhanContext(self.client_id, self.access_token)
                self._client = dhanhq(ctx)
            else:
                self._client = dhanhq(self.client_id, self.access_token)
        except Exception as exc:  # pragma: no cover - SDK init edge cases
            raise DhanAuthError(f"failed to initialize Dhan client: {exc}") from exc
        return self._client

    def _resolve_security_id(self, symbol: str) -> str:
        key = symbol.strip().upper()
        if key.isdigit():
            return key
        return NSE_EQUITY_SECURITY_IDS.get(key, "")

    def _normalize(self, raw: Any, symbol: str) -> list[Candle]:
        """Convert SDK response payload into ``Candle`` objects."""
        if not isinstance(raw, dict):
            return []
        status = str(raw.get("status", "")).lower()
        if status and status != "success":
            remarks = raw.get("remarks") or raw.get("error") or ""
            text = str(remarks).lower()
            if "token" in text or "unauth" in text or "expired" in text:
                print(f"Dhan auth issue for {symbol}: token may be expired ({remarks}).")
            else:
                print(f"Dhan non-success response for {symbol}: {remarks or raw}")
            return []

        data = raw.get("data") or {}
        opens = data.get("open") or []
        highs = data.get("high") or []
        lows = data.get("low") or []
        closes = data.get("close") or []
        volumes = data.get("volume") or []
        timestamps = data.get("timestamp") or data.get("start_Time") or []

        if not closes:
            return []

        candles: list[Candle] = []
        for i in range(len(closes)):
            ts_raw = timestamps[i] if i < len(timestamps) else ""
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
        return candles


def _format_timestamp(value: Any) -> str:
    """Dhan returns epoch seconds for timestamps; render as ISO for humans."""
    try:
        if isinstance(value, (int, float)) and value > 0:
            return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        pass
    return str(value)
