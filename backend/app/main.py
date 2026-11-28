"""FastAPI application entrypoint, lifespan, CORS, health check, and WebSocket stream."""

import asyncio
import os
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api import (
    routes_analysis,
    routes_market,
    routes_signals,
    routes_system,
    routes_trading,
    routes_webhooks,
)
from app.core.config import get_settings
from app.core.logging_config import logger
from app.data.manager import market_data_manager
from app.database.connection import db_store
from app.ml.probability import probability_manager
from app.models.market import Timeframe


@asynccontextmanager
async def lifespan(_app: FastAPI):
    cfg = get_settings()
    await db_store.initialize()
    if not probability_manager.model_available:
        probability_manager.load_saved_model()
    logger.info(
        "ML Probability Engine status: available=%s validated=%s experimental=%s model=%s trained_on=%s",
        probability_manager.model_available,
        probability_manager.validated,
        probability_manager.is_experimental,
        probability_manager.model_name,
        probability_manager.trained_on,
    )
    logger.info(
        "Starting %s (env=%s, storage=%s, cors_origins=%s)",
        cfg.app_name,
        cfg.app_env,
        db_store.backend_type,
        cfg.cors_origin_list,
    )
    if not cfg.twelvedata_api_key.strip():
        logger.warning(
            "TWELVEDATA_API_KEY is not set; XAUUSD/EURUSD/GBPUSD live feeds will report DATA_UNAVAILABLE until configured."
        )
    if cfg.app_env.lower() == "production" and not cfg.frontend_url.strip():
        logger.warning(
            "FRONTEND_URL is not set in production; ensure CORS_ORIGINS includes your Vercel URL."
        )
    yield
    await db_store.close()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Quantitative & AI-assisted trading analysis API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled server error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error while processing request."},
    )


@app.get("/health", tags=["Health"])
async def root_health():
    """Lightweight Render health-check endpoint."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "storage": "ephemeral_in_memory",
    }


app.include_router(routes_market.router)
app.include_router(routes_analysis.router)
app.include_router(routes_signals.router)
app.include_router(routes_webhooks.router)
app.include_router(routes_trading.router)
app.include_router(routes_system.router)


@app.websocket("/ws/market")
async def market_ws(websocket: WebSocket, symbol: str = "BTCUSD", timeframe: str = "1m", allow_demo: bool = False):
    """Push periodic real market snapshot updates without fabricating prices."""
    await websocket.accept()
    try:
        tf = Timeframe(timeframe)
    except ValueError:
        tf = Timeframe.M1
    try:
        while True:
            resp = await market_data_manager.get_market_data(
                symbol=symbol, timeframe=tf, limit=100, allow_demo=allow_demo
            )
            await websocket.send_json(
                {
                    "type": "market_snapshot",
                    "overview": resp.overview.model_dump(mode="json"),
                    "latest_candle": resp.candles[-1].model_dump(mode="json") if resp.candles else None,
                }
            )
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        return


if __name__ == "__main__":
    port = int(os.getenv("PORT", str(settings.app_port)))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
