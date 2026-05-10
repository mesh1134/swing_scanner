"""Standalone smoke test for the Yahoo Finance market data provider.

Run this directly (``python test_yfinance.py``) to verify ``yfinance``
connectivity without touching the scheduler, AI, or Telegram delivery
paths. Prints the latest candles for RELIANCE.NS in a human-readable
table.

Usage:
    python test_yfinance.py [SYMBOL]

Default symbol is ``RELIANCE.NS``. NSE tickers need the ``.NS`` suffix;
US tickers can be passed bare (``AAPL``, ``MSFT``). No API key required.
"""
from __future__ import annotations

import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from swing_scanner.data_providers import YFinanceProvider


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE.NS"

    print(f"Fetching daily candles for {symbol} via yfinance (lookback=30d)...")
    provider = YFinanceProvider()

    try:
        candles = provider.fetch_candles(
            symbol=symbol, interval="daily", lookback_days=30
        )
    except Exception as exc:
        print(f"Unexpected error calling YFinanceProvider: {exc}")
        return 2

    if not candles:
        print(
            "No candles returned. Possible causes: invalid ticker, missing "
            "'.NS' suffix for NSE symbols, network issue, or yfinance not "
            "installed. Check the log lines above for the specific reason."
        )
        return 3

    print(f"Received {len(candles)} candles. Showing last 5:\n")
    header = (
        f"{'timestamp':<22} {'open':>10} {'high':>10} "
        f"{'low':>10} {'close':>10} {'volume':>14}"
    )
    print(header)
    print("-" * len(header))
    for c in candles[-5:]:
        print(
            f"{c.timestamp:<22} {c.open:>10.2f} {c.high:>10.2f} "
            f"{c.low:>10.2f} {c.close:>10.2f} {c.volume:>14.0f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
