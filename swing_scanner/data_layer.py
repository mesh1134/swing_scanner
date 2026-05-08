from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib import request

try:
    import pyotp
except ImportError:  # pragma: no cover
    pyotp = None

try:
    from SmartApi import SmartConnect
except ImportError:  # pragma: no cover
    SmartConnect = None


@dataclass
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class AngelOneDataClient:
    def __init__(self, api_key: str, client_code: str, mpin: str, totp_secret: str):
        self.api_key = api_key
        self.client_code = client_code
        self.mpin = mpin
        self.totp_secret = totp_secret

    def fetch_candles(self, symbol: str, interval: str = "FIFTEEN_MINUTE") -> list[Candle]:
        if not (self.api_key and self.client_code and self.mpin and self.totp_secret):
            return []
        if SmartConnect is None:
            return []

        auth_token = self._login()
        if not auth_token:
            return []

        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=15)
        payload = {
            "exchange": "NSE",
            "symboltoken": symbol,
            "interval": interval,
            "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate": to_dt.strftime("%Y-%m-%d %H:%M"),
        }
        try:
            smart = SmartConnect(api_key=self.api_key)
            smart.setAccessToken(auth_token)
            data = smart.getCandleData(payload)
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

    def _login(self) -> str:
        if pyotp is None:
            return ""
        try:
            smart = SmartConnect(api_key=self.api_key)
            session = smart.generateSession(
                self.client_code,
                self.mpin,
                pyotp.TOTP(self.totp_secret).now(),
            )
        except Exception:
            return ""
        data = session.get("data", {})
        return str(data.get("jwtToken", ""))


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
