from __future__ import annotations

import argparse
import time
from datetime import datetime

from swing_scanner.ai_brain import GeminiIdeaGenerator
from swing_scanner.analysis import analyze_symbol
from swing_scanner.config import Settings
from swing_scanner.data_providers import MarketDataProvider, build_provider
from swing_scanner.delivery import TelegramNotifier, format_trade_idea
from swing_scanner.news import PerplexityNewsClient
from swing_scanner.scheduler import register_weekday_scan_jobs
from swing_scanner.watchlist import load_watchlist


def run_scan(
    symbols: list[str],
    settings: Settings,
    data_provider: MarketDataProvider | None = None,
    debug: bool = False,
) -> list[str]:
    # The provider is injectable so tests can plug in fakes; the default
    # path delegates vendor selection to the factory, which reads
    # ``settings.market_data_provider`` (env: MARKET_DATA_PROVIDER).
    provider: MarketDataProvider = data_provider or build_provider(settings)
    news_client = PerplexityNewsClient(api_key=settings.perplexity_api_key)
    idea_generator = GeminiIdeaGenerator(api_key=settings.gemini_api_key)
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    if debug:
        print(f"[debug] provider={type(provider).__name__} symbols={symbols}")

    alerts: list[str] = []
    for symbol in symbols:
        # 90d window: comfortably exceeds analysis.py's 30-row floor and
        # absorbs weekends/holidays from any provider.
        candles = provider.fetch_candles(symbol=symbol, lookback_days=90)
        if debug:
            print(f"[debug] {symbol}: fetched {len(candles)} candles")
        signal = analyze_symbol(symbol=symbol, candles=candles)
        if debug:
            _log_signal(symbol, signal, len(candles))
        if signal is None or not signal.is_candidate:
            continue
        news = news_client.latest_news_summary(symbol)
        idea = idea_generator.build_trade_idea(signal, news)
        message = format_trade_idea(idea)
        notifier.send(message)
        alerts.append(message)
    return alerts


def _log_signal(symbol: str, signal, candle_count: int) -> None:
    """Render the per-symbol indicator state so a 0-alerts run is diagnosable."""
    if signal is None:
        # analyze_symbol returns None when pandas is missing or there are
        # too few rows (< 30) to compute the 20-window indicators.
        print(
            f"[debug] {symbol}: no signal (candles={candle_count}, "
            "likely below the 30-row analysis floor)"
        )
        return
    print(
        f"[debug] {symbol}: candidate={signal.is_candidate} "
        f"close={signal.close:.2f} rsi={signal.rsi:.2f} macd={signal.macd:.4f} "
        f"ema20={signal.ema_20:.2f} bb=[{signal.bb_lower:.2f},{signal.bb_upper:.2f}] "
        f"vol={signal.volume:.0f}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Swing scanner runner")
    # --symbols and --watchlist are interchangeable sources; at least one
    # is required. CLI --symbols wins if both are supplied.
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--symbols", help="Comma-separated symbol tokens")
    source.add_argument(
        "--watchlist",
        help="Path to a watchlist file (one symbol per line; '#' comments allowed).",
    )
    parser.add_argument("--run-once", action="store_true", help="Run only one scan cycle")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print per-symbol candle count and indicator values for every scan.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = load_watchlist(args.watchlist)
    if not symbols:
        raise SystemExit("No symbols to scan; check --symbols or --watchlist input.")
    settings = Settings()

    def scheduled_job() -> None:
        now = datetime.now()
        try:
            # CLI --debug wins; otherwise honor SCAN_DEBUG env (Settings).
            alerts = run_scan(
                symbols, settings, debug=args.debug or settings.scan_debug
            )
            print(f"[{now.isoformat()}] Fixed-time scan complete. Alerts: {len(alerts)}")
        except Exception as exc:
            print(f"[{now.isoformat()}] Scan skipped due to recoverable error: {exc}")

    if args.run_once:
        scheduled_job()
        return

    import schedule

    register_weekday_scan_jobs(schedule, scheduled_job)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
