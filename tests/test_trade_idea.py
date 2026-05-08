import unittest

from swing_scanner.ai_brain import GeminiIdeaGenerator
from swing_scanner.analysis import SetupSignal
from swing_scanner.delivery import format_trade_idea


class TradeIdeaTests(unittest.TestCase):
    def test_fallback_trade_idea(self):
        signal = SetupSignal(
            symbol="INFY",
            rsi=55.0,
            macd=0.3,
            ema_20=1490.0,
            bb_upper=1540.0,
            bb_lower=1460.0,
            close=1510.0,
            volume=1000000.0,
            is_candidate=True,
        )
        idea = GeminiIdeaGenerator(api_key="").build_trade_idea(signal, "Neutral")
        self.assertEqual(idea.symbol, "INFY")
        self.assertEqual(idea.direction, "LONG")
        self.assertGreater(idea.target, idea.entry)
        self.assertLess(idea.stop_loss, idea.entry)

    def test_format_trade_idea(self):
        signal = SetupSignal(
            symbol="TCS",
            rsi=54.0,
            macd=0.2,
            ema_20=3500.0,
            bb_upper=3600.0,
            bb_lower=3440.0,
            close=3550.0,
            volume=800000.0,
            is_candidate=True,
        )
        idea = GeminiIdeaGenerator(api_key="").build_trade_idea(signal, "Positive")
        text = format_trade_idea(idea)
        self.assertIn("Swing Alert: TCS", text)
        self.assertIn("Stop-Loss", text)


if __name__ == "__main__":
    unittest.main()
