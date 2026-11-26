# TradingView Webhook & Pine Script Configuration Guide

## Architecture
```text
TradingView Pine Script -> TradingView Alert -> HTTPS POST Webhook -> FastAPI Endpoint (202 Accepted)
  -> Secret Verification + SHA-256 Deduplication -> Async Background Queue -> Quantitative Pipeline -> Dashboard & Notifications
```

Embedded TradingView charts do not transmit private candle data to third-party servers. Instead, TradingView sends webhook alerts directly to `POST /api/webhooks/tradingview`.

## 1. Configure Your Webhook Secret
In `.env`:
```env
TRADINGVIEW_WEBHOOK_SECRET=replace-with-long-random-secret
WEBHOOK_DEDUP_WINDOW_SECONDS=300
```
Restart the backend after editing `.env`.

## 2. Add the Pine Script Indicator
1. Open TradingView -> **Pine Editor**.
2. Paste the contents of [`tradingview/ai_trading_analyzer_alert.pine`](../tradingview/ai_trading_analyzer_alert.pine).
3. Click **Add to chart**.
4. Open indicator settings and set **Webhook Secret Token** to match `TRADINGVIEW_WEBHOOK_SECRET`.

## 3. Create the TradingView Alert
1. Click **Alert** (`Alt+A`) on your TradingView chart.
2. Condition: select `AI Trading Analyzer - Structured Alert Emitter` -> `Any alert() function call`.
3. Notifications tab: enable **Webhook URL** and enter your publicly reachable HTTPS URL, e.g.:
   `https://your-domain.com/api/webhooks/tradingview`
   *(For local development, tunnel port 8000 using ngrok or Cloudflare Tunnel.)*
4. Or if using a custom alert condition without `alert()`, paste [`tradingview/example_alert_payload.json`](../tradingview/example_alert_payload.json) into the **Message** box.

## 4. Timeout & Idempotency Guarantees
- TradingView enforces a strict ~3 second webhook timeout.
- `/api/webhooks/tradingview` validates authentication and payload schema synchronously, records the event, returns `HTTP 202 Accepted` in milliseconds, and executes the full multi-timeframe analysis asynchronously.
- Duplicate payloads arriving within `WEBHOOK_DEDUP_WINDOW_SECONDS` are logged as `duplicate_ignored` and skipped.
