from __future__ import annotations

import argparse
import time
from datetime import datetime

from swing_scanner.ai_brain import GeminiIdeaGenerator
from swing_scanner.analysis import analyze_symbol
from swing_scanner.config import Settings
from swing_scanner.data_layer import AngelOneDataClient, PerplexityNewsClient
from swing_scanner.delivery import TelegramNotifier, format_trade_idea
from swing_scanner.scheduler import is_market_hours, seconds_to_next_quarter


def run_scan(symbols: list[str], settings: Settings) -> list[str]:
    data_client = AngelOneDataClient(
        api_key=settings.angel_one_api_key,
        client_code=settings.angel_one_client_code,
        access_token=settings.angel_one_access_token,
    )
    news_client = PerplexityNewsClient(api_key=settings.perplexity_api_key)
    idea_generator = GeminiIdeaGenerator(api_key=settings.gemini_api_key)
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    alerts: list[str] = []
    for symbol in symbols:
        candles = data_client.fetch_candles(symbol=symbol)
        signal = analyze_symbol(symbol=symbol, candles=candles)
        if signal is None or not signal.is_candidate:
            continue
        news = news_client.latest_news_summary(symbol)
        idea = idea_generator.build_trade_idea(signal, news)
        message = format_trade_idea(idea)
        notifier.send(message)
        alerts.append(message)
    return alerts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Swing scanner runner")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbol tokens")
    parser.add_argument("--run-once", action="store_true", help="Run only one scan cycle")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    settings = Settings()

    while True:
        now = datetime.now()
        if is_market_hours(now):
            alerts = run_scan(symbols, settings)
            print(f"[{now.isoformat()}] Scan complete. Alerts: {len(alerts)}")
        else:
            print(f"[{now.isoformat()}] Outside market hours. Waiting.")

        if args.run_once:
            return
        time.sleep(seconds_to_next_quarter(datetime.now()))


if __name__ == "__main__":
    main()
