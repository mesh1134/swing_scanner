import os
import sqlite3
import unittest
from datetime import datetime
from swing_scanner.persistence import DatabaseManager
from swing_scanner.strategies.base import SetupSignal
from swing_scanner.ai_brain import TradeAnalysis

class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_persistence.db"
        self._cleanup()
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        # Force garbage collection to close any dangling sqlite handles
        import gc
        gc.collect()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass

    def test_init_db(self):
        """Verify that tables are created correctly."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            self.assertIn("scans", tables)
            self.assertIn("signals", tables)
            self.assertIn("trade_ideas", tables)
        finally:
            conn.close()

    def test_scan_lifecycle(self):
        """Test recording scan start and completion."""
        scan_id = self.db.start_scan(10)
        self.assertEqual(scan_id, 1)
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
            self.assertEqual(row["symbols_count"], 10)
            self.assertEqual(row["status"], "started")
        finally:
            conn.close()

        self.db.complete_scan(scan_id)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
            self.assertEqual(row["status"], "completed")
        finally:
            conn.close()

    def test_save_signal_and_trade_idea(self):
        """Test persisting a signal and an associated trade idea."""
        scan_id = self.db.start_scan(1)
        signal = SetupSignal(
            symbol="RELIANCE.NS",
            rsi=55.0,
            macd=0.5,
            ema_20=2500.0,
            bb_upper=2600.0,
            bb_lower=2400.0,
            close=2550.0,
            volume=1000000,
            is_candidate=True,
            avg_volume=900000
        )
        signal_id = self.db.save_signal(scan_id, signal, "swing")
        self.assertEqual(signal_id, 1)

        analysis = TradeAnalysis(
            symbol="RELIANCE.NS",
            strategy_name="swing",
            direction="LONG",
            entry=2550.0,
            target=2700.0,
            stop_loss=2450.0,
            risk_reward=1.8,
            thesis="Bullish momentum",
            momentum="RSI rising",
            trend="Above EMA20",
            volume="Strong",
            setup_quality="High",
            risks="Market volatility",
            news_summary="Good earnings",
            features={"some": "feature"},
            source="llm"
        )
        idea_id = self.db.save_trade_idea(signal_id, analysis)
        self.assertEqual(idea_id, 1)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Check signal
            sig_row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
            self.assertEqual(sig_row["symbol"], "RELIANCE.NS")
            self.assertEqual(sig_row["close"], 2550.0)
            
            # Check trade idea
            idea_row = conn.execute("SELECT * FROM trade_ideas WHERE signal_id = ?", (signal_id,)).fetchone()
            self.assertEqual(idea_row["entry"], 2550.0)
            self.assertEqual(idea_row["thesis"], "Bullish momentum")
            self.assertEqual(idea_row["is_diagnostic"], 0)
        finally:
            conn.close()

    def test_get_recent_signals(self):
        """Test retrieving recent signals for a symbol."""
        for i in range(3):
            scan_id = self.db.start_scan(1)
            signal = SetupSignal(
                symbol="TCS.NS",
                rsi=50.0 + i,
                macd=0.1,
                ema_20=3000.0,
                bb_upper=3100.0,
                bb_lower=2900.0,
                close=3050.0,
                volume=500000,
                is_candidate=True
            )
            self.db.save_signal(scan_id, signal, "swing")
            self.db.complete_scan(scan_id)

        recent = self.db.get_recent_signals("TCS.NS", limit=2)
        self.assertEqual(len(recent), 2)
        # Order should be descending by timestamp (newest first)
        self.assertEqual(recent[0]["rsi"], 52.0)
        self.assertEqual(recent[1]["rsi"], 51.0)

if __name__ == "__main__":
    unittest.main()
