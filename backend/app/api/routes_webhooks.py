"""TradingView webhook ingestion, logs, and status routes."""

from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status
from app.core.config import get_settings
from app.database.repositories import repo
from app.models.journal import TradingViewAlertPayload
from app.webhooks.tradingview import webhook_processor

router = APIRouter(prefix="/api/webhooks", tags=["TradingView Webhooks"])


@router.post("/tradingview", status_code=status.HTTP_202_ACCEPTED)
async def receive_tradingview_alert(
    payload: TradingViewAlertPayload,
    x_webhook_secret: Optional[str] = Header(default=None),
):
    rec = await webhook_processor.handle_alert(payload, header_secret=x_webhook_secret)
    if rec.status == "rejected_auth":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=rec.message)
    return {
        "accepted": True,
        "alert_id": rec.alert_id,
        "status": rec.status,
        "message": rec.message,
        "symbol": rec.symbol,
        "timeframe": rec.timeframe,
    }


@router.get("/logs")
async def get_webhook_logs(limit: int = 50):
    logs = await repo.list_webhook_logs(limit=limit)
    return [log.model_dump(mode="json") for log in logs]


@router.get("/status")
async def webhook_status():
    settings = get_settings()
    logs = await repo.list_webhook_logs(limit=10)
    return {
        "endpoint": "/api/webhooks/tradingview",
        "secret_configured": settings.safe_public_status()["webhook_secret_configured"],
        "dedup_window_seconds": settings.webhook_dedup_window_seconds,
        "recent_alerts_count": len(logs),
        "last_received_at": logs[0].received_at.isoformat() if logs else None,
    }
