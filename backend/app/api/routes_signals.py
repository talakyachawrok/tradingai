"""Trade Signals, Signal History, and Signal Market-Tracking API routes."""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from app.database.repositories import repo
from app.services.signals import track_active_signals

router = APIRouter(prefix="/api/signals", tags=["Trade Signals"])


@router.get("")
async def list_signals(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    direction: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 200,
):
    items = await repo.list_signals(limit=limit)
    out = []
    dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
    dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None

    for s in items:
        if symbol and s.symbol.upper() != symbol.upper():
            continue
        if timeframe and s.timeframe.value != timeframe:
            continue
        if direction and s.direction.upper() != direction.upper():
            continue
        if status and s.status.value != status:
            continue
        if dt_from and s.created_at < dt_from:
            continue
        if dt_to and s.created_at > dt_to:
            continue
        out.append(s.model_dump(mode="json"))
    return out


@router.get("/latest")
async def get_latest_signal(symbol: Optional[str] = None, timeframe: Optional[str] = None):
    items = await repo.list_signals(limit=50)
    for s in items:
        if symbol and s.symbol.upper() != symbol.upper():
            continue
        if timeframe and s.timeframe.value != timeframe:
            continue
        return s.model_dump(mode="json")
    return None


@router.post("/track")
async def sync_signal_tracking(allow_demo: bool = False):
    updated = await track_active_signals(allow_demo=allow_demo)
    return [s.model_dump(mode="json") for s in updated]


@router.get("/{signal_id}")
async def get_signal(signal_id: str):
    sig = await repo.get_signal(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found.")
    return sig.model_dump(mode="json")
