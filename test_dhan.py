"""Standalone smoke test for the DhanHQ market data provider.

Run this directly (``python test_dhan.py``) to verify credentials and
basic connectivity without touching the scheduler, AI, or Telegram
delivery paths. Prints the latest candles for RELIANCE (NSE equity) in a
human-readable table.

Usage:
    python test_dhan.py [SYMBOL]

The default symbol is RELIANCE. Credentials are read from ``.env`` via
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

from swing_scanner.data_providers import DhanProvider


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"

    client_id = os.getenv("DHAN_CLIENT_ID", "")
    access_token = os.getenv("DHAN_ACCESS_TOKEN", "")
    if not (client_id and access_token):
        print("ERROR: DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN must be set in .env")
        return 1

    print(f"Fetching daily candles for {symbol} (lookback=30d)...")
    provider = DhanProvider(client_id=client_id, access_token=access_token)

    try:
        candles = provider.fetch_candles(
            symbol=symbol, interval="daily", lookback_days=30
        )
    except Exception as exc:
        print(f"Unexpected error calling DhanProvider: {exc}")
        return 2

    if not candles:
        print(
            "No candles returned. Possible causes: expired access token, "
            "unknown symbol mapping, market closed, or API rate limit. "
            "Check the log lines above for the specific reason."
        )
        return 3

    print(f"Received {len(candles)} candles. Showing last 5:\n")
    header = f"{'timestamp':<22} {'open':>10} {'high':>10} {'low':>10} {'close':>10} {'volume':>14}"
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
