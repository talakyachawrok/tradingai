"""FastAPI application entrypoint, lifespan, CORS, and WebSocket stream."""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.api import (
    routes_analysis,
    routes_market,
    routes_system,
    routes_trading,
    routes_webhooks,
)
from app.core.config import get_settings
from app.data.manager import market_data_manager
from app.database.connection import db_store
from app.models.market import Timeframe


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db_store.initialize()
    yield
    await db_store.close()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Full-stack quantitative & AI-assisted trading analysis platform.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_market.router)
app.include_router(routes_analysis.router)
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
