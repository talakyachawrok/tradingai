"""Typed repository helpers over DocumentStore for all domain collections."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.database.connection import db_store
from app.models.journal import (
    BacktestResult,
    JournalEntry,
    NotificationItem,
    PaperTradePosition,
    WebhookLogRecord,
)
from app.models.settings import AppUserSettings


COLLECTIONS = {
    "analyses": "analyses",
    "journal": "journal",
    "paper_trades": "paper_trades",
    "paper_account": "paper_account",
    "settings": "user_settings",
    "model_evaluations": "model_evaluations",
    "backtests": "backtests",
    "alerts": "alerts",
    "notifications": "notifications",
    "instruments": "custom_instruments",
    "market_cache": "market_data_cache",
}


class Repository:
    """Domain-level persistence API."""

    @staticmethod
    async def save_settings(settings_obj: AppUserSettings) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await db_store.upsert(
            COLLECTIONS["settings"], "default", settings_obj.model_dump(mode="json"), now
        )

    @staticmethod
    async def get_settings() -> AppUserSettings:
        raw = await db_store.get(COLLECTIONS["settings"], "default")
        if raw:
            return AppUserSettings.model_validate(raw)
        return AppUserSettings()

    @staticmethod
    async def save_analysis(analysis_id: str, payload: Dict[str, Any], created_at: str) -> None:
        await db_store.upsert(COLLECTIONS["analyses"], analysis_id, payload, created_at)

    @staticmethod
    async def get_analysis(analysis_id: str) -> Optional[Dict[str, Any]]:
        return await db_store.get(COLLECTIONS["analyses"], analysis_id)

    @staticmethod
    async def list_analyses(limit: int = 50) -> List[Dict[str, Any]]:
        return await db_store.list_all(COLLECTIONS["analyses"], limit=limit)

    @staticmethod
    async def save_journal_entry(entry: JournalEntry) -> None:
        await db_store.upsert(
            COLLECTIONS["journal"],
            entry.id,
            entry.model_dump(mode="json"),
            entry.created_at.isoformat(),
        )

    @staticmethod
    async def list_journal_entries(limit: int = 200) -> List[JournalEntry]:
        rows = await db_store.list_all(COLLECTIONS["journal"], limit=limit)
        return [JournalEntry.model_validate(r) for r in rows]

    @staticmethod
    async def get_journal_entry(entry_id: str) -> Optional[JournalEntry]:
        raw = await db_store.get(COLLECTIONS["journal"], entry_id)
        return JournalEntry.model_validate(raw) if raw else None

    @staticmethod
    async def save_backtest(result: BacktestResult) -> None:
        await db_store.upsert(
            COLLECTIONS["backtests"],
            result.backtest_id,
            result.model_dump(mode="json"),
            result.created_at.isoformat(),
        )

    @staticmethod
    async def list_backtests(limit: int = 50) -> List[BacktestResult]:
        rows = await db_store.list_all(COLLECTIONS["backtests"], limit=limit)
        return [BacktestResult.model_validate(r) for r in rows]

    @staticmethod
    async def save_paper_trade(position: PaperTradePosition) -> None:
        await db_store.upsert(
            COLLECTIONS["paper_trades"],
            position.trade_id,
            position.model_dump(mode="json"),
            position.opened_at.isoformat(),
        )

    @staticmethod
    async def list_paper_trades(limit: int = 300) -> List[PaperTradePosition]:
        rows = await db_store.list_all(COLLECTIONS["paper_trades"], limit=limit)
        return [PaperTradePosition.model_validate(r) for r in rows]

    @staticmethod
    async def get_paper_account_state() -> Dict[str, Any]:
        raw = await db_store.get(COLLECTIONS["paper_account"], "default")
        if raw:
            return raw
        return {"initial_balance": 10000.0, "balance": 10000.0}

    @staticmethod
    async def save_paper_account_state(state: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await db_store.upsert(COLLECTIONS["paper_account"], "default", state, now)

    @staticmethod
    async def save_webhook_log(log: WebhookLogRecord) -> None:
        await db_store.upsert(
            COLLECTIONS["alerts"],
            log.alert_id,
            log.model_dump(mode="json"),
            log.received_at.isoformat(),
        )

    @staticmethod
    async def list_webhook_logs(limit: int = 100) -> List[WebhookLogRecord]:
        rows = await db_store.list_all(COLLECTIONS["alerts"], limit=limit)
        return [WebhookLogRecord.model_validate(r) for r in rows]

    @staticmethod
    async def save_notification(item: NotificationItem) -> None:
        await db_store.upsert(
            COLLECTIONS["notifications"],
            item.id,
            item.model_dump(mode="json"),
            item.created_at.isoformat(),
        )

    @staticmethod
    async def list_notifications(limit: int = 100) -> List[NotificationItem]:
        rows = await db_store.list_all(COLLECTIONS["notifications"], limit=limit)
        return [NotificationItem.model_validate(r) for r in rows]

    @staticmethod
    async def save_model_evaluation(eval_id: str, payload: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await db_store.upsert(COLLECTIONS["model_evaluations"], eval_id, payload, now)

    @staticmethod
    async def get_latest_model_evaluation() -> Optional[Dict[str, Any]]:
        rows = await db_store.list_all(COLLECTIONS["model_evaluations"], limit=1)
        return rows[0] if rows else None


repo = Repository()
