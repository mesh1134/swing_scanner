"""Swing-trading candidate strategy.

Carries the original ``analysis.analyze_symbol`` logic verbatim — same
indicators, same thresholds, same ``< 30`` row floor — so behavior is
identical post-refactor. Future strategies (breakout, mean-reversion,
etc.) can live alongside this module without touching the scan loop.
"""
from __future__ import annotations

try:
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import MACD, EMAIndicator
    from ta.volatility import BollingerBands
except ImportError:  # pragma: no cover
    pd = None
    RSIIndicator = MACD = EMAIndicator = BollingerBands = None

from swing_scanner.data_providers import Candle
from swing_scanner.strategies.base import SetupSignal, Strategy


class SwingStrategy(Strategy):
    """Default long-bias swing setup detector.

    Candidate when, on the latest candle:
      * ``40 <= RSI(14) <= 65``
      * ``MACD diff > 0``
      * ``close > EMA(20)``
      * ``volume >= 20-bar avg volume``
      * ``close < upper Bollinger band (20, 2)``
    """

    strategy_name = "swing"

    def analyze(self, symbol: str, candles: list[Candle]) -> SetupSignal | None:
        if pd is None or not candles:
            return None

        frame = pd.DataFrame([c.__dict__ for c in candles])
        if frame.empty or len(frame) < 30:
            return None

        frame["rsi"] = RSIIndicator(close=frame["close"], window=14).rsi()
        macd = MACD(close=frame["close"])
        frame["macd"] = macd.macd_diff()
        frame["ema_20"] = EMAIndicator(close=frame["close"], window=20).ema_indicator()
        bb = BollingerBands(close=frame["close"], window=20, window_dev=2)
        frame["bb_upper"] = bb.bollinger_hband()
        frame["bb_lower"] = bb.bollinger_lband()
        frame["avg_volume"] = frame["volume"].rolling(20).mean()

        last = frame.iloc[-1]
        avg_volume = float(last["avg_volume"]) if pd.notna(last["avg_volume"]) else 0.0
        is_candidate = bool(
            40 <= last["rsi"] <= 65
            and last["macd"] > 0
            and last["close"] > last["ema_20"]
            and last["volume"] >= avg_volume
            and last["close"] < last["bb_upper"]
        )

        return SetupSignal(
            symbol=symbol,
            rsi=float(last["rsi"]),
            macd=float(last["macd"]),
            ema_20=float(last["ema_20"]),
            bb_upper=float(last["bb_upper"]),
            bb_lower=float(last["bb_lower"]),
            close=float(last["close"]),
            volume=float(last["volume"]),
            is_candidate=is_candidate,
            avg_volume=avg_volume,
        )
