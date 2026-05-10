"""Watchlist file loader.

Reads a plain-text symbol list (one per line) so the scanner can scale
beyond a CLI-friendly handful of tickers. Supports ``#`` comments and
inline comments after the symbol.

Example ``watchlist.txt``::

    # NSE large caps (yfinance needs the .NS suffix)
    RELIANCE.NS
    INFY.NS         # comment after a symbol is allowed
    HDFCBANK.NS

    # US large caps
    AAPL
    MSFT
"""
from __future__ import annotations

from pathlib import Path


def load_watchlist(path: str | Path) -> list[str]:
    """Return the list of symbols defined in ``path``.

    Empty lines and ``#``-prefixed lines are ignored. Inline ``#``
    comments after a symbol are stripped. Order is preserved; duplicates
    are removed while keeping the first occurrence.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Watchlist file not found: {file_path}")

    seen: set[str] = set()
    symbols: list[str] = []
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line in seen:
            continue
        seen.add(line)
        symbols.append(line)
    return symbols
