"""Signal persistence, deduplication, non-repainting, expiry, and market tracking service."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from app.core.instruments import instrument_registry, normalize_symbol
from app.data.manager import market_data_manager
from app.database.repositories import repo
from app.models.analysis import (
    BeginnerExplanation,
    DecisionType,
    PatternStory,
    SignalStatus,
    SignalTrackingState,
    SimpleTradePlan,
    TradeAnalysisReport,
    TradeSignalRecord,
)
from app.models.journal import NotificationItem
from app.models.market import TIMEFRAME_SECONDS, OHLCVCandle, Timeframe
from app.models.settings import AppUserSettings


def compute_signal_expiry(
    candle_ts: datetime,
    timeframe: Timeframe,
    expiry_candles: int,
    expiry_minutes: int,
    reference_now: Optional[datetime] = None,
) -> datetime:
    """Compute conservative expiry timestamp from candle interval count or configured minutes."""
    now = reference_now or datetime.now(timezone.utc)
    tf_seconds = TIMEFRAME_SECONDS[timeframe] * max(1, expiry_candles)
    base = max(candle_ts, now)
    return base + timedelta(seconds=min(tf_seconds, expiry_minutes * 60) if expiry_minutes > 0 else tf_seconds)


async def _should_emit_signal_notification(
    symbol: str,
    timeframe: Timeframe,
    direction: str,
    settings: AppUserSettings,
    now: datetime,
) -> bool:
    if not settings.notifications_enabled:
        return False
    if direction == "BUY" and not settings.alerts.enable_buy_alerts:
        return False
    if direction == "SELL" and not settings.alerts.enable_sell_alerts:
        return False
    if settings.alerts.selected_symbols and symbol not in [
        normalize_symbol(s) for s in settings.alerts.selected_symbols
    ]:
        return False
    if settings.alerts.selected_timeframes and timeframe not in settings.alerts.selected_timeframes:
        return False

    cooldown = settings.alerts.alert_cooldown_minutes
    if cooldown > 0:
        recent_notifs = await repo.list_notifications(limit=30)
        cutoff = now - timedelta(minutes=cooldown)
        for n in recent_notifs:
            if (
                n.category == "trade_signal"
                and n.created_at >= cutoff
                and n.metadata.get("symbol") == symbol
                and n.metadata.get("timeframe") == timeframe.value
                and n.metadata.get("direction") == direction
            ):
                return False
    return True


async def record_signal_from_report(
    report: TradeAnalysisReport,
    signal_status: SignalStatus,
    beginner_exp: BeginnerExplanation,
    pattern_story: PatternStory,
    simple_plan: SimpleTradePlan,
    settings: AppUserSettings,
) -> TradeSignalRecord:
    """
    Persist a non-repainting signal record.
    If an identical candle+direction signal already exists, return the existing signal
    without repainting its entry/SL/TP or firing duplicate alerts.
    """
    direction = (
        "BUY"
        if signal_status == SignalStatus.BUY_SIGNAL
        else (
            "SELL"
            if signal_status == SignalStatus.SELL_SIGNAL
            else ("WAIT" if signal_status in (SignalStatus.WAIT_FOR_CONFIRMATION, SignalStatus.SETUP_FORMING) else "NONE")
        )
    )
    dedup_key = f"{report.symbol}|{report.timeframe.value}|{report.data_timestamp.isoformat()}|{direction}"
    existing = await repo.find_signal_by_dedup_key(dedup_key)
    if existing is not None:
        return existing

    now = report.created_at
    expires_at = compute_signal_expiry(
        candle_ts=report.data_timestamp,
        timeframe=report.timeframe,
        expiry_candles=settings.alerts.signal_expiry_candles,
        expiry_minutes=settings.alerts.signal_expiry_minutes,
        reference_now=now,
    )

    spec = instrument_registry.get(report.symbol)
    decimals = spec.decimals if spec else 5
    fmt = lambda v: f"{v:.{decimals}f}" if v is not None else "N/A"

    sig = TradeSignalRecord(
        signal_id=str(uuid.uuid4()),
        dedup_key=dedup_key,
        analysis_id=report.analysis_id,
        created_at=now,
        candle_timestamp=report.data_timestamp,
        expires_at=expires_at,
        symbol=report.symbol,
        timeframe=report.timeframe,
        provider=report.provider,
        connection_status=report.connection_status,
        is_demo=report.is_demo,
        direction=direction,
        status=signal_status,
        entry_price=report.trade_levels.entry_price,
        entry_zone_low=report.trade_levels.entry_zone_low,
        entry_zone_high=report.trade_levels.entry_zone_high,
        stop_loss=report.trade_levels.stop_loss,
        take_profit_1=report.trade_levels.take_profit_1,
        take_profit_2=report.trade_levels.take_profit_2,
        take_profit_3=report.trade_levels.take_profit_3,
        risk_reward=report.trade_levels.risk_reward_tp1,
        setup_score=report.setup_score.total_score,
        probability_estimate=report.probability.estimated_win_probability,
        probability_status=report.probability.status_label,
        invalidation_condition=report.explanation.invalidation,
        short_reason=report.decision_reason,
        beginner_explanation=beginner_exp,
        pattern_story=pattern_story,
        simple_trade_plan=simple_plan,
        tracking=SignalTrackingState(
            last_checked_at=now,
            last_checked_price=report.current_price,
            tracking_note=(
                "Signal active; awaiting entry/target/SL monitoring."
                if signal_status in (SignalStatus.BUY_SIGNAL, SignalStatus.SELL_SIGNAL)
                else f"Status is {signal_status.value}."
            ),
        ),
        notified=False,
    )

    # Notify ONLY for qualifying BUY SIGNAL / SELL SIGNAL when enabled and not duplicated
    if signal_status in (SignalStatus.BUY_SIGNAL, SignalStatus.SELL_SIGNAL):
        if await _should_emit_signal_notification(report.symbol, report.timeframe, direction, settings, now):
            reason_line = (
                beginner_exp.why_bullets[0]
                if beginner_exp.why_bullets
                else report.decision_reason
            )
            msg = (
                f"Timeframe: {report.timeframe.value} | "
                f"Entry: {fmt(sig.entry_price)} | SL: {fmt(sig.stop_loss)} | "
                f"TP1: {fmt(sig.take_profit_1)} | TP2: {fmt(sig.take_profit_2)}. "
                f"Reason: {reason_line}"
            )
            await repo.save_notification(
                NotificationItem(
                    id=str(uuid.uuid4()),
                    created_at=now,
                    category="trade_signal",
                    severity="success" if direction == "BUY" else "warning",
                    title=f"{signal_status.value} — {report.symbol}",
                    message=msg,
                    metadata={
                        "signal_id": sig.signal_id,
                        "analysis_id": report.analysis_id,
                        "symbol": report.symbol,
                        "timeframe": report.timeframe.value,
                        "direction": direction,
                        "score": report.setup_score.total_score,
                    },
                )
            )
            sig.notified = True

    await repo.save_signal(sig)
    return sig


def evaluate_signal_against_candles(
    signal: TradeSignalRecord,
    candles: List[OHLCVCandle],
    now: Optional[datetime] = None,
) -> tuple[TradeSignalRecord, Optional[str]]:
    """
    Evaluate an active BUY SIGNAL / SELL SIGNAL against real OHLC candles after signal.candle_timestamp.
    Returns (updated_signal, transition_event_title_or_None).
    Never guesses intrabar execution order when both SL and TP are touched inside the same bar.
    """
    check_now = now or datetime.now(timezone.utc)
    if signal.status not in (SignalStatus.BUY_SIGNAL, SignalStatus.SELL_SIGNAL):
        return signal, None

    if signal.entry_price is None or signal.stop_loss is None or signal.take_profit_1 is None:
        return signal, None

    subsequent = [c for c in candles if c.timestamp > signal.candle_timestamp]
    is_buy = signal.direction == "BUY"
    tr = signal.tracking
    tr.last_checked_at = check_now
    if subsequent:
        tr.last_checked_price = subsequent[-1].close

    entry_low = signal.entry_zone_low or signal.entry_price
    entry_high = signal.entry_zone_high or signal.entry_price

    for bar in subsequent:
        if not tr.entry_reached:
            # Check if price touched entry zone or crossed entry level
            if (bar.low <= entry_high and bar.high >= entry_low) or (
                is_buy and bar.low <= signal.entry_price
            ) or (not is_buy and bar.high >= signal.entry_price):
                tr.entry_reached = True
                tr.entry_reached_at = bar.timestamp

        # Check intrabar ambiguity before evaluating outcome
        sl_hit = (bar.low <= signal.stop_loss) if is_buy else (bar.high >= signal.stop_loss)
        tp1_hit = (bar.high >= signal.take_profit_1) if is_buy else (bar.low <= signal.take_profit_1)

        if sl_hit and tp1_hit and not tr.tp1_reached and not tr.sl_reached:
            tr.ambiguous_intrabar = True
            tr.tracking_note = (
                f"Candle {bar.timestamp.isoformat()} touched both SL ({signal.stop_loss}) and "
                f"TP1 ({signal.take_profit_1}); intrabar order cannot be resolved from {signal.timeframe.value} data."
            )
            return signal, None

        if sl_hit and not tr.tp1_reached:
            tr.sl_reached = True
            tr.sl_reached_at = bar.timestamp
            signal.status = SignalStatus.STOP_LOSS_HIT
            tr.tracking_note = f"Stop Loss ({signal.stop_loss}) reached at {bar.timestamp.strftime('%Y-%m-%d %H:%M UTC')}."
            return signal, f"STOP LOSS HIT — {signal.symbol} ({signal.timeframe.value})"

        if tp1_hit and not tr.tp1_reached:
            tr.tp1_reached = True
            tr.tp1_reached_at = bar.timestamp

        if signal.take_profit_2 is not None:
            tp2_hit = (bar.high >= signal.take_profit_2) if is_buy else (bar.low <= signal.take_profit_2)
            if tp2_hit and not tr.tp2_reached and not tr.sl_reached:
                tr.tp2_reached = True
                tr.tp2_reached_at = bar.timestamp

        if signal.take_profit_3 is not None:
            tp3_hit = (bar.high >= signal.take_profit_3) if is_buy else (bar.low <= signal.take_profit_3)
            if tp3_hit and not tr.tp3_reached and not tr.sl_reached:
                tr.tp3_reached = True
                tr.tp3_reached_at = bar.timestamp

        if tr.tp1_reached:
            signal.status = SignalStatus.TARGET_HIT
            reached_list = ["TP1"]
            if tr.tp2_reached:
                reached_list.append("TP2")
            if tr.tp3_reached:
                reached_list.append("TP3")
            tr.tracking_note = f"Target(s) {', '.join(reached_list)} reached."
            return signal, f"TARGET HIT ({', '.join(reached_list)}) — {signal.symbol} ({signal.timeframe.value})"

    # Check expiry only if no target or SL has hit
    if check_now >= signal.expires_at and not tr.tp1_reached and not tr.sl_reached:
        tr.expired = True
        signal.status = SignalStatus.SIGNAL_EXPIRED
        tr.tracking_note = f"Signal expired at {signal.expires_at.strftime('%Y-%m-%d %H:%M UTC')} without reaching target."
        return signal, f"SIGNAL EXPIRED — {signal.symbol} ({signal.timeframe.value})"

    tr.tracking_note = (
        "Entry zone reached; monitoring TP1/SL."
        if tr.entry_reached
        else "Active signal; waiting for price to reach entry/TP/SL."
    )
    return signal, None


async def track_active_signals(allow_demo: bool = False) -> List[TradeSignalRecord]:
    """Check all active BUY/SELL signals against latest available market candles."""
    signals = await repo.list_signals(limit=300)
    active = [s for s in signals if s.status in (SignalStatus.BUY_SIGNAL, SignalStatus.SELL_SIGNAL)]
    candle_cache: Dict[tuple[str, Timeframe], List[OHLCVCandle]] = {}
    now = datetime.now(timezone.utc)

    for sig in active:
        key = (sig.symbol, sig.timeframe)
        if key not in candle_cache:
            mkt = await market_data_manager.get_market_data(
                symbol=sig.symbol,
                timeframe=sig.timeframe,
                limit=200,
                allow_demo=allow_demo or sig.is_demo,
            )
            candle_cache[key] = mkt.candles
        candles = candle_cache[key]
        if not candles:
            continue
        updated, event_title = evaluate_signal_against_candles(sig, candles, now=now)
        await repo.save_signal(updated)
        if event_title:
            await repo.save_notification(
                NotificationItem(
                    id=str(uuid.uuid4()),
                    created_at=now,
                    category="signal_tracking",
                    severity="success" if updated.status == SignalStatus.TARGET_HIT else "warning",
                    title=event_title,
                    message=updated.tracking.tracking_note,
                    metadata={"signal_id": updated.signal_id, "status": updated.status.value},
                )
            )

    return await repo.list_signals(limit=300)
