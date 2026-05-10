"""Strategy abstraction.

Each :class:`Strategy` consumes a list of :class:`Candle` and returns a
:class:`SetupSignal` (or ``None`` if there is nothing actionable). This
decouples ``app.py`` from any specific candidate-selection logic so we
can plug in additional strategies (mean-reversion, breakout, etc.)
without touching the scan loop, provider system, AI layer, or delivery.

``SetupSignal`` lives here (rather than in ``analysis.py``) so strategy
modules can import it without depending on the legacy facade. The
existing ``swing_scanner.analysis`` module re-exports it for backward
compatibility.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from swing_scanner.data_providers import Candle


@dataclass
class SetupSignal:
    """Indicator snapshot for the most recent candle of ``symbol``.

    Field set is unchanged from the pre-refactor ``analysis.SetupSignal``
    so downstream consumers (``ai_brain``, ``delivery``, debug logging)
    keep working without edits.
    """

    symbol: str
    rsi: float
    macd: float
    ema_20: float
    bb_upper: float
    bb_lower: float
    close: float
    volume: float
    is_candidate: bool
    # 20-bar rolling average volume (defaults to 0.0 for backward compat
    # with any callers that build SetupSignal without it).
    avg_volume: float = 0.0


class Strategy(ABC):
    """Base class for candidate-selection strategies."""

    #: Human-readable identifier used by the registry / debug logs.
    strategy_name: str = "base"

    @abstractmethod
    def analyze(self, symbol: str, candles: list[Candle]) -> SetupSignal | None:
        """Return a :class:`SetupSignal` for ``symbol`` or ``None``.

        Implementations must never raise on insufficient data; instead
        they should return ``None`` so the scan loop can continue to the
        next symbol.
        """
