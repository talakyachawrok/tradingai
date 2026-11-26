# Testing Guide

## Backend Automated Test Suite
The backend uses `pytest` and `pytest-asyncio` to test mathematical calculations, edge cases, look-ahead bias prevention, risk gates, and FastAPI routes.

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest -v
```

### Covered Test Areas
- **Candlestick Patterns:** Exact OHLC calculations for Bullish/Bearish Engulfing, Hammer, Shooting Star, Doji, Morning/Evening Star, Three White Soldiers, Inside/Outside Bar, Pin Bars.
- **Indicators:** EMA 20/50/200, Wilder RSI 14, ATR 14, MACD line/signal/histogram.
- **Market Structure & Liquidity:** Swing highs/lows, HH/HL/LH/LL labeling, BOS & CHoCH detection, liquidity sweep detection, Fair Value Gaps.
- **Risk & Levels:** Structural + ATR stop-loss placement, TP1/TP2/TP3 targets, R:R rejection, position sizing (including refusal on incomplete specs), rules-based decision gate.
- **Data Integrity:** Corrupted OHLC removal, duplicate timestamp removal, time-gap flagging, stale-feed rejection.
- **Backtesting:** Look-ahead-free replay, conservative intrabar SL-before-TP tie-breaker.
- **Paper Trading & Webhooks:** Risk limit enforcement, P&L calculation, secret verification, deduplication, HTTP 202 acceptance.

## Frontend Typecheck & Production Build
```bash
cd frontend
npx tsc --noEmit
npm run build
```
