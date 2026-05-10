from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

# Force UTF-8 on stdout/stderr so the rupee symbol (\u20b9) and other
# non-ASCII output survive redirection to a file or capture by cron /
# systemd / CI on Windows (cp1252 console default would otherwise raise
# UnicodeEncodeError mid-scan and abort the run).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):  # pragma: no cover
        # Older Python or non-TextIOWrapper stream; skip silently.
        pass

from swing_scanner.ai_brain import GeminiTradeAnalyst
from swing_scanner.config import Settings
from swing_scanner.data_providers import MarketDataProvider, build_provider
from swing_scanner.delivery import TelegramNotifier, format_trade_idea
from swing_scanner.evaluator import evaluate_outcomes
from swing_scanner.news import build_news_client
from swing_scanner.scheduler import register_weekday_scan_jobs
from swing_scanner.persistence import DatabaseManager
from swing_scanner.strategies import build_strategy
from swing_scanner.watchlist import load_watchlist


def run_scan(
    symbols: list[str],
    settings: Settings,
    data_provider: MarketDataProvider | None = None,
    debug: bool = False,
    force_analyze_all: bool = False,
    db: DatabaseManager | None = None,
) -> list[str]:
    """Run one scan cycle and return the list of formatted alert strings.

    ``force_analyze_all`` is a diagnostic mode: the deterministic
    candidate gate is bypassed, every signal is sent to the LLM, and
    results are printed to stdout instead of pushed to Telegram. Use it
    to exercise the AI/news layers end-to-end on quiet days.
    """
    # The provider is injectable so tests can plug in fakes; the default
    # path delegates vendor selection to the factory, which reads
    # ``settings.market_data_provider`` (env: MARKET_DATA_PROVIDER).
    provider: MarketDataProvider = data_provider or build_provider(settings)
    # Strategy is selected by SCAN_STRATEGY (default "swing") and is the
    # only piece of code aware of candidate-selection rules.
    strategy = build_strategy(settings.scan_strategy)
    news_client = build_news_client(settings)
    analyst = GeminiTradeAnalyst(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )
    notifier = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    if debug:
        print(
            f"[debug] provider={type(provider).__name__} "
            f"strategy={strategy.strategy_name} "
            f"news={type(news_client).__name__} "
            f"model={settings.gemini_model} "
            f"force_analyze_all={force_analyze_all} symbols={symbols}"
        )

    # The per-symbol pipeline (fetch -> strategy -> news -> analyst) is
    # I/O-bound, so threads parallelise it cheaply. Telegram sends and
    # stdout output stay in the main thread to keep alert ordering
    # deterministic and prevent interleaved debug logs.
    max_workers = max(1, min(settings.scan_max_workers, len(symbols)))

    scan_id = db.start_scan(len(symbols)) if db else None

    def worker(symbol: str) -> _SymbolResult:
        return _process_symbol(
            symbol=symbol,
            provider=provider,
            strategy=strategy,
            news_client=news_client,
            analyst=analyst,
            debug=debug,
            force_analyze_all=force_analyze_all,
            db=db,
            scan_id=scan_id,
        )

    if max_workers == 1:
        results: list[_SymbolResult] = [worker(s) for s in symbols]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            # executor.map preserves input order, which keeps the debug
            # log and Telegram delivery in watchlist sequence.
            results = list(pool.map(worker, symbols))

    alerts: list[str] = []
    sent_count = 0
    for result in results:
        for line in result.debug_lines:
            print(line)
        if result.message is None:
            continue
        if result.is_force_diag:
            print(
                f"\n--- [force-analyze, candidate=False] {result.symbol} ---\n"
                f"{result.message}\n"
            )
        else:
            if notifier.send(result.message):
                sent_count += 1
        alerts.append(result.message)

    if debug or force_analyze_all:
        print(
            f"[debug] scan summary: analysed={len(alerts)} "
            f"sent_to_telegram={sent_count}"
        )
    
    if db and scan_id:
        db.complete_scan(scan_id)

    return alerts


@dataclass
class _SymbolResult:
    """Per-symbol output of the parallel scan worker.

    ``message`` is None when the symbol was filtered out (no signal, or
    non-candidate in normal mode). ``is_force_diag`` flags the
    force-analyze case where the message must be printed instead of sent.
    ``debug_lines`` is buffered in the worker so the main thread can
    print them in symbol order without thread interleaving.
    """

    symbol: str
    message: str | None
    is_force_diag: bool
    debug_lines: list[str]


def _process_symbol(
    symbol: str,
    provider: MarketDataProvider,
    strategy,
    news_client,
    analyst: GeminiTradeAnalyst,
    debug: bool,
    force_analyze_all: bool,
    db: DatabaseManager | None = None,
    scan_id: int | None = None,
) -> _SymbolResult:
    """Run the per-symbol pipeline. Pure I/O + computation, no stdout.

    Debug output is captured into ``debug_lines`` instead of printed so
    the main thread can flush it in order, keeping logs readable when
    multiple symbols run concurrently.
    """
    debug_lines: list[str] = []
    # 90d window: comfortably exceeds analysis.py's 30-row floor and
    # absorbs weekends/holidays from any provider.
    candles = provider.fetch_candles(symbol=symbol, lookback_days=90)
    if debug:
        debug_lines.append(f"[debug] {symbol}: fetched {len(candles)} candles")
    signal = strategy.analyze(symbol=symbol, candles=candles)
    if debug:
        debug_lines.append(
            _format_signal_log(symbol, signal, len(candles), strategy.strategy_name)
        )
    if signal is None:
        return _SymbolResult(symbol, None, False, debug_lines)

    signal_id = None
    if db and scan_id:
        signal_id = db.save_signal(scan_id, signal, strategy.strategy_name)

    # Normal mode: only real candidates reach the LLM. Force mode:
    # bypass the gate so the AI/news layers can be exercised on
    # quiet days. The analyst explains; it never decides.
    if not signal.is_candidate and not force_analyze_all:
        return _SymbolResult(symbol, None, False, debug_lines)

    news = news_client.latest_news_summary(symbol)
    analysis = analyst.analyze(
        signal=signal,
        strategy_name=strategy.strategy_name,
        news_summary=news,
        debug=debug,
        debug_sink=debug_lines,
    )
    is_force_diag = force_analyze_all and not signal.is_candidate
    
    if db and signal_id:
        db.save_trade_idea(signal_id, analysis, is_diagnostic=is_force_diag)

    # Tag the rendered message itself when this is a diagnostic
    # (non-candidate) emission so the alert can never be mistaken for
    # a real trade signal even if copy-pasted out of console context.
    message = format_trade_idea(analysis, diagnostic=is_force_diag)
    return _SymbolResult(symbol, message, is_force_diag, debug_lines)


def _format_signal_log(
    symbol: str, signal, candle_count: int, strategy_name: str
) -> str:
    """Render the per-symbol indicator state as a string.

    Returns a string instead of printing so the parallel scan worker
    can buffer it and the main thread can flush logs in symbol order.
    """
    if signal is None:
        # Strategies return None when pandas is missing or there are
        # too few rows (< 30) to compute the 20-window indicators.
        return (
            f"[debug] {symbol} [{strategy_name}]: no signal "
            f"(candles={candle_count}, likely below the 30-row analysis floor)"
        )
    return (
        f"[debug] {symbol} [{strategy_name}]: candidate={signal.is_candidate} "
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
    parser.add_argument(
        "--force-analyze-all",
        action="store_true",
        help=(
            "Diagnostic: bypass the candidate gate and run the AI analyst on "
            "every signal. Output is printed; Telegram is skipped for "
            "non-candidates so the alert channel stays clean."
        ),
    )
    parser.add_argument(
        "--evaluate-outcomes",
        action="store_true",
        help="Evaluate historical signals against actual post-scan price action."
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

    if args.evaluate_outcomes:
        if not settings.scan_db_path:
            raise SystemExit("Database not configured; cannot evaluate outcomes.")
        db = DatabaseManager(settings.scan_db_path)
        provider = build_provider(settings)
        print(f"[{datetime.now().isoformat()}] Starting outcome evaluation...")
        outcomes = evaluate_outcomes(
            db=db, 
            provider=provider, 
            settings=settings, 
            debug=args.debug or settings.scan_debug
        )
        print(f"[{datetime.now().isoformat()}] Evaluated {len(outcomes)} pending outcomes.")
        return

    def scheduled_job() -> None:
        now = datetime.now()
        db = DatabaseManager(settings.scan_db_path) if settings.scan_db_path else None
        try:
            # CLI --debug wins; otherwise honor SCAN_DEBUG env (Settings).
            alerts = run_scan(
                symbols,
                settings,
                debug=args.debug or settings.scan_debug,
                force_analyze_all=args.force_analyze_all,
                db=db,
            )
            print(
                f"[{now.isoformat()}] Scan complete. "
                f"Signals analysed: {len(alerts)}"
            )
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
