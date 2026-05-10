## Production Readiness Audit Plan - Swing Scanner (DigitalOcean $6 VM)

### Summary
- Current architecture is a Python monolith with in-process scheduling, threaded per-symbol scanning, SQLite persistence, and Telegram delivery.
- Core flow is clear and modular, but production maturity is limited by missing deployment automation, timezone fragility, weak observability, and concurrency risk around SQLite writes.
- Repo evidence shows no codified infra/deploy assets (`.github/workflows`, `Dockerfile`, `systemd` units), so deployment is currently manual/implicit.
- Baseline tests pass locally (`18/18`), but they do not cover live API limits, VM hardening, or deployment safety.

### System Map (Current)
- Ingestion: `watchlist` -> provider factory -> `yfinance`/`dhan` fetch.
- Signal engine: strategy computes RSI/MACD/EMA/BB and candidate flag.
- Intelligence: only candidates go through news summary + Gemini analyst.
- Persistence: every signal plus candidate trade ideas stored in SQLite.
- Delivery: formatted alert to Telegram Bot API.
- Main code anchors:
  - `swing_scanner/app.py`
  - `swing_scanner/scheduler.py`
  - `swing_scanner/persistence.py`

### VM & Deployment Analysis
- Current state assessment:
  - Runtime loop is process-resident (`schedule.run_pending()` + `sleep(1)`), so Python stays in memory continuously.
  - Scheduler uses naive local time (`datetime.now()`), so NSE timing is only correct if server timezone is explicitly IST.
  - Process management is documented as “systemd or screen” but not enforced/configured in repo.
  - No CI/CD pipeline is present; no GitHub Actions workflows found.
- Proposed production model (lightweight, low-RAM):
  - Use `systemd` `oneshot` service + `systemd` timer (09:20, 12:27, 15:15 IST) to run `--run-once`.
  - Keep process ephemeral instead of always-on loop to reduce idle RAM and leak surface.
  - Store secrets in `/etc/swing-scanner.env` (`chmod 600`, root-owned).
  - Enable journald retention caps and structured logs.
  - Add UFW baseline (`22/tcp` restricted, deny inbound by default, allow outbound).
- Proposed CI/CD workflow (GitHub Actions -> Droplet via SSH):
  - CI on PR/push: setup Python 3.11, install deps, run unit tests.
  - Deploy on `main` (or release tag): single concurrency lock, SSH with deploy key, pull exact commit SHA, install deps, restart `systemd` unit/timer, run post-deploy smoke check, auto-rollback to previous SHA on failure.
  - Keep it simple: no Docker required for this workload.

### Vulnerabilities & Technical Debt

#### Critical
- Timezone correctness risk for market scans (naive `datetime.now()` in scheduler path).
- SQLite write contention risk under threaded workers (multiple concurrent writes with separate connections can lock DB).
- API key exposure risk by embedding Gemini key in request URL query string.
- No automated deployment gate; manual deploy path risks drift and broken production.

#### High
- No codified process supervision artifacts (unit/timer files absent in repo).
- No request backoff/retry + rate-limit handling for Telegram/Gemini/Perplexity (`429/5xx` resilience gap).
- Exceptions are broadly swallowed in external calls, reducing alertability and masking degraded mode.
- Monitoring drift: docs mention Telegram heartbeats, but no heartbeat implementation found.
- No resource guardrails for tiny VM (worker tuning, memory cap strategy, API concurrency cap not enforced operationally).

#### Low
- Dependency footprint appears heavier than runtime needs (possible unused packages).
- `.env.example` and operational docs can drift from real runtime flags.
- README includes local `file://` image path, reducing reproducibility.

### Action Plan (Execution Checklist)
1. Lock runtime architecture for low-cost VM:
   - Switch to `systemd timer + --run-once` execution model.
   - Make IST explicit in scheduling (zone-aware time handling).
2. Harden persistence path:
   - Serialize DB writes (single writer queue or batched writes), enable WAL mode, set busy timeout, add DB health/error metrics.
3. Add API resilience:
   - Centralize HTTP client wrapper with timeout, retry (exponential backoff + jitter), and 429 handling.
   - Add outbound rate limiting for Telegram and LLM/news calls.
4. Secure secrets and host:
   - Move secrets to root-only env file, rotate exposed keys, stop putting API keys in URLs, enforce UFW and SSH hardening checklist.
5. Establish CI/CD:
   - Add GitHub Actions `ci.yml` (tests/lint), `deploy.yml` (SSH deploy, restart service, smoke check, rollback).
   - Add deploy concurrency lock and environment protection (manual approval for production).
6. Improve observability:
   - Structured logs with scan_id/symbol/duration/status.
   - Add heartbeat + failure notification to Telegram.
   - Add startup diagnostics and post-deploy smoke command.
7. Add production validation tests:
   - Concurrency test with real SQLite contention scenario.
   - Timezone scheduling tests (UTC server vs IST target).
   - Failure-path tests for API retry/timeout and degraded-mode behavior.

### Assumptions & Defaults
- Assumption: no direct server access in this phase; VM/security findings are repo-based plus deployment-doc inference.
- Default chosen: `systemd timer` over Docker/PM2 to minimize RAM and operational complexity on a $6 droplet.
- Default chosen: GitHub Actions + SSH deploy keyed to `main`, with rollback on failed smoke checks.
- Target outcome: reliable scans at exact NSE windows, safe automated deployments, and deterministic degraded behavior under API or network stress.
