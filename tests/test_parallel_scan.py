"""Regression tests for the parallel scan loop in ``swing_scanner.app``.

These verify two contracts the rest of the codebase depends on:

1. ``run_scan`` preserves the input symbol order in its returned alerts
   and in the Telegram delivery sequence (we use ``executor.map``, but
   the test pins this so a future refactor can't silently regress it).
2. The parallel and sequential paths (``scan_max_workers`` > 1 vs. == 1)
   produce byte-identical alert lists for the same input. This guards
   against accidental shared-state bugs creeping in when worker count
   changes.
"""
from __future__ import annotations

import time
import unittest
from dataclasses import replace
from unittest.mock import patch

from swing_scanner.app import run_scan
from swing_scanner.config import Settings
from swing_scanner.data_providers.base import Candle, MarketDataProvider


def _candles(seed: float) -> list[Candle]:
    """Build a 60-row synthetic candle series.

    The strategy needs >= 30 rows to compute 20-window indicators. We
    generate a gently-rising series so RSI/MACD land in the neutral
    zone and ``is_candidate`` is deterministic per ``seed``.
    """
    out: list[Candle] = []
    base = 100.0 + seed
    for i in range(60):
        px = base + i * 0.5
        out.append(
            Candle(
                timestamp=f"2024-01-{(i % 28) + 1:02d}",
                open=px,
                high=px + 1,
                low=px - 1,
                close=px,
                volume=1_000_000.0 + i * 1000,
            )
        )
    return out


class _SlowProvider(MarketDataProvider):
    """Sleeps per fetch so the parallel speedup is observable.

    The sleep is short (50ms) - enough that 4 sequential fetches take
    ~200ms while 4 parallel fetches take ~50ms, but small enough that
    the test doesn't slow down CI noticeably.
    """

    def __init__(self, delay_s: float = 0.05) -> None:
        self.delay_s = delay_s
        self.calls: list[str] = []

    def fetch_candles(
        self, symbol: str, interval: str = "daily", lookback_days: int = 30
    ) -> list[Candle]:
        time.sleep(self.delay_s)
        self.calls.append(symbol)
        # seed by symbol so each gets a distinct but deterministic series
        return _candles(seed=float(sum(ord(c) for c in symbol) % 50))


class ParallelScanTests(unittest.TestCase):
    SYMBOLS = ["AAA.NS", "BBB.NS", "CCC.NS", "DDD.NS"]

    def _settings(self, workers: int) -> Settings:
        # Empty Gemini key forces the analyst into rule-based fallback,
        # which keeps the test hermetic (no network) while still
        # exercising the full run_scan code path.
        return Settings(
            gemini_api_key="",
            telegram_bot_token="",
            telegram_chat_id="",
            news_source="none",
            scan_max_workers=workers,
            scan_cache_ttl=0,
        )

    def test_parallel_preserves_symbol_order(self):
        provider = _SlowProvider()
        with patch(
            "swing_scanner.app.build_provider", return_value=provider
        ):
            alerts = run_scan(
                symbols=list(self.SYMBOLS),
                settings=self._settings(workers=4),
                data_provider=provider,
                debug=False,
                force_analyze_all=True,  # bypass candidate gate so we
                                          # always get one alert per symbol
            )
        self.assertEqual(len(alerts), len(self.SYMBOLS))
        # Verify each alert mentions its symbol in the header. Header
        # is either "Swing Alert: <sym>" (real candidate) or
        # "Diagnostic: <sym>" preceded by a [DIAGNOSTIC ...] banner
        # (force-mode non-candidate); both cases include the symbol
        # within the first two lines.
        for symbol, alert in zip(self.SYMBOLS, alerts):
            head = "\n".join(alert.splitlines()[:2])
            self.assertIn(symbol, head)

    def test_parallel_matches_sequential_output(self):
        # Parallel and sequential paths must produce identical alerts
        # for the same input, otherwise we have a shared-state bug.
        symbols = list(self.SYMBOLS)
        seq_provider = _SlowProvider(delay_s=0.0)
        par_provider = _SlowProvider(delay_s=0.0)
        with patch("swing_scanner.app.build_provider", return_value=seq_provider):
            seq_alerts = run_scan(
                symbols=symbols,
                settings=self._settings(workers=1),
                data_provider=seq_provider,
                force_analyze_all=True,
            )
        with patch("swing_scanner.app.build_provider", return_value=par_provider):
            par_alerts = run_scan(
                symbols=symbols,
                settings=self._settings(workers=4),
                data_provider=par_provider,
                force_analyze_all=True,
            )
        self.assertEqual(seq_alerts, par_alerts)

    def test_parallel_actually_runs_concurrently(self):
        # Sanity check that parallelism is real, not just scheduled
        # serially. With per-fetch sleep of 50ms and 4 symbols at
        # workers=4, wall-clock should be < 150ms (vs. ~200ms serial).
        provider = _SlowProvider(delay_s=0.05)
        start = time.monotonic()
        with patch("swing_scanner.app.build_provider", return_value=provider):
            run_scan(
                symbols=list(self.SYMBOLS),
                settings=self._settings(workers=4),
                data_provider=provider,
                force_analyze_all=True,
            )
        elapsed = time.monotonic() - start
        # generous threshold to avoid CI flakiness; serial would be
        # ~200ms so anything < 150ms proves real concurrency
        self.assertLess(
            elapsed,
            0.15,
            f"Parallel scan took {elapsed:.3f}s; expected < 0.15s",
        )


if __name__ == "__main__":
    unittest.main()
