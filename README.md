# swing_scanner

Starter implementation of a stock swing scanner with this architecture:

1. **Data layer**
   - DhanHQ candles (NSE equities) via pluggable `MarketDataProvider`
   - Perplexity news summaries
   - Fixed weekday scan schedule
2. **Technical analysis engine**
   - `pandas` + `ta`
   - RSI, MACD, Bollinger Bands, EMA, and volume filters
3. **AI brain**
   - Gemini API integration point
   - Structured entry/target/stop-loss trade idea output
4. **Delivery**
   - Telegram bot alert sender

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m swing_scanner.app --symbols RELIANCE,INFY,TCS --run-once
```

## Doppler usage

```bash
doppler run -- python -m swing_scanner.app --symbols RELIANCE,INFY,TCS
```

## Environment variables

- `DHAN_CLIENT_ID`
- `DHAN_ACCESS_TOKEN`
- `PERPLEXITY_API_KEY`
- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Startup commands

```bash
# One scan cycle now
python -m swing_scanner.app --symbols RELIANCE,INFY,TCS --run-once

# Continuous weekday schedule (09:20, 12:15, 15:00 IST)
python -m swing_scanner.app --symbols RELIANCE,INFY,TCS
```

## Notes

- This is an initial scaffold with real API integration points and safe fallbacks.
- If indicator dependencies are not installed, the scanner skips analysis gracefully.
- Use `--run-once` for one immediate scan cycle, or omit it to run on weekdays at 09:20, 12:15, and 15:00 (IST).

## Dhan smoke test

```bash
python test_dhan.py              # defaults to RELIANCE
python test_dhan.py INFY
```

Credentials are loaded from `.env` (via `python-dotenv`). The script
prints the last 5 daily candles and exits non-zero on failure so it is
safe to wire into CI.

## Data provider architecture

- `swing_scanner/data_providers/base.py` – `MarketDataProvider` ABC + `Candle` dataclass
- `swing_scanner/data_providers/dhan_provider.py` – DhanHQ SDK implementation
- `swing_scanner/data_providers/mock_provider.py` – deterministic synthetic feed for tests

Swap providers by passing `data_provider=...` to `run_scan()`.
