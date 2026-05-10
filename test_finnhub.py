"""Standalone smoke test for the Finnhub market data provider.

Run this directly (``python test_finnhub.py``) to verify the
``FINNHUB_API_KEY`` and basic connectivity without touching the
scheduler, AI, or Telegram delivery paths. Prints the latest candles for
INFY (NSE equity) in a human-readable table.

Usage:
    python test_finnhub.py [SYMBOL]

The default symbol is INFY. Credentials are read from ``.env`` via
``python-dotenv`` (falling back to the process environment).
"""
from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from swing_scanner.data_providers import FinnhubProvider


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "INFY"

    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key:
        print("ERROR: FINNHUB_API_KEY must be set in .env or the environment.")
        return 1

    print(f"Fetching daily candles for {symbol} via Finnhub (lookback=30d)...")
    provider = FinnhubProvider(api_key=api_key)

    try:
        candles = provider.fetch_candles(
            symbol=symbol, interval="daily", lookback_days=30
        )
    except Exception as exc:
        print(f"Unexpected error calling FinnhubProvider: {exc}")
        return 2

    if not candles:
        print(
            "No candles returned. Possible causes: invalid API key, plan "
            "does not cover this exchange, rate limit, market closed, or "
            "unknown symbol mapping. Check the log lines above for the "
            "specific reason."
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
