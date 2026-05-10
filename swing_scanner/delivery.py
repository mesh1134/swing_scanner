from __future__ import annotations

from urllib import parse

from swing_scanner.ai_brain import TradeAnalysis
from swing_scanner.http_client import HttpRequestError, post_form


def format_trade_idea(analysis: TradeAnalysis, diagnostic: bool = False) -> str:
    """Render a :class:`TradeAnalysis` as a Telegram-friendly message.

    Layout intentionally keeps numeric trade levels at the top (where a
    trader scans first) and analyst commentary below. The ``source`` tag
    flags whether commentary came from the LLM or the rule-based
    fallback.

    When ``diagnostic`` is True (used by --force-analyze-all for
    non-candidates), a clear banner is prepended and the header label
    changes from "Swing Alert" to "Diagnostic" so the message can never
    be mistaken for a real trade signal even if copy-pasted out of
    context.
    """
    src_tag = "AI" if analysis.source == "llm" else "rule-based"
    risk_pct = (
        (analysis.entry - analysis.stop_loss) / analysis.entry * 100.0
        if analysis.entry
        else 0.0
    )
    if diagnostic:
        header = (
            "[DIAGNOSTIC \u2014 non-candidate; trade levels are reference only]\n"
            f"Diagnostic: {analysis.symbol}  [{analysis.strategy_name}]"
        )
    else:
        header = f"Swing Alert: {analysis.symbol}  [{analysis.strategy_name}]"
    # Extract base symbol without the .NS suffix for Groww search
    base_symbol = analysis.symbol.split(".")[0]
    groww_link = f"https://groww.in/search?q={base_symbol}"

    return (
        f"{header}\n"
        f"Direction: {analysis.direction}\n"
        f"Entry: \u20b9{analysis.entry}   Target: \u20b9{analysis.target}   "
        f"Stop: \u20b9{analysis.stop_loss}   "
        f"Risk: {risk_pct:.2f}%   R:R 1:{analysis.risk_reward}\n"
        f"\n"
        f"Thesis ({src_tag}): {analysis.thesis}\n"
        f"Momentum: {analysis.momentum}\n"
        f"Trend: {analysis.trend}\n"
        f"Volume: {analysis.volume}\n"
        f"Quality: {analysis.setup_quality}\n"
        f"Risks: {analysis.risks}\n"
        f"\n"
        f"\U0001F50D Trade on Groww: {groww_link}"
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
        try:
            body = post_form(endpoint, payload)
            return bool(body.get("ok"))
        except HttpRequestError:
            return False
