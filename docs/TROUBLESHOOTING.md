# Troubleshooting Guide

### 1. Dashboard shows `DATA_UNAVAILABLE`
- **Cause:** No live API key is configured for Forex/Metals (`TWELVEDATA_API_KEY` or `ALPHAVANTAGE_API_KEY`), or the machine has no internet access to reach Binance Public API for `BTCUSD`.
- **Resolution:** Add a provider key in `.env` and restart the backend, upload an OHLCV `.csv` file via **Upload OHLC CSV**, or check **Demo Historical Mode** to inspect the analytical pipeline with static sample candles.

### 2. "ANALYZE MARKET" returns an error
- **Cause:** Fewer than 30 valid candles loaded, or the feed is stale beyond `STALE_DATA_THRESHOLD_SECONDS`.
- **Resolution:** Ensure valid OHLC data is loaded or adjust `STALE_DATA_THRESHOLD_SECONDS` for delayed feeds.

### 3. TradingView Webhook returns `401 Unauthorized`
- **Cause:** The `secret` in the JSON payload or `X-Webhook-Secret` header does not match `TRADINGVIEW_WEBHOOK_SECRET` in `.env`.

### 4. ML Probability Card displays `PROBABILITY MODEL NOT YET VALIDATED`
- **Intentional safeguard:** Probability estimates are withheld until you open **Probability Lab**, select >=120 historical candles, and run **Train & Validate** using chronological train/val/test splits.

### 5. Position Size Calculator warns about missing instrument specs
- **Intentional safeguard:** Custom symbols added without `contract_size`, `tick_size`, and `tick_value_per_lot` will not guess lot sizes. Update the instrument's contract specifications via `POST /api/market/instruments`.
