"""Regression tests for the two polish fixes shipped 2026-05-10:

1. ``MIN_RISK_PCT`` floor raised from 1.5% to 2.0% in
   ``compute_trade_levels`` so swing stops aren't tighter than typical
   intra-day noise.
2. ``format_trade_idea(..., diagnostic=True)`` prepends a clear banner
   and switches the header from "Swing Alert" to "Diagnostic" so
   force-analyze non-candidate output cannot be mistaken for a real
   trade signal.
"""
from __future__ import annotations

import unittest

from swing_scanner.ai_brain import (
    MIN_RISK_PCT,
    GeminiIdeaGenerator,
    compute_trade_levels,
)
from swing_scanner.delivery import format_trade_idea
from swing_scanner.strategies.base import SetupSignal


def _signal_with_tight_stops() -> SetupSignal:
    """Construct a setup where every candidate stop sits within 1% of entry.

    With both ``ema_stop`` (1% below EMA20) and ``bb_stop`` (BB lower)
    above the 2% floor cutoff, ``compute_trade_levels`` should fall back
    to the floor. This pins the contract: the floor is enforced, and
    its value matches ``MIN_RISK_PCT``.
    """
    return SetupSignal(
        symbol="TEST",
        rsi=55.0,
        macd=0.1,
        ema_20=999.5,       # ema_stop = 989.5 -> 1.0% below entry, inside floor
        bb_upper=1020.0,
        bb_lower=995.0,     # bb_stop = 995.0 -> 0.5% below entry, inside floor
        close=1000.0,
        volume=1_000_000.0,
        avg_volume=1_000_000.0,
        is_candidate=True,
    )


class StopFloorTests(unittest.TestCase):
    def test_floor_is_two_percent(self):
        # Pin the constant itself so a future bump to e.g. 2.5% requires
        # an explicit test update rather than silently changing risk
        # math for live trades.
        self.assertAlmostEqual(MIN_RISK_PCT, 0.02, places=4)

    def test_tight_setup_clamps_to_floor(self):
        signal = _signal_with_tight_stops()
        entry, target, stop, rr = compute_trade_levels(signal)
        risk_pct = (entry - stop) / entry
        # Stop must equal exactly the 2% floor on this setup.
        self.assertAlmostEqual(risk_pct, MIN_RISK_PCT, places=4)
        # Target uses the 1.8 R-multiple on the floored risk.
        self.assertAlmostEqual(target, entry + (entry - stop) * 1.8, places=2)
        self.assertAlmostEqual(rr, 1.8, places=2)

    def test_wide_setup_uses_natural_stop_not_floor(self):
        # A setup where bb_lower sits 3% below entry should produce a
        # 3% stop, NOT the 2% floor. The floor only kicks in when the
        # tightest natural stop is below it.
        signal = SetupSignal(
            symbol="TEST",
            rsi=55.0,
            macd=0.1,
            ema_20=970.0,   # ema_stop = 960.3 -> 3.97% below entry
            bb_upper=1020.0,
            bb_lower=970.0, # bb_stop = 970.0 -> 3.00% below entry (tightest valid)
            close=1000.0,
            volume=1_000_000.0,
            avg_volume=1_000_000.0,
            is_candidate=True,
        )
        entry, _target, stop, _rr = compute_trade_levels(signal)
        risk_pct = (entry - stop) / entry
        # Should land near 3% (bb_stop), not 2% (floor) and not 4% (cap).
        self.assertAlmostEqual(risk_pct, 0.03, places=2)


class DiagnosticFormatTests(unittest.TestCase):
    def _analysis(self):
        signal = SetupSignal(
            symbol="INFY",
            rsi=38.0,
            macd=-2.0,
            ema_20=1212.0,
            bb_upper=1355.0,
            bb_lower=1095.0,
            close=1179.0,
            volume=7_000_000.0,
            avg_volume=13_000_000.0,
            is_candidate=False,
        )
        # rule-based path keeps the test hermetic (no Gemini call)
        return GeminiIdeaGenerator(api_key="").build_trade_idea(signal, "")

    def test_default_format_is_swing_alert(self):
        text = format_trade_idea(self._analysis())
        self.assertTrue(
            text.startswith("Swing Alert: INFY"),
            f"Expected 'Swing Alert' header, got: {text.splitlines()[0]!r}",
        )
        self.assertNotIn("DIAGNOSTIC", text)

    def test_diagnostic_format_has_banner_and_label(self):
        text = format_trade_idea(self._analysis(), diagnostic=True)
        first_line = text.splitlines()[0]
        # Banner is the very first line so it stands out in any reader.
        self.assertIn("DIAGNOSTIC", first_line)
        self.assertIn("non-candidate", first_line)
        # Header line is replaced with "Diagnostic:" so the message
        # cannot be mistaken for "Swing Alert" when copy-pasted.
        self.assertIn("Diagnostic: INFY", text)
        self.assertNotIn("Swing Alert: INFY", text)
        # The trade-level line still renders so the diagnostic remains
        # useful for inspection - just clearly labelled.
        self.assertIn("Entry:", text)
        self.assertIn("Stop:", text)


if __name__ == "__main__":
    unittest.main()
