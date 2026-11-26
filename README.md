# AI Trading Analyzer

**AI Trading Analyzer** is a full-stack quantitative market analysis, backtesting, paper-trading, and TradingView webhook intelligence platform.

It combines deterministic OHLCV quantitative engines (candlestick patterns, market structure BOS/CHoCH, liquidity & Fair Value Gaps, technical indicators, multi-timeframe alignment, risk-adjusted SL/TP planning, and look-ahead-free backtesting) with an optional grounded AI explanation layer and a strictly validated ML probability lab.

---

## Key Safeguards & Design Principles

- **Never fakes live prices:** When live API credentials are missing or unreachable, the UI explicitly displays `DATA_UNAVAILABLE` or requires opting into `Demo Historical Mode` (static historical dataset ending 2026-02-15 UTC).
- **Never forces trades:** The deterministic eligibility engine evaluates `BUY SETUP`, `SELL SETUP`, `WAIT`, or `NO VALID SETUP`. Conflicting timeframes, low R:R, stale feeds, or breached risk limits automatically reject setups.
- **Score ≠ Probability:** Setup quality scores (0–100) are transparent weighted heuristics. Win probability is isolated in the ML Probability Lab and displays `PROBABILITY MODEL NOT YET VALIDATED` until trained and validated chronologically.
- **Simulated Paper Trading Only:** Never transmits real-money orders.

---

## Project Structure

```text
AI-Trading-Analyzer/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI REST & WebSocket endpoints
│   │   ├── core/           # Config & instrument contract registry
│   │   ├── data/           # Market data providers & OHLCV validator
│   │   ├── patterns/       # 21+ OHLC candlestick pattern detectors
│   │   ├── structure/      # Swing HH/HL/LH/LL, BOS, CHoCH, regime
│   │   ├── indicators/     # EMA 20/50/200, RSI, ATR, MACD, Volume
│   │   ├── analysis/       # Liquidity/FVG, MTF, scoring, decision, AI explanation
│   │   ├── risk/           # Entry/SL/TP engine & position sizer
│   │   ├── ml/             # Chronological walk-forward probability model
│   │   ├── backtesting/    # Look-ahead-free historical simulator
│   │   ├── paper_trading/  # Virtual portfolio & risk limit enforcer
│   │   ├── webhooks/       # TradingView alert auth, dedup & async queue
│   │   ├── database/       # MongoDB + local SQLite document store
│   │   └── services/       # Notifications & UTC session/news calendar
│   └── tests/              # Comprehensive pytest calculation & API suite
├── frontend/               # React + TypeScript + Vite + Tailwind + Lightweight Charts
├── tradingview/            # Pine Script v5 alert script & JSON payload template
├── scripts/                # Local dev launcher scripts
└── docs/                   # Setup, API, Webhook, Testing & Deployment guides
```

---

## Quick Start (Local Development)

### 1. Environment Setup
```bash
cp .env.example .env
# Edit .env to add optional TwelveData, AlphaVantage, Finnhub, OpenAI/Gemini/Anthropic, or MongoDB settings.
```

### 2. Backend Setup (Python 3.11+)
```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend Setup (Node.js 20+)
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`.

### 4. Run Tests
```bash
cd backend
.\.venv\Scripts\python.exe -m pytest -v
```

---

## Documentation Guides

- [API & Provider Configuration](docs/API_CONFIGURATION.md)
- [TradingView Webhook & Pine Script Guide](docs/TRADINGVIEW_WEBHOOK_SETUP.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Testing Guide](docs/TESTING.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md)
