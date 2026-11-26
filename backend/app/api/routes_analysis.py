"""Analysis execution, history, and position-sizing routes."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.analysis.pipeline import run_full_analysis
from app.database.repositories import repo
from app.models.analysis import PositionSizeRequest
from app.models.market import Timeframe
from app.paper_trading.engine import get_paper_account_summary
from app.risk.position_sizing import calculate_position_size
from app.services.news_session import get_sessions_and_news

router = APIRouter(prefix="/api/analysis", tags=["Analysis"])


class AnalyzeMarketRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: Timeframe = Timeframe.H1
    provider: Optional[str] = None
    allow_demo: bool = False


@router.post("/run")
async def analyze_market(req: AnalyzeMarketRequest):
    paper_summary = await get_paper_account_summary()
    news_info = await get_sessions_and_news(req.symbol)
    try:
        report = await run_full_analysis(
            symbol=req.symbol,
            timeframe=req.timeframe,
            provider_override=req.provider,
            allow_demo=req.allow_demo,
            paper_account=paper_summary,
            news_blackout_active=bool(news_info.get("blackout_active")),
            news_blackout_reason=str(news_info.get("blackout_reason", "")),
        )
        return report.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/history")
async def list_analyses(limit: int = 30):
    return await repo.list_analyses(limit=limit)


@router.get("/{analysis_id}")
async def get_analysis(analysis_id: str):
    doc = await repo.get_analysis(analysis_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis report not found.")
    return doc


@router.post("/position-size")
async def compute_position_size(req: PositionSizeRequest):
    res = calculate_position_size(req)
    return res.model_dump(mode="json")
