from __future__ import annotations

from dataclasses import dataclass

try:
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import MACD, EMAIndicator
    from ta.volatility import BollingerBands
except ImportError:  # pragma: no cover
    pd = None
    RSIIndicator = MACD = EMAIndicator = BollingerBands = None

from swing_scanner.data_layer import Candle


@dataclass
class SetupSignal:
    symbol: str
    rsi: float
    macd: float
    ema_20: float
    bb_upper: float
    bb_lower: float
    close: float
    volume: float
    is_candidate: bool


def analyze_symbol(symbol: str, candles: list[Candle]) -> SetupSignal | None:
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
    is_candidate = bool(
        40 <= last["rsi"] <= 65
        and last["macd"] > 0
        and last["close"] > last["ema_20"]
        and last["volume"] >= (last["avg_volume"] or 0)
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
    )
