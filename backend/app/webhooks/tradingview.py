"""TradingView webhook validation, deduplication, and asynchronous background processing."""

import asyncio
import hashlib
import hmac
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional
from app.analysis.pipeline import run_full_analysis
from app.core.config import get_settings
from app.core.instruments import normalize_symbol
from app.data.providers.webhook_cache import webhook_cache_provider
from app.database.repositories import repo
from app.models.journal import NotificationItem, TradingViewAlertPayload, WebhookLogRecord
from app.models.market import Timeframe


TIMEFRAME_ALIAS: Dict[str, Timeframe] = {
    "1": Timeframe.M1,
    "1m": Timeframe.M1,
    "3": Timeframe.M3,
    "3m": Timeframe.M3,
    "5": Timeframe.M5,
    "5m": Timeframe.M5,
    "15": Timeframe.M15,
    "15m": Timeframe.M15,
    "30": Timeframe.M30,
    "30m": Timeframe.M30,
    "60": Timeframe.H1,
    "1h": Timeframe.H1,
    "240": Timeframe.H4,
    "4h": Timeframe.H4,
    "d": Timeframe.D1,
    "1d": Timeframe.D1,
    "daily": Timeframe.D1,
}


class WebhookProcessor:
    """Fast, idempotent TradingView webhook handler with background async queue."""

    def __init__(self) -> None:
        self._recent_hashes: Dict[str, float] = {}
        self._active_tasks: set[asyncio.Task] = set()

    @staticmethod
    def map_timeframe(raw_tf: str) -> Timeframe:
        cleaned = raw_tf.strip().lower()
        return TIMEFRAME_ALIAS.get(cleaned, Timeframe.H1)

    @staticmethod
    def compute_dedup_hash(payload: TradingViewAlertPayload) -> str:
        norm = normalize_symbol(payload.symbol)
        price_val = payload.close or payload.price or ""
        ts_val = payload.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        raw = f"{norm}|{payload.timeframe.lower()}|{payload.event.lower()}|{ts_val}|{price_val}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def verify_secret(self, header_secret: Optional[str], payload_secret: Optional[str]) -> bool:
        settings = get_settings()
        expected = settings.tradingview_webhook_secret.strip()
        provided = (header_secret or payload_secret or "").strip()
        if not expected or not provided:
            return False
        return hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))

    def is_duplicate(self, dedup_hash: str) -> bool:
        now_ts = time.monotonic()
        window = get_settings().webhook_dedup_window_seconds
        expired = [k for k, ts in self._recent_hashes.items() if now_ts - ts > window]
        for k in expired:
            self._recent_hashes.pop(k, None)
        if dedup_hash in self._recent_hashes:
            return True
        self._recent_hashes[dedup_hash] = now_ts
        return False

    async def handle_alert(
        self, payload: TradingViewAlertPayload, header_secret: Optional[str] = None
    ) -> WebhookLogRecord:
        now = datetime.now(timezone.utc)
        alert_id = str(uuid.uuid4())
        norm_symbol = normalize_symbol(payload.symbol)
        tf = self.map_timeframe(payload.timeframe)
        dedup_hash = self.compute_dedup_hash(payload)

        if not self.verify_secret(header_secret, payload.secret):
            rec = WebhookLogRecord(
                alert_id=alert_id,
                received_at=now,
                dedup_hash=dedup_hash,
                symbol=norm_symbol,
                timeframe=tf.value,
                event=payload.event,
                status="rejected_auth",
                message="Invalid or missing webhook secret.",
            )
            await repo.save_webhook_log(rec)
            return rec

        if self.is_duplicate(dedup_hash):
            rec = WebhookLogRecord(
                alert_id=alert_id,
                received_at=now,
                dedup_hash=dedup_hash,
                symbol=norm_symbol,
                timeframe=tf.value,
                event=payload.event,
                status="duplicate_ignored",
                message="Duplicate alert ignored within deduplication window.",
            )
            await repo.save_webhook_log(rec)
            return rec

        # If TradingView sent OHLC bar data, cache it for analysis
        close_px = payload.close or payload.price
        if close_px and close_px > 0:
            open_px = payload.open or close_px
            high_px = max(payload.high or close_px, open_px, close_px)
            low_px = min(payload.low or close_px, open_px, close_px)
            webhook_cache_provider.push_candles(
                norm_symbol,
                tf,
                [
                    {
                        "timestamp": payload.timestamp or now.isoformat(),
                        "open": open_px,
                        "high": high_px,
                        "low": low_px,
                        "close": close_px,
                        "volume": payload.volume,
                    }
                ],
                replace=False,
            )

        rec = WebhookLogRecord(
            alert_id=alert_id,
            received_at=now,
            dedup_hash=dedup_hash,
            symbol=norm_symbol,
            timeframe=tf.value,
            event=payload.event,
            status="queued",
            message="Alert validated and queued for asynchronous analysis.",
        )
        await repo.save_webhook_log(rec)
        await repo.save_notification(
            NotificationItem(
                id=str(uuid.uuid4()),
                created_at=now,
                category="webhook",
                severity="info",
                title=f"TradingView Alert: {norm_symbol} ({tf.value})",
                message=f"Event '{payload.event}' queued for background analysis.",
                metadata={"alert_id": alert_id},
            )
        )

        # Respond quickly to TradingView (<3s timeout) and process asynchronously
        task = asyncio.create_task(self._process_async(rec, norm_symbol, tf))
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)
        return rec

    async def _process_async(self, rec: WebhookLogRecord, symbol: str, tf: Timeframe) -> None:
        try:
            report = await run_full_analysis(symbol=symbol, timeframe=tf, allow_demo=False)
            rec.status = "processed"
            rec.analysis_id = report.analysis_id
            rec.message = f"Completed: {report.final_decision.value} (score {report.setup_score.total_score}/100)."
        except Exception as exc:
            rec.status = "processed_no_data"
            rec.message = f"Alert logged; full analysis skipped ({exc})."
        await repo.save_webhook_log(rec)


webhook_processor = WebhookProcessor()
