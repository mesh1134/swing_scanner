from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import request

from swing_scanner.analysis import SetupSignal

MIN_RISK_PCT = 0.015
TARGET_R_MULTIPLE = 1.8


@dataclass
class TradeIdea:
    symbol: str
    direction: str
    entry: float
    target: float
    stop_loss: float
    rationale: str


class GeminiIdeaGenerator:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def build_trade_idea(self, signal: SetupSignal, news_summary: str) -> TradeIdea:
        if not self.api_key:
            return self._fallback(signal, news_summary)

        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={self.api_key}"
        )
        prompt = (
            "You are a swing trade assistant. Return strict JSON with keys: "
            "direction, entry, target, stop_loss, rationale. "
            f"Signal: {signal}. News: {news_summary}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=20) as response:
                raw = json.loads(response.read().decode("utf-8"))
            text = raw["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            return TradeIdea(
                symbol=signal.symbol,
                direction=parsed["direction"],
                entry=float(parsed["entry"]),
                target=float(parsed["target"]),
                stop_loss=float(parsed["stop_loss"]),
                rationale=str(parsed["rationale"]),
            )
        except Exception:
            return self._fallback(signal, news_summary)

    @staticmethod
    def _fallback(signal: SetupSignal, news_summary: str) -> TradeIdea:
        entry = signal.close
        risk = max(signal.close - signal.bb_lower, signal.close * MIN_RISK_PCT)
        target = signal.close + (risk * TARGET_R_MULTIPLE)
        stop = signal.close - risk
        return TradeIdea(
            symbol=signal.symbol,
            direction="LONG",
            entry=round(entry, 2),
            target=round(target, 2),
            stop_loss=round(stop, 2),
            rationale=f"Rule-based fallback using RSI/MACD/EMA setup. News: {news_summary}",
        )
