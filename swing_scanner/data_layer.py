from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import request


@dataclass
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class AngelOneDataClient:
    def __init__(self, api_key: str, client_code: str, access_token: str):
        self.api_key = api_key
        self.client_code = client_code
        self.access_token = access_token

    def fetch_candles(self, symbol: str, interval: str = "FIFTEEN_MINUTE") -> list[Candle]:
        if not (self.api_key and self.client_code and self.access_token):
            return []

        url = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
        payload = {
            "exchange": "NSE",
            "symboltoken": symbol,
            "interval": interval,
        }
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
                "X-PrivateKey": self.api_key,
                "X-UserType": "USER",
                "X-SourceID": "WEB",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []

        candles: list[Candle] = []
        for row in data.get("data", []):
            if len(row) < 6:
                continue
            candles.append(
                Candle(
                    timestamp=str(row[0]),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return candles


class PerplexityNewsClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def latest_news_summary(self, symbol: str) -> str:
        if not self.api_key:
            return "No news API key configured."
        url = "https://api.perplexity.ai/chat/completions"
        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "user",
                    "content": f"Provide a concise latest market-moving news summary for {symbol}.",
                }
            ],
            "temperature": 0.2,
        }
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except Exception:
            return "Unable to fetch news summary."
