import json
from datetime import datetime
from typing import Any

from swing_scanner.config import Settings
from swing_scanner.data_providers.base import MarketDataProvider
from swing_scanner.persistence import DatabaseManager

def evaluate_outcomes(
    db: DatabaseManager,
    provider: MarketDataProvider,
    settings: Settings,
    debug: bool = False
) -> list[dict[str, Any]]:
    """Evaluate historical candidate signals to empirically measure strategy quality.
    
    Tracks post-signal price action over fixed evaluation windows (e.g. 5, 10 days)
    to calculate max gain, max drawdown, return percentage, and hit/miss on targets.
    """
    windows = [5, 10]
    outcomes = []
    
    for window in windows:
        pending = db.get_pending_evaluations(window)
        if not pending:
            continue
            
        for p in pending:
            symbol = p["symbol"]
            scan_time_str = p["scan_timestamp"]
            
            # scan_timestamp is ISO format from datetime.now().isoformat()
            try:
                scan_date = datetime.fromisoformat(scan_time_str).date()
            except ValueError:
                # fallback for older rows or unexpected formats
                scan_date = datetime.strptime(scan_time_str[:10], "%Y-%m-%d").date()
            
            # Fetch last 60 days to ensure we cover the window + weekends
            candles = provider.fetch_candles(symbol, lookback_days=60)
            if not candles:
                if debug:
                    print(f"[debug] evaluator: no candles fetched for {symbol}")
                continue
                
            # Filter candles strictly after the scan date
            post_scan_candles = []
            for c in candles:
                c_date_str = c.timestamp[:10]  # usually 'YYYY-MM-DD ...'
                try:
                    c_date = datetime.strptime(c_date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                    
                if c_date > scan_date:
                    post_scan_candles.append(c)
                    
            if len(post_scan_candles) < window:
                # Not enough trading days have elapsed
                if debug:
                    print(f"[debug] evaluator: skipping {symbol} (signal {p['signal_id']}) for {window}d window, only {len(post_scan_candles)} post-scan candles")
                continue
                
            # Truncate to the evaluation window
            eval_candles = post_scan_candles[:window]
            
            entry = p["entry_price"]
            target = p["target"]
            stop = p["stop_loss"]
            
            target_hit = False
            stop_hit = False
            highest = entry
            lowest = entry
            
            for c in eval_candles:
                if not target_hit and c.high >= target:
                    target_hit = True
                if not stop_hit and c.low <= stop:
                    stop_hit = True
                    
                if c.high > highest:
                    highest = c.high
                if c.low < lowest:
                    lowest = c.low
            
            # max_gain is calculated from the highest high seen, relative to entry
            max_gain_pct = (highest - entry) / entry * 100.0
            # max_drawdown is calculated from the lowest low seen, relative to entry
            max_drawdown_pct = (lowest - entry) / entry * 100.0
            
            latest_close = eval_candles[-1].close
            return_pct = (latest_close - entry) / entry * 100.0
            
            outcome = {
                "signal_id": p["signal_id"],
                "symbol": symbol,
                "strategy": p["strategy"],
                "scan_timestamp": scan_time_str,
                "evaluation_timestamp": datetime.now().isoformat(),
                "evaluation_window_days": window,
                "entry_price": entry,
                "latest_close": latest_close,
                "return_pct": round(return_pct, 2),
                "max_gain_pct": round(max_gain_pct, 2),
                "max_drawdown_pct": round(max_drawdown_pct, 2),
                "target_hit": target_hit,
                "stop_hit": stop_hit
            }
            
            db.save_signal_outcome(outcome)
            outcomes.append(outcome)
            
            if debug:
                print(
                    f"[debug] Evaluated {symbol} (signal {p['signal_id']}) "
                    f"for {window}d window: return={return_pct:.2f}% "
                    f"target={target_hit} stop={stop_hit}"
                )
                
    return outcomes
