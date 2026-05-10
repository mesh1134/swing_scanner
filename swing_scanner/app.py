from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

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
from swing_scanner.logging_utils import configure_logging
from swing_scanner.news import build_news_client
from swing_scanner.scheduler import register_weekday_scan_jobs
from swing_scanner.persistence import DatabaseManager
from swing_scanner.strategies import build_strategy
from swing_scanner.watchlist import load_watchlist

logger = logging.getLogger(__name__)
DEFAULT_HEALTHCHECK_WATCHLIST = "watchlist.example.txt"


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
    started_at = time.monotonic()

    scan_id = db.start_scan(len(symbols)) if db else None
    logger.info(
        "scan_start",
        extra={"event": "scan_start", "scan_id": scan_id, "status": "started"},
    )

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
    duration_ms = int((time.monotonic() - started_at) * 1000)
    logger.info(
        "scan_complete",
        extra={
            "event": "scan_complete",
            "scan_id": scan_id,
            "duration_ms": duration_ms,
            "status": "completed",
        },
    )

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
    symbol_started = time.monotonic()
    try:
        candles = provider.fetch_candles(symbol=symbol, lookback_days=90)
    except Exception:
        logger.exception(
            "symbol_fetch_failed",
            extra={"event": "symbol_fetch_failed", "scan_id": scan_id, "symbol": symbol, "status": "failed"},
        )
        return _SymbolResult(symbol, None, False, debug_lines)
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
    logger.info(
        "symbol_processed",
        extra={
            "event": "symbol_processed",
            "scan_id": scan_id,
            "symbol": symbol,
            "status": "ok",
            "duration_ms": int((time.monotonic() - symbol_started) * 1000),
        },
    )
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
    source = parser.add_mutually_exclusive_group(required=False)
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
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Validate configuration and exit 0 without scanning.",
    )
    return parser.parse_args()


def _resolve_healthcheck_watchlist(args: argparse.Namespace) -> tuple[str, str]:
    if args.watchlist:
        return args.watchlist, "cli(--watchlist)"
    env_watchlist = os.getenv("SCAN_WATCHLIST_PATH", "").strip()
    if env_watchlist:
        return env_watchlist, "env(SCAN_WATCHLIST_PATH)"
    return DEFAULT_HEALTHCHECK_WATCHLIST, f"default({DEFAULT_HEALTHCHECK_WATCHLIST})"


def _run_healthcheck(args: argparse.Namespace, settings: Settings) -> list[str]:
    errors: list[str] = []

    watchlist_path, watchlist_source = _resolve_healthcheck_watchlist(args)
    try:
        symbols = load_watchlist(watchlist_path)
        if not symbols:
            errors.append(f"Watchlist has no symbols: {watchlist_path}")
    except Exception as exc:
        errors.append(
            f"Watchlist unreadable ({watchlist_source}): {watchlist_path} ({exc})"
        )

    if settings.scan_db_path:
        db_path = Path(settings.scan_db_path)
        db_dir = db_path.parent if str(db_path.parent) else Path(".")
        if not db_dir.exists():
            errors.append(f"DB directory does not exist: {db_dir}")
        elif not os.access(db_dir, os.W_OK):
            errors.append(f"DB directory is not writable: {db_dir}")
        else:
            try:
                if db_path.exists():
                    uri = f"file:{db_path.resolve().as_posix()}?mode=rw"
                    with sqlite3.connect(uri, uri=True, timeout=2.0) as conn:
                        conn.execute("PRAGMA user_version").fetchone()
                else:
                    probe = db_dir / ".scan_db_write_probe"
                    with open(probe, "w", encoding="utf-8"):
                        pass
                    probe.unlink(missing_ok=True)
            except Exception as exc:
                errors.append(f"DB path is not writable/usable: {db_path} ({exc})")

    provider_name = settings.market_data_provider.strip().lower()
    if provider_name == "dhan" and (
        not settings.dhan_client_id or not settings.dhan_access_token
    ):
        errors.append(
            "MARKET_DATA_PROVIDER=dhan requires DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN"
        )

    news_source = settings.news_source.strip().lower()
    if news_source == "gemini" and not settings.gemini_api_key:
        errors.append("NEWS_SOURCE=gemini requires GEMINI_API_KEY")
    if news_source == "perplexity" and not settings.perplexity_api_key:
        errors.append("NEWS_SOURCE=perplexity requires PERPLEXITY_API_KEY")

    if settings.telegram_heartbeat_enabled and (
        not settings.telegram_bot_token or not settings.telegram_chat_id
    ):
        errors.append(
            "TELEGRAM_HEARTBEAT_ENABLED requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
        )

    return errors


def main() -> None:
    configure_logging()
    args = parse_args()
    settings = Settings()

    if args.healthcheck:
        errors = _run_healthcheck(args, settings)
        if errors:
            for err in errors:
                logger.error(
                    f"healthcheck_error: {err}",
                    extra={"event": "healthcheck_error", "status": "failed"},
                )
                print(f"HEALTHCHECK_ERROR: {err}")
            raise SystemExit(1)
        logger.info(
            "healthcheck_ok",
            extra={"event": "healthcheck_ok", "status": "ok"},
        )
        print("OK")
        return

    if not args.symbols and not args.watchlist:
        raise SystemExit("Provide either --symbols or --watchlist (or use --healthcheck).")
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = load_watchlist(args.watchlist)
    if not symbols:
        raise SystemExit("No symbols to scan; check --symbols or --watchlist input.")

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
        now = datetime.now(ZoneInfo(settings.app_timezone))
        db = DatabaseManager(settings.scan_db_path) if settings.scan_db_path else None
        notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
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
            if settings.telegram_heartbeat_enabled:
                notifier.send(
                    f"Heartbeat: scan finished at {now.isoformat()} ({settings.app_timezone}), alerts={len(alerts)}"
                )
        except Exception as exc:
            print(f"[{now.isoformat()}] Scan skipped due to recoverable error: {exc}")
            logger.exception(
                "scan_failed",
                extra={"event": "scan_failed", "status": "failed"},
            )
            if settings.telegram_heartbeat_enabled:
                notifier.send(
                    f"ALERT: scan failed at {now.isoformat()} ({settings.app_timezone}) error={exc}"
                )

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
