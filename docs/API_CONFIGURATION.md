# API & Provider Configuration Guide

All secrets must live in `.env` (never in frontend files or git commits).

## Market Data Providers

| Provider | Symbols | Timeframes | Credentials | Notes |
| --- | --- | --- | --- | --- |
| `twelvedata` | XAUUSD, EURUSD, GBPUSD, BTCUSD, custom | 1m, 5m, 15m, 30m, 1h, 4h, 1d | `TWELVEDATA_API_KEY` | 3m is unavailable natively |
| `alphavantage` | EURUSD, GBPUSD, XAUUSD, BTCUSD | 1m, 5m, 15m, 30m, 1h, 1d | `ALPHAVANTAGE_API_KEY` | 3m and 4h unavailable natively |
| `binance_public` | BTCUSD (`BTCUSDT`) | All (`1m`..`1d`) | None required | Uses public Binance Spot REST API |
| `webhook_cache` | Any | Any | `TRADINGVIEW_WEBHOOK_SECRET` | Populated via TradingView alerts or CSV upload |
| `demo_historical` | XAUUSD, EURUSD, GBPUSD, BTCUSD | All | None | Static offline historical sample ending 2026-02-15 UTC |

## Optional AI Explanation Providers
The quantitative rules engine **always** computes setup scores, SL/TP, and eligibility decisions. Set `AI_PROVIDER` in `.env` to enrich prose explanations:
- `AI_PROVIDER=none` (default): Deterministic grounded template narrative.
- `AI_PROVIDER=openai` + `OPENAI_API_KEY`
- `AI_PROVIDER=gemini` + `GEMINI_API_KEY`
- `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`
- `AI_PROVIDER=ollama` + `OLLAMA_BASE_URL`

## Optional Economic News Calendar
Set `NEWS_PROVIDER=finnhub` and `FINNHUB_API_KEY` in `.env`. Without this key, the News module explicitly displays `UNAVAILABLE` and never invents events.

## Database Configuration
- **MongoDB (recommended for production):** Set `MONGODB_URI=mongodb://localhost:27017` and `MONGODB_DB_NAME=ai_trading_analyzer`.
- **Automatic Local Fallback:** If `MONGODB_URI` is blank or unreachable, the backend stores documents persistently in SQLite at `LOCAL_DB_PATH` (`./data/ai_trading_analyzer.db`) and reports the active backend on `/api/health` and the Settings page.
