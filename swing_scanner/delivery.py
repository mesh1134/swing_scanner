from __future__ import annotations

import json
from urllib import parse, request

from swing_scanner.ai_brain import TradeIdea


def format_trade_idea(idea: TradeIdea) -> str:
    return (
        f"📈 Swing Alert: {idea.symbol}\n"
        f"Direction: {idea.direction}\n"
        f"Entry: {idea.entry}\n"
        f"Target: {idea.target}\n"
        f"Stop-Loss: {idea.stop_loss}\n"
        f"Why: {idea.rationale}"
    )


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, text: str) -> bool:
        if not (self.bot_token and self.chat_id):
            return False
        endpoint = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = parse.urlencode({"chat_id": self.chat_id, "text": text}).encode("utf-8")
        req = request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                body = json.loads(response.read().decode("utf-8"))
            return bool(body.get("ok"))
        except Exception:
            return False
