from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator

from swing_scanner.ai_brain import TradeAnalysis
from swing_scanner.strategies.base import SetupSignal


class DatabaseManager:
    """Handles SQLite persistence for scan results, signals, and trade ideas.

    The schema is designed to support historical lookback and future
    backtesting / win-rate tracking.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._connection() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Scans table: records every time the app runs a scan cycle.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbols_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT
                )
            """)

            # Signals table: records technical indicators for every symbol processed.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    is_candidate INTEGER NOT NULL,
                    close REAL NOT NULL,
                    rsi REAL NOT NULL,
                    macd REAL NOT NULL,
                    ema_20 REAL NOT NULL,
                    bb_lower REAL NOT NULL,
                    bb_upper REAL NOT NULL,
                    volume REAL NOT NULL,
                    avg_volume REAL NOT NULL,
                    FOREIGN KEY (scan_id) REFERENCES scans (id) ON DELETE CASCADE
                )
            """)

            # Trade Ideas table: records AI commentary and trade levels for candidates.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_ideas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER NOT NULL,
                    entry REAL NOT NULL,
                    target REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    risk_reward REAL NOT NULL,
                    thesis TEXT,
                    momentum TEXT,
                    trend TEXT,
                    volume_context TEXT,
                    setup_quality TEXT,
                    risks TEXT,
                    news_summary TEXT,
                    features_json TEXT,
                    source TEXT,
                    is_diagnostic INTEGER NOT NULL,
                    FOREIGN KEY (signal_id) REFERENCES signals (id) ON DELETE CASCADE
                )
            """)

            # Signal Outcomes table: tracks post-signal performance metrics
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    scan_timestamp TEXT NOT NULL,
                    evaluation_timestamp TEXT NOT NULL,
                    evaluation_window_days INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    latest_close REAL NOT NULL,
                    return_pct REAL NOT NULL,
                    max_gain_pct REAL NOT NULL,
                    max_drawdown_pct REAL NOT NULL,
                    target_hit INTEGER NOT NULL,
                    stop_hit INTEGER NOT NULL,
                    FOREIGN KEY (signal_id) REFERENCES signals (id) ON DELETE CASCADE,
                    UNIQUE(signal_id, evaluation_window_days)
                )
            """)

    def start_scan(self, symbols_count: int) -> int:
        """Record the start of a scan and return the scan_id."""
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO scans (timestamp, symbols_count, status) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), symbols_count, "started")
            )
            return cursor.lastrowid

    def complete_scan(self, scan_id: int, status: str = "completed", error_message: str | None = None) -> None:
        """Update the scan status upon completion or failure."""
        with self._connection() as conn:
            conn.execute(
                "UPDATE scans SET status = ?, error_message = ? WHERE id = ?",
                (status, error_message, scan_id)
            )

    def save_signal(self, scan_id: int, signal: SetupSignal, strategy_name: str) -> int:
        """Persist a SetupSignal to the database."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO signals (
                    scan_id, symbol, strategy, is_candidate, close, rsi, macd, 
                    ema_20, bb_lower, bb_upper, volume, avg_volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    signal.symbol,
                    strategy_name,
                    1 if signal.is_candidate else 0,
                    signal.close,
                    signal.rsi,
                    signal.macd,
                    signal.ema_20,
                    signal.bb_lower,
                    signal.bb_upper,
                    signal.volume,
                    signal.avg_volume
                )
            )
            return cursor.lastrowid

    def save_trade_idea(self, signal_id: int, analysis: TradeAnalysis, is_diagnostic: bool = False) -> int:
        """Persist a TradeAnalysis (Trade Idea) to the database."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trade_ideas (
                    signal_id, entry, target, stop_loss, risk_reward,
                    thesis, momentum, trend, volume_context, setup_quality,
                    risks, news_summary, features_json, source, is_diagnostic
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    analysis.entry,
                    analysis.target,
                    analysis.stop_loss,
                    analysis.risk_reward,
                    analysis.thesis,
                    analysis.momentum,
                    analysis.trend,
                    analysis.volume,  # analysis.volume is the commentary string
                    analysis.setup_quality,
                    analysis.risks,
                    analysis.news_summary,
                    json.dumps(analysis.features),
                    analysis.source,
                    1 if is_diagnostic else 0
                )
            )
            return cursor.lastrowid

    def get_recent_signals(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve the most recent signals for a given symbol."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT s.*, scans.timestamp 
                FROM signals s
                JOIN scans ON s.scan_id = scans.id
                WHERE s.symbol = ?
                ORDER BY scans.timestamp DESC
                LIMIT ?
                """,
                (symbol, limit)
            )
            return [dict(row) for row in rows]

    def save_signal_outcome(self, outcome: dict[str, Any]) -> int:
        """Persist a post-signal evaluation outcome to the database."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO signal_outcomes (
                    signal_id, symbol, strategy, scan_timestamp, evaluation_timestamp,
                    evaluation_window_days, entry_price, latest_close, return_pct,
                    max_gain_pct, max_drawdown_pct, target_hit, stop_hit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome["signal_id"],
                    outcome["symbol"],
                    outcome["strategy"],
                    outcome["scan_timestamp"],
                    outcome["evaluation_timestamp"],
                    outcome["evaluation_window_days"],
                    outcome["entry_price"],
                    outcome["latest_close"],
                    outcome["return_pct"],
                    outcome["max_gain_pct"],
                    outcome["max_drawdown_pct"],
                    1 if outcome["target_hit"] else 0,
                    1 if outcome["stop_hit"] else 0
                )
            )
            return cursor.lastrowid

    def get_pending_evaluations(self, window_days: int) -> list[dict[str, Any]]:
        """Find candidate signals that are old enough to evaluate but lack an outcome for this window."""
        with self._connection() as conn:
            # We want signals that are candidates (or have a trade idea)
            # that were scanned at least 'window_days' ago (plus a generous margin for weekends),
            # actually we can just fetch all candidates and in the python code check calendar/trading days.
            # To be safe, we fetch anything older than `window_days` calendar days.
            rows = conn.execute(
                """
                SELECT 
                    s.id as signal_id, 
                    s.symbol, 
                    s.strategy, 
                    scans.timestamp as scan_timestamp,
                    t.entry as entry_price,
                    t.target,
                    t.stop_loss
                FROM signals s
                JOIN scans ON s.scan_id = scans.id
                JOIN trade_ideas t ON s.id = t.signal_id
                LEFT JOIN signal_outcomes so ON s.id = so.signal_id AND so.evaluation_window_days = ?
                WHERE s.is_candidate = 1 
                  AND so.id IS NULL
                  AND date(scans.timestamp) <= date('now', '-' || ? || ' days')
                ORDER BY scans.timestamp ASC
                """,
                (window_days, window_days)
            )
            return [dict(row) for row in rows]
