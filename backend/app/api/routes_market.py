"""Market data, instruments, CSV upload, and sessions/news routes."""

from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from app.core.instruments import InstrumentSpec, instrument_registry
from app.data.manager import market_data_manager
from app.indicators.engine import evaluate_indicators
from app.models.market import Timeframe
from app.services.news_session import get_sessions_and_news

router = APIRouter(prefix="/api/market", tags=["Market Data"])


@router.get("/instruments")
async def list_instruments():
    return [inst.model_dump(mode="json") for inst in instrument_registry.list_instruments()]


@router.post("/instruments")
async def add_or_update_instrument(spec: InstrumentSpec):
    saved = instrument_registry.add_or_update(spec)
    return saved.model_dump(mode="json")


@router.delete("/instruments/{symbol}")
async def remove_instrument(symbol: str):
    ok = instrument_registry.remove_custom(symbol)
    if not ok:
        raise HTTPException(status_code=400, detail="Default instruments cannot be deleted or symbol not found.")
    return {"deleted": True, "symbol": symbol.upper()}


@router.get("/providers")
async def list_providers():
    return [cap.model_dump(mode="json") for cap in market_data_manager.list_provider_capabilities()]


@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str = "XAUUSD",
    timeframe: Timeframe = Timeframe.H1,
    provider: Optional[str] = None,
    limit: int = 300,
    allow_demo: bool = False,
):
    resp = await market_data_manager.get_market_data(
        symbol=symbol,
        timeframe=timeframe,
        provider_override=provider,
        limit=limit,
        allow_demo=allow_demo,
    )
    ind_snap, overlays = evaluate_indicators(resp.candles)
    return {
        **resp.model_dump(mode="json"),
        "indicators": ind_snap.model_dump(mode="json"),
        "overlays": overlays.model_dump(mode="json"),
    }


@router.post("/upload-csv")
async def upload_csv(
    symbol: str = Form(...),
    timeframe: Timeframe = Form(Timeframe.H1),
    file: UploadFile = File(...),
):
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")
    try:
        count = market_data_manager.ingest_csv(symbol, timeframe, text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV OHLCV format: {exc}") from exc
    if count == 0:
        raise HTTPException(status_code=400, detail="No valid OHLC rows parsed from CSV.")
    return {"symbol": symbol.upper(), "timeframe": timeframe.value, "candles_loaded": count}


@router.get("/sessions-news")
async def sessions_and_news(symbol: str = "XAUUSD"):
    return await get_sessions_and_news(symbol)
