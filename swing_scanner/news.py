"""News summary clients.

Isolated from the market data layer so swapping market data providers
(Dhan, mock, etc.) doesn't churn news integration code.
"""
from __future__ import annotations

import json
from urllib import request


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
