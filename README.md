# 💹 Swing Scanner (NSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Market: NSE](https://img.shields.io/badge/Market-NSE-orange.svg)](https://www.nseindia.com/)
[![Deployment: DigitalOcean](https://img.shields.io/badge/Deployment-DigitalOcean-blue.svg)](https://www.digitalocean.com/)

A professional-grade, AI-powered swing-trade candidate scanner for the Indian Equities market (NSE). This tool bridges the gap between **deterministic quantitative filters** and **probabilistic AI reasoning**, delivering high-probability trade setups directly to your Telegram.

---

## 🌟 Why This Project?

Most trading bots are either purely technical (missing market context) or purely AI-based (hallucinating price levels). **Swing Scanner** solves this with a multi-layered architecture:

1.  **Quantitative Filter:** A high-performance engine scans thousands of data points to identify setups with specific RSI, MACD, and Bollinger Band characteristics.
2.  **Agentic Intelligence:** On detection, an AI Agent (Gemini 2.5 Flash) performs real-time Google Search grounding to understand *why* the stock is moving (earnings, news, sector tailwinds).
3.  **Deterministic Engine:** Trade levels (Entry, Target, Stop-Loss) are calculated using robust mathematical models, ensuring the AI never "invents" a price.

---

## ✨ Key Features

### 🧠 Grounded AI Analysis
Uses **Gemini 2.5 Flash** with search grounding to provide structured analyst-grade commentary. It evaluates:
- **Momentum & Trend:** RSI, MACD, and EMA relationship.
- **Volume Quality:** Relative volume vs. 20-bar averages.
- **Risk Assessment:** Real-time news catalysts and invalidation triggers.

### 🕒 NSE-Specific Intelligence
Automated scheduling aligned with the Indian market lifecycle:
- **09:20 IST:** Opening momentum scan (5m after open).
- **12:27 IST:** Mid-market stability check.
- **15:15 IST:** Closing window for EOD setups.

### 🗄️ Persistent Intelligence
Integrated **SQLite Persistence** records every scan, signal, and AI thesis. This creates a rich dataset for:
- Historical lookback of trade ideas.
- Win-rate and performance tracking.
- Quantitative backtesting of the "AI Thesis" vs. actual outcomes.

### ⚡ Parallelized Performance
Built with `ThreadPoolExecutor`, the scanner can process a 50+ symbol watchlist in seconds, ensuring you never miss a fast-moving setup.

---

## 🛠️ Tech Stack

- **Core:** Python 3.11+
- **Quantitative:** Pandas, TA-Lib (or fallback), yfinance
- **AI:** Google Gemini 2.5 Flash (via API)
- **Database:** SQLite3
- **Delivery:** Telegram Bot API
- **Networking:** Pure `urllib` (Zero third-party HTTP dependencies for minimal overhead)
- **Deployment:** DigitalOcean Droplet (Ubuntu/Linux)

---

## 🏗️ Architecture

```mermaid
graph TD
    A[Watchlist] --> B[Market Data Provider]
    B --> C[Strategy Engine]
    C -->|Deterministic Filter| D{Is Candidate?}
    D -->|Yes| E[News Agent - Search Grounding]
    E --> F[Gemini AI Analyst]
    F --> G[Deterministic Trade Engine]
    G --> H[SQLite Persistence]
    H --> I[Telegram Delivery]
    D -->|No| J[Log Signal to DB]
```

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/yourusername/swing_scanner.git
cd swing_scanner
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file from the example:
```bash
GEMINI_API_KEY=your_google_ai_studio_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. Usage
```powershell
# Run a single scan on the example watchlist
python -m swing_scanner.app --watchlist .\watchlist.example.txt --run-once

# Start the market-hours scheduler
python -m swing_scanner.app --watchlist .\watchlist.example.txt
```

---

## ☁️ Deployment

Production deployment assets are included:
- `deploy/systemd/swing-scanner.service` and `deploy/systemd/swing-scanner.timer`
- `deploy/scripts/install_systemd.sh`
- `.github/workflows/ci.yml` and `.github/workflows/deploy.yml`

Recommended VM model:
- Use the `systemd` timer to run `--run-once` at NSE windows.
- Keep secrets in `/etc/swing-scanner.env` with root-only permissions.
- Keep the production watchlist at `/opt/swing_scanner/watchlist.txt`.
- Use `sudo systemd-run --wait --collect --property=User=swing --property=Group=swing --property=WorkingDirectory=/opt/swing_scanner --property=EnvironmentFile=/etc/swing-scanner.env /opt/swing_scanner/.venv/bin/python -m swing_scanner.app --healthcheck --watchlist /opt/swing_scanner/watchlist.txt` as the post-deploy smoke check.

Preflight checklist (before enabling timer):
1. Create Linux user/group `swing`.
2. Create `/etc/swing-scanner.env` and set `chmod 600`.
3. Ensure `/opt/swing_scanner/watchlist.txt` exists and is readable.
4. Run `deploy/scripts/install_systemd.sh`.
5. Validate with:
   - `sudo systemctl start swing-scanner.service`
   - `journalctl -u swing-scanner.service -n 100 --no-pager`

Scheduler modes:
- **Production (recommended):** `systemd` timer (`deploy/systemd/swing-scanner.timer`) runs one-shot scans at fixed NSE windows.
- **Dev/local mode:** in-process loop (`python -m swing_scanner.app --watchlist ...`) depends on the host clock/timezone and is not the preferred production mode.

---

## 🧪 Testing

I maintain a high-quality codebase with 20+ comprehensive tests covering persistence, scheduling, HTTP retry behavior, and AI logic.

```powershell
python -m unittest discover -s tests -v
```

---

## 📋 Roadmap

- [x] **Persistence:** SQLite DB for historical lookback.
- [x] **NSE Scheduling:** Automation for Indian market hours.
- [ ] **FastAPI Backend:** REST API for mobile/web dashboards.
- [ ] **Multi-Broker Integration:** Native execution for Dhan, Zerodha, etc.

---

*Disclaimer: This is a tool for technical analysis. Trading involves risk. All trade ideas are generated for educational purposes and do not constitute financial advice.*
