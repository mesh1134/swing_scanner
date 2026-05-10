"""Strategy registry / factory.

Centralizes the ``SCAN_STRATEGY`` -> concrete :class:`Strategy` mapping
so the rest of the app never imports a specific strategy module.
"""
from __future__ import annotations

from swing_scanner.strategies.base import Strategy
from swing_scanner.strategies.swing_strategy import SwingStrategy


SUPPORTED_STRATEGIES = ("swing",)
DEFAULT_STRATEGY = "swing"


def build_strategy(name: str | None) -> Strategy:
    """Return the :class:`Strategy` matching ``name``.

    Unknown values log and fall back to the default — matches the
    "log-and-degrade" posture used by the provider factory.
    """
    key = (name or DEFAULT_STRATEGY).strip().lower()
    if key not in SUPPORTED_STRATEGIES:
        print(
            f"Unknown SCAN_STRATEGY={key!r}; falling back to {DEFAULT_STRATEGY!r}. "
            f"Supported: {', '.join(SUPPORTED_STRATEGIES)}."
        )
        key = DEFAULT_STRATEGY

    if key == "swing":
        return SwingStrategy()
    # Unreachable while the supported set has only one entry; kept for
    # clarity once additional strategies land.
    return SwingStrategy()
