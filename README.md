# 💹 Swing Scanner (NSE)

A premium, daily swing-trade candidate scanner for Indian equities (NSE). This tool automates the process of identifying high-probability swing setups, enriching them with grounded AI analysis, and delivering trade ideas directly to Telegram.

---

## 🚀 Overview

*   **Market Focus:** NSE (Indian Equities)
*   **Currency:** INR (₹)
*   **Timezone:** Asia/Kolkata (UTC+05:30)
*   **Philosophy:** Deterministic filters identify *what* to trade; AI explains *why* it's moving.

## ✨ Key Features

*   **High-Performance Scanning:** Parallelized per-symbol pipeline using `ThreadPoolExecutor` (scans 16+ symbols in ~35s).
*   **Grounded AI Analysis:** Uses **Gemini 1.5 Flash** with Google Search grounding to fetch real-time news and generate structured trade theses.
*   **Deterministic Trade Engine:** Math-driven trade levels (Entry, Target, Stop-Loss) using a robust 3-stop logic and 2.0% risk floor.
*   **Rich Telegram Delivery:** Beautifully formatted alerts including risk/reward ratios, risk percentages, and multi-dimensional AI commentary (Momentum, Trend, Volume, Risks).
*   **Lightweight Architecture:** Zero third-party HTTP libraries (uses `urllib.request`). Graceful degradation if `pandas` or `ta` are missing.

## 🛠️ Quick Start

### 1. Installation
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file or set the following environment variables:
```bash
GEMINI_API_KEY=your_google_ai_studio_key
TELEGRAM_BOT_TOKEN=your_bot_token      # Optional
TELEGRAM_CHAT_ID=your_chat_id          # Optional
MARKET_DATA_PROVIDER=yfinance           # Default: yfinance (also supports: dhan, mock)
```

### 3. Run a Scan
```powershell
# Run once for the default watchlist
python -m swing_scanner.app --watchlist .\watchlist.example.txt --run-once

# Smoke test AI analysis for all symbols (diagnostic mode)
python -m swing_scanner.app --watchlist .\watchlist.example.txt --run-once --debug --force-analyze-all

# Run for specific symbols
python -m swing_scanner.app --symbols RELIANCE.NS,INFY.NS --run-once
```

## 🏗️ Architecture

1.  **Watchlist Manager:** Parses tickers from text files (supports comments and blank lines).
2.  **Market Data Provider:** Pluggable interface for fetching daily candles (default: `yfinance`).
3.  **Strategy Engine:** Deterministic 5-condition filter:
    *   RSI Range
    *   MACD Positive State
    *   Price relative to EMA20
    *   Bollinger Band Position
    *   Relative Volume
4.  **News Client:** Gemini-powered search grounding (or Perplexity) for latest market catalysts.
5.  **AI Analyst:** Gemini 1.5 Flash generates structured JSON commentary (Thesis, Momentum, Trend, Volume, Quality, Risks).
6.  **Trade Engine:** Calculates precise levels with risk-adjusted stops (capped at 4%, floor at 2%).
7.  **Notifier:** Dispatches formatted Telegram alerts or stdout logs.

## 🧪 Testing

The project uses the standard `unittest` framework.

```powershell
# Run all tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 📋 Environment Variables Reference

| Variable | Description | Default |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Key from Google AI Studio | **Required** |
| `MARKET_DATA_PROVIDER` | `yfinance`, `dhan`, `mock`, `finnhub` | `yfinance` |
| `SCAN_STRATEGY` | Strategy name from registry | `swing` |
| `GEMINI_MODEL` | Gemini model version | `gemini-2.5-flash` |
| `NEWS_SOURCE` | `gemini`, `perplexity`, `none` | `gemini` |
| `SCAN_MAX_WORKERS` | Parallel thread count | `8` |
| `SCAN_CACHE_TTL` | Cache duration (seconds) | `600` |

## 🗺️ Roadmap

- [ ] **Persistence:** SQLite DB for historical lookback and win-rate tracking.
- [ ] **NSE Scheduling:** Intraday/EOD automation aligned with NSE market hours.
- [ ] **Watchlist Tiers:** Separate A-list and B-list candidates for tiered scanning.
- [ ] **FastAPI Layer:** Backend for a future web-based dashboard.

---
*Disclaimer: This is a tool for technical analysis. Trading involves risk. Use the AI commentary as an analytical aid, not financial advice.*
