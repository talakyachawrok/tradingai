"""Paper Trading Engine with risk-limit enforcement and live mark-to-market tracking."""

import uuid
from datetime import datetime, timezone
from typing import Dict, List
from app.core.instruments import instrument_registry, normalize_symbol
from app.data.manager import market_data_manager
from app.database.repositories import repo
from app.models.journal import (
    NotificationItem,
    PaperAccountSummary,
    PaperTradeOrderRequest,
    PaperTradePosition,
    PaperTradeStatus,
)
from app.models.market import Timeframe


async def get_paper_account_summary() -> PaperAccountSummary:
    settings = await repo.get_settings()
    state = await repo.get_paper_account_state()
    trades = await repo.list_paper_trades(limit=500)

    initial_balance = float(state.get("initial_balance", 10000.0))
    balance = float(state.get("balance", 10000.0))
    today = datetime.now(timezone.utc).date()

    open_positions = [t for t in trades if t.status == PaperTradeStatus.OPEN]
    closed_positions = [t for t in trades if t.status != PaperTradeStatus.OPEN]
    closed_sorted = sorted(
        closed_positions,
        key=lambda t: t.closed_at or t.opened_at,
        reverse=True,
    )

    unrealized = sum(t.unrealized_pnl for t in open_positions)
    realized = sum(t.realized_pnl for t in closed_positions)
    daily_closed = [
        t for t in closed_positions if (t.closed_at or t.opened_at).date() == today
    ]
    daily_opened = [t for t in trades if t.opened_at.date() == today]
    daily_realized = sum(t.realized_pnl for t in daily_closed)
    daily_loss_pct = (
        max(0.0, (-daily_realized / initial_balance) * 100.0) if initial_balance > 0 else 0.0
    )

    consec_losses = 0
    for t in closed_sorted:
        if t.realized_pnl < 0:
            consec_losses += 1
        else:
            break

    wins = sum(1 for t in closed_positions if t.realized_pnl > 0)
    losses = sum(1 for t in closed_positions if t.realized_pnl < 0)
    win_rate = (wins / len(closed_positions) * 100.0) if closed_positions else 0.0

    # Risk limit evaluation
    reasons: List[str] = []
    if daily_loss_pct >= settings.risk.max_daily_loss_pct:
        reasons.append(
            f"Daily loss ({daily_loss_pct:.2f}%) reached max limit ({settings.risk.max_daily_loss_pct:.2f}%)."
        )
    if len(daily_opened) >= settings.risk.max_daily_trades:
        reasons.append(
            f"Daily trades ({len(daily_opened)}) reached max limit ({settings.risk.max_daily_trades})."
        )
    if consec_losses >= settings.risk.max_consecutive_losses:
        reasons.append(
            f"Consecutive losses ({consec_losses}) reached max limit ({settings.risk.max_consecutive_losses})."
        )
    if len(open_positions) >= settings.risk.max_open_paper_trades:
        reasons.append(
            f"Open paper trades ({len(open_positions)}) reached max ({settings.risk.max_open_paper_trades})."
        )

    return PaperAccountSummary(
        initial_balance=round(initial_balance, 2),
        balance=round(balance, 2),
        equity=round(balance + unrealized, 2),
        unrealized_pnl=round(unrealized, 2),
        realized_pnl=round(realized, 2),
        daily_realized_pnl=round(daily_realized, 2),
        daily_loss_pct=round(daily_loss_pct, 2),
        daily_trades_count=len(daily_opened),
        consecutive_losses=consec_losses,
        open_positions_count=len(open_positions),
        total_closed_trades=len(closed_positions),
        winning_trades=wins,
        losing_trades=losses,
        win_rate_pct=round(win_rate, 2),
        risk_limit_breached=len(reasons) > 0,
        risk_limit_reasons=reasons,
    )


async def open_paper_trade(req: PaperTradeOrderRequest) -> PaperTradePosition:
    settings = await repo.get_settings()
    summary = await get_paper_account_summary()
    if summary.risk_limit_breached:
        raise ValueError("Risk limits breached: " + "; ".join(summary.risk_limit_reasons))
    if req.risk_percentage > settings.risk.max_risk_per_trade_pct:
        raise ValueError(
            f"Requested risk ({req.risk_percentage}%) exceeds configured max risk per trade ({settings.risk.max_risk_per_trade_pct}%)."
        )

    norm = normalize_symbol(req.symbol)
    direction = req.direction.strip().upper()
    if direction not in ("BUY", "SELL"):
        raise ValueError("Direction must be BUY or SELL.")

    entry = req.entry_price
    is_demo = req.is_demo_data
    if entry is None:
        mkt = await market_data_manager.get_market_data(
            norm, Timeframe.M15, allow_demo=req.is_demo_data
        )
        if mkt.overview.current_price is None:
            raise ValueError(
                f"Cannot execute market paper trade for {norm}: no current market price available."
            )
        entry = mkt.overview.current_price
        is_demo = mkt.overview.is_demo

    if direction == "BUY" and (req.stop_loss >= entry or req.take_profit <= entry):
        raise ValueError("For BUY trade, stop_loss must be below entry and take_profit above entry.")
    if direction == "SELL" and (req.stop_loss <= entry or req.take_profit >= entry):
        raise ValueError("For SELL trade, stop_loss must be above entry and take_profit below entry.")

    stop_dist = abs(entry - req.stop_loss)
    rr = abs(req.take_profit - entry) / stop_dist
    if rr < settings.risk.min_risk_reward:
        raise ValueError(
            f"Trade R:R ({rr:.2f}:1) is below configured minimum ({settings.risk.min_risk_reward:.2f}:1)."
        )

    risk_amount = round(summary.balance * (req.risk_percentage / 100.0), 2)
    units = round(risk_amount / stop_dist, 4)
    spec = instrument_registry.get(norm)
    lots = (
        round(units / spec.contract_size, 4)
        if spec and spec.contract_size
        else None
    )

    pos = PaperTradePosition(
        trade_id=str(uuid.uuid4()),
        symbol=norm,
        direction=direction,
        status=PaperTradeStatus.OPEN,
        opened_at=datetime.now(timezone.utc),
        entry_price=entry,
        current_price=entry,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
        quantity_units=units,
        lots=lots,
        risk_amount=risk_amount,
        risk_percentage=req.risk_percentage,
        analysis_id=req.analysis_id,
        setup_score=req.setup_score,
        is_demo_data=is_demo,
        notes=req.notes,
    )
    await repo.save_paper_trade(pos)
    return pos


async def close_paper_trade(
    trade_id: str, exit_price: float | None = None, status: PaperTradeStatus = PaperTradeStatus.CLOSED_MANUAL
) -> PaperTradePosition:
    trades = await repo.list_paper_trades(limit=500)
    pos = next((t for t in trades if t.trade_id == trade_id), None)
    if pos is None:
        raise ValueError("Paper trade not found.")
    if pos.status != PaperTradeStatus.OPEN:
        return pos

    px = exit_price if exit_price is not None else pos.current_price
    diff = (px - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - px)
    pnl = round(diff * pos.quantity_units, 2)
    r_mult = round(pnl / pos.risk_amount, 3) if pos.risk_amount > 0 else 0.0

    pos.status = status
    pos.closed_at = datetime.now(timezone.utc)
    pos.exit_price = px
    pos.current_price = px
    pos.unrealized_pnl = 0.0
    pos.realized_pnl = pnl
    pos.r_multiple = r_mult
    await repo.save_paper_trade(pos)

    state = await repo.get_paper_account_state()
    state["balance"] = round(float(state.get("balance", 10000.0)) + pnl, 2)
    await repo.save_paper_account_state(state)

    await repo.save_notification(
        NotificationItem(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            category="paper_trading",
            severity="success" if pnl >= 0 else "warning",
            title=f"Paper Trade {status.value}: {pos.symbol}",
            message=f"{pos.direction} closed at {px} with simulated P&L ${pnl:.2f} ({r_mult}R).",
            metadata={"trade_id": pos.trade_id},
        )
    )
    return pos


async def mark_to_market_open_positions(allow_demo: bool = False) -> List[PaperTradePosition]:
    """Update unrealized P&L and trigger SL/TP closes using available market prices."""
    trades = await repo.list_paper_trades(limit=500)
    open_trades = [t for t in trades if t.status == PaperTradeStatus.OPEN]
    price_cache: Dict[str, float] = {}

    for pos in open_trades:
        if pos.symbol not in price_cache:
            mkt = await market_data_manager.get_market_data(
                pos.symbol, Timeframe.M15, allow_demo=allow_demo or pos.is_demo_data
            )
            if mkt.overview.current_price is not None:
                price_cache[pos.symbol] = mkt.overview.current_price
        px = price_cache.get(pos.symbol)
        if px is None:
            continue

        if pos.direction == "BUY":
            if px <= pos.stop_loss:
                await close_paper_trade(pos.trade_id, pos.stop_loss, PaperTradeStatus.CLOSED_SL)
                continue
            if px >= pos.take_profit:
                await close_paper_trade(pos.trade_id, pos.take_profit, PaperTradeStatus.CLOSED_TP)
                continue
            unrealized = (px - pos.entry_price) * pos.quantity_units
        else:
            if px >= pos.stop_loss:
                await close_paper_trade(pos.trade_id, pos.stop_loss, PaperTradeStatus.CLOSED_SL)
                continue
            if px <= pos.take_profit:
                await close_paper_trade(pos.trade_id, pos.take_profit, PaperTradeStatus.CLOSED_TP)
                continue
            unrealized = (pos.entry_price - px) * pos.quantity_units

        pos.current_price = px
        pos.unrealized_pnl = round(unrealized, 2)
        await repo.save_paper_trade(pos)

    return await repo.list_paper_trades(limit=500)


async def reset_paper_account(initial_balance: float = 10000.0) -> PaperAccountSummary:
    trades = await repo.list_paper_trades(limit=500)
    from app.database.connection import db_store
    from app.database.repositories import COLLECTIONS

    for t in trades:
        await db_store.delete(COLLECTIONS["paper_trades"], t.trade_id)
    await repo.save_paper_account_state(
        {"initial_balance": initial_balance, "balance": initial_balance}
    )
    return await get_paper_account_summary()
