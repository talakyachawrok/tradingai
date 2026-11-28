# Render Deployment Guide — AI Trading Analyzer Backend

This guide walks through deploying the **AI Trading Analyzer** FastAPI backend (`backend/`) to **Render** with ephemeral in-memory processing (no MongoDB or external database required) and connecting it to your frontend (e.g., hosted on Vercel).

---

## 1. GitHub Preparation

1. Verify `.env` is ignored in `.gitignore` and **never** commit real API keys or secrets.
2. Verify `.env.example` contains placeholder values only.
3. Push your repository to GitHub:
   ```bash
   git status
   git add .
   git commit -m "Prepare backend for Render deployment"
   git push origin main
   ```

---

## 2. Create the Render Web Service

1. Sign in to [Render](https://render.com) and click **New + -> Web Service**.
2. Connect your GitHub repository (`talakyachawrok/tradingai` or your repo).
3. Configure the service settings:
   - **Name:** `ai-trading-analyzer-api` (or your preference)
   - **Region:** Choose nearest region to your users / market data API
   - **Branch:** `main`
   - **Root Directory:** `backend`
   - **Runtime:** `Python 3`
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command:**
     ```bash
     uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Health Check Path:** `/health`

*(Render automatically injects `$PORT`; do not hardcode port `8000` in the start command.)*

---

## 3. Environment Variables Required on Render

In the Render service dashboard under **Environment -> Environment Variables**, add:

| Variable | Value / Example | Required? | Notes |
| --- | --- | --- | --- |
| `APP_ENV` | `production` | Recommended | Disables wildcard `*` CORS origins |
| `FRONTEND_URL` | `https://your-frontend.vercel.app` | **Yes (for Vercel)** | Exact Vercel origin without trailing slash |
| `CORS_ORIGINS` | `https://your-frontend.vercel.app` | Optional | Comma-separated extra allowed origins |
| `TWELVEDATA_API_KEY` | `your_twelvedata_key` | Recommended | Required for live `XAUUSD`, `EURUSD`, `GBPUSD` data |
| `DEFAULT_DATA_PROVIDER` | `auto` | Optional | Uses TwelveData / Binance Public automatically |
| `MARKET_DATA_CACHE_TTL_SECONDS` | `30` | Optional | Reduces API credit usage |
| `STALE_DATA_THRESHOLD_SECONDS` | `900` | Optional | Freshness threshold in seconds |
| `ALPHAVANTAGE_API_KEY` | `your_alphavantage_key` | Optional | Secondary FX provider |
| `FINNHUB_API_KEY` | `your_finnhub_key` | Optional | Economic calendar (set `NEWS_PROVIDER=finnhub` if used) |
| `AI_PROVIDER` | `none` (or `openai`/`gemini`/`anthropic`) | Optional | Set matching API key if using LLM narration |
| `TRADINGVIEW_WEBHOOK_SECRET` | `long-random-secret` | Optional | Needed only if receiving TradingView alerts |

> Note: `PORT` is supplied automatically by Render. No `MONGODB_URI` or database URL is needed—all analysis, signals, and runtime state operate ephemerally in memory.

---

## 4. Health Check Verification

Once deployed, Render gives you a service URL such as `https://ai-trading-analyzer-api.onrender.com`.

Test the health-check endpoint in your browser or with `curl`:
```bash
curl https://ai-trading-analyzer-api.onrender.com/health
```
Expected response:
```json
{
  "status": "ok",
  "service": "AI Trading Analyzer",
  "environment": "production",
  "storage": "ephemeral_in_memory"
}
```

You can also verify `/api/health`:
```bash
curl https://ai-trading-analyzer-api.onrender.com/api/health
```

---

## 5. Connect Your Frontend (Vercel)

1. Open your frontend project settings on **Vercel -> Settings -> Environment Variables**.
2. Add:
   - **Name:** `VITE_API_URL`
   - **Value:** `https://ai-trading-analyzer-api.onrender.com` *(your actual Render URL, no trailing slash)*
   - *(Note: `frontend/src/services/api.ts` supports both `VITE_API_URL` and `VITE_API_BASE_URL`.)*
3. Redeploy your Vercel frontend so Vite embeds `VITE_API_URL` during the build.
4. Make sure your Render `FRONTEND_URL` variable matches your exact Vercel domain (e.g. `https://your-app.vercel.app`) so CORS allows browser requests.
5. In the live dashboard, go to **Settings & Risk** and click **Test API Connection** on `twelvedata` (for `XAUUSD`) or `binance_public` (for `BTCUSD`).

---

## 6. Redeploying After Code Changes

1. Commit and push changes to GitHub:
   ```bash
   git add .
   git commit -m "Update analyzer backend"
   git push origin main
   ```
2. By default, Render's **Auto-Deploy** triggers automatically on every push to `main`.
3. If Auto-Deploy is disabled, click **Manual Deploy -> Deploy latest commit** in the Render dashboard.
