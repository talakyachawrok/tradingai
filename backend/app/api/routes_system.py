"""ML Probability Model, Settings, Notifications, and Health routes."""

import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.config import get_settings
from app.core.instruments import normalize_symbol
from app.data.manager import market_data_manager
from app.database.connection import db_store
from app.database.repositories import repo
from app.ml.features import FEATURE_NAMES
from app.ml.probability import probability_manager
from app.models.market import Timeframe
from app.models.settings import AppUserSettings

router = APIRouter(prefix="/api", tags=["System, ML & Settings"])


@router.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "database": {
            "backend": db_store.backend_type,
            "connected": db_store.connected,
            "message": db_store.status_message,
        },
        "config": settings.safe_public_status(),
        "ml_model_available": probability_manager.model_available,
        "ml_model_validated": probability_manager.validated,
        "ml_is_experimental": probability_manager.is_experimental,
    }


@router.get("/settings")
async def get_user_settings():
    user_settings = await repo.get_settings()
    env_status = get_settings().safe_public_status()
    return {
        "user_settings": user_settings.model_dump(mode="json"),
        "environment": env_status,
        "database": {
            "backend": db_store.backend_type,
            "connected": db_store.connected,
            "message": db_store.status_message,
        },
    }


@router.put("/settings")
async def update_user_settings(body: AppUserSettings):
    await repo.save_settings(body)
    return {"saved": True, "user_settings": body.model_dump(mode="json")}


# --- ML Probability Model ---
@router.get("/ml/status")
async def ml_status():
    latest = await repo.get_latest_model_evaluation()
    return {
        "current_runtime": probability_manager.evaluation_report,
        "last_persisted_evaluation": latest,
        "artifact_loaded": probability_manager.model_available,
        "is_experimental": probability_manager.is_experimental,
        "feature_count": len(FEATURE_NAMES),
        "feature_names": FEATURE_NAMES,
    }


class TrainMLRequest(BaseModel):
    symbol: str = "BTCUSD"
    timeframe: Timeframe = Timeframe.H1
    model_type: str = "logistic_regression"  # logistic_regression, random_forest, gradient_boosting
    horizon_bars: int = 24
    allow_demo: bool = False


@router.post("/ml/train")
async def train_ml_model(req: TrainMLRequest):
    settings = await repo.get_settings()
    norm_symbol = normalize_symbol(req.symbol)
    resp = await market_data_manager.get_market_data(
        symbol=norm_symbol,
        timeframe=req.timeframe,
        provider_override=settings.data_provider,
        limit=1000,
        allow_demo=req.allow_demo,
    )
    if len(resp.candles) < 150:
        raise HTTPException(
            status_code=422,
            detail=resp.overview.status_message
            or f"Need at least 150 candles to train and chronologically validate model (found {len(resp.candles)}).",
        )
    report = probability_manager.train_and_validate(
        candles=resp.candles,
        symbol=norm_symbol,
        timeframe=req.timeframe,
        model_type=req.model_type,
        horizon_bars=req.horizon_bars,
        is_demo=resp.overview.is_demo,
        data_source=resp.overview.data_source,
        save_artifact=False,
    )
    if not report.get("validated"):
        raise HTTPException(
            status_code=422,
            detail=report.get("error") or "Model validation failed for this dataset.",
        )
    report["data_source"] = resp.overview.data_source
    report["is_demo"] = resp.overview.is_demo
    await repo.save_model_evaluation(str(uuid.uuid4()), report)
    return report


# --- Notifications ---
@router.get("/notifications")
async def list_notifications(limit: int = 50):
    items = await repo.list_notifications(limit=limit)
    return [n.model_dump(mode="json") for n in items]


@router.post("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str):
    items = await repo.list_notifications(limit=200)
    target = next((n for n in items if n.id == notif_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Notification not found.")
    target.read = True
    await repo.save_notification(target)
    return {"read": True, "id": notif_id}


@router.post("/notifications/read-all")
async def mark_all_notifications_read():
    items = await repo.list_notifications(limit=200)
    for n in items:
        if not n.read:
            n.read = True
            await repo.save_notification(n)
    return {"marked": len(items)}
