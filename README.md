# swing_scanner

Starter implementation of a stock swing scanner with this architecture:

1. **Data layer**
   - Angel One SmartAPI candles (NSE/BSE symbols)
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

## Environment variables

- `ANGEL_ONE_API_KEY`
- `ANGEL_ONE_CLIENT_CODE`
- `ANGEL_ONE_MPIN`
- `ANGEL_ONE_TOTP_SECRET`
- `PERPLEXITY_API_KEY`
- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Notes

- This is an initial scaffold with real API integration points and safe fallbacks.
- If indicator dependencies are not installed, the scanner skips analysis gracefully.
- Use `--run-once` for one immediate scan cycle, or omit it to run on weekdays at 09:20, 12:15, and 15:00 (IST).
