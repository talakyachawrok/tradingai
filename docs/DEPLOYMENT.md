# Deployment Guide

## Option 1: Docker Compose (Backend + Frontend + MongoDB)
1. Copy environment variables:
   ```bash
   cp .env.example .env
   ```
2. Update `TRADINGVIEW_WEBHOOK_SECRET` and any market-data / AI keys in `.env`.
3. Build and start all services:
   ```bash
   docker compose up -d --build
   ```
4. Access the application:
   - Frontend UI: `http://localhost:5173`
   - Backend API & Swagger Docs: `http://localhost:8000/docs`
   - MongoDB: `mongodb://localhost:27017`

## Option 2: Local Windows / Linux Process Deployment
- Backend:
  ```bash
  cd backend
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
  ```
- Frontend production build:
  ```bash
  cd frontend
  npm run build
  ```
  Serve `frontend/dist` behind Nginx, Caddy, or a CDN and proxy `/api` and `/ws` to port `8000`.

## Production Checklist
- Use HTTPS (TLS) in front of `/api/webhooks/tradingview` so TradingView webhooks stay encrypted and accepted.
- Set `CORS_ORIGINS` strictly to your frontend origin.
- Rotate `TRADINGVIEW_WEBHOOK_SECRET` before enabling live TradingView alerts.
