"""Candidate-selection strategies.

See :mod:`swing_scanner.strategies.base` for the abstract contract and
:mod:`swing_scanner.strategies.registry` for runtime selection.
"""

from swing_scanner.strategies.base import SetupSignal, Strategy
from swing_scanner.strategies.registry import (
    DEFAULT_STRATEGY,
    SUPPORTED_STRATEGIES,
    build_strategy,
)
from swing_scanner.strategies.swing_strategy import SwingStrategy

__all__ = [
    "Strategy",
    "SetupSignal",
    "SwingStrategy",
    "build_strategy",
    "SUPPORTED_STRATEGIES",
    "DEFAULT_STRATEGY",
]
