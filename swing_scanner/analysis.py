"""Backward-compatible facade over :mod:`swing_scanner.strategies`.

The original analysis logic now lives in
:class:`swing_scanner.strategies.swing_strategy.SwingStrategy`. This
module re-exports :class:`SetupSignal` and exposes ``analyze_symbol`` so
existing imports (``from swing_scanner.analysis import analyze_symbol,
SetupSignal``) keep working unchanged.
"""
from __future__ import annotations

from swing_scanner.data_providers import Candle
from swing_scanner.strategies import SetupSignal, SwingStrategy

__all__ = ["SetupSignal", "analyze_symbol"]

# Module-level instance keeps the function-level call site cheap and
# matches the prior behavior (no per-call construction cost).
_DEFAULT_STRATEGY = SwingStrategy()


def analyze_symbol(symbol: str, candles: list[Candle]) -> SetupSignal | None:
    """Run the default swing strategy. Preserved for legacy imports.

    New code should call ``Strategy.analyze`` via
    :func:`swing_scanner.strategies.build_strategy` instead.
    """
    return _DEFAULT_STRATEGY.analyze(symbol=symbol, candles=candles)
