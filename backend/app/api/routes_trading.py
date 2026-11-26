"""Trade Journal, Backtesting, and Paper Trading routes."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.backtesting.engine import execute_backtest
from app.database.repositories import repo
from app.models.journal import BacktestRequest, PaperTradeOrderRequest
from app.paper_trading.engine import (
    close_paper_trade,
    get_paper_account_summary,
    mark_to_market_open_positions,
    open_paper_trade,
    reset_paper_account,
)

router = APIRouter(prefix="/api", tags=["Journal, Backtesting & Paper Trading"])


# --- Journal ---
@router.get("/journal")
async def list_journal(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    decision: Optional[str] = None,
    pattern: Optional[str] = None,
    outcome: Optional[str] = None,
    min_score: Optional[float] = None,
    limit: int = 200,
):
    entries = await repo.list_journal_entries(limit=limit)
    filtered = []
    for e in entries:
        if symbol and e.symbol.upper() != symbol.upper():
            continue
        if timeframe and e.timeframe.value != timeframe:
            continue
        if decision and e.decision.value != decision:
            continue
        if outcome and e.outcome != outcome:
            continue
        if min_score is not None and e.setup_score < min_score:
            continue
        if pattern and not any(pattern.lower() in p.lower() for p in e.patterns):
            continue
        filtered.append(e.model_dump(mode="json"))
    return filtered


class JournalUpdate(BaseModel):
    outcome: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/journal/{entry_id}")
async def update_journal_entry(entry_id: str, body: JournalUpdate):
    entry = await repo.get_journal_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found.")
    if body.outcome is not None:
        entry.outcome = body.outcome
    if body.notes is not None:
        entry.notes = body.notes
    await repo.save_journal_entry(entry)
    return entry.model_dump(mode="json")


# --- Backtesting ---
@router.post("/backtest/run")
async def run_backtest(req: BacktestRequest):
    try:
        res = await execute_backtest(req)
        return res.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/backtest/history")
async def list_backtests(limit: int = 30):
    items = await repo.list_backtests(limit=limit)
    return [i.model_dump(mode="json") for i in items]


# --- Paper Trading ---
@router.get("/paper/account")
async def paper_account():
    summary = await get_paper_account_summary()
    return summary.model_dump(mode="json")


@router.get("/paper/positions")
async def paper_positions(limit: int = 200):
    positions = await repo.list_paper_trades(limit=limit)
    return [p.model_dump(mode="json") for p in positions]


@router.post("/paper/order")
async def create_paper_order(req: PaperTradeOrderRequest):
    try:
        pos = await open_paper_trade(req)
        return pos.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/paper/close/{trade_id}")
async def close_paper_order(trade_id: str, exit_price: Optional[float] = None):
    try:
        pos = await close_paper_trade(trade_id, exit_price=exit_price)
        return pos.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/paper/sync")
async def sync_paper_positions(allow_demo: bool = False):
    positions = await mark_to_market_open_positions(allow_demo=allow_demo)
    summary = await get_paper_account_summary()
    return {
        "summary": summary.model_dump(mode="json"),
        "positions": [p.model_dump(mode="json") for p in positions],
    }


@router.post("/paper/reset")
async def reset_paper(initial_balance: float = 10000.0):
    summary = await reset_paper_account(initial_balance)
    return summary.model_dump(mode="json")
