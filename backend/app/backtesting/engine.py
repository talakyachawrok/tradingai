"""Look-ahead-free historical Backtesting Engine with conservative intrabar execution."""

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.analysis.liquidity import analyze_liquidity_and_levels
from app.analysis.scoring import determine_candidate_direction, score_trade_setup
from app.core.instruments import instrument_registry, normalize_symbol
from app.data.manager import market_data_manager
from app.database.repositories import repo
from app.indicators.engine import evaluate_indicators
from app.models.analysis import (
    BiasDirection,
    MultiTimeframeEntry,
    MultiTimeframeResult,
)
from app.models.journal import (
    BacktestBreakdownItem,
    BacktestRequest,
    BacktestResult,
    BacktestTradeRecord,
)
from app.models.market import OHLCVCandle, Timeframe
from app.patterns.engine import detect_candlestick_patterns
from app.risk.levels import calculate_trade_levels
from app.structure.engine import analyze_market_structure


def run_backtest_on_candles(
    candles: List[OHLCVCandle],
    req: BacktestRequest,
    data_source: str,
    is_demo: bool,
) -> BacktestResult:
    """
    Simulate trading signals strictly bar-by-bar using only historical data <= bar index i.
    Enforces conservative intrabar ordering: when a bar's range touches both SL and TP,
    stop-loss is assumed triggered first.
    """
    norm = normalize_symbol(req.symbol)
    spec = instrument_registry.get(norm)
    decimals = spec.decimals if spec else 5

    filtered = [
        c
        for c in candles
        if (req.start_date is None or c.timestamp >= req.start_date)
        and (req.end_date is None or c.timestamp <= req.end_date)
    ]
    if len(filtered) < 80:
        raise ValueError(
            f"Backtest requires at least 80 candles in selected range (found {len(filtered)})."
        )

    balance = req.initial_balance
    peak_balance = balance
    max_drawdown_pct = 0.0
    equity_curve: List[Dict] = [
        {"timestamp": filtered[60].timestamp.isoformat(), "balance": round(balance, 2), "drawdown_pct": 0.0}
    ]
    trades: List[BacktestTradeRecord] = []

    cost_rate = (req.spread_bps + req.slippage_bps + req.commission_bps * 2.0) / 10000.0
    open_pos: Optional[Dict] = None
    warmup = 60

    for i in range(warmup, len(filtered)):
        bar = filtered[i]

        # 1. Manage open position on current bar
        if open_pos is not None:
            is_buy = open_pos["direction"] == "BUY"
            sl = open_pos["sl"]
            tp = open_pos["tp"]
            sl_hit = (bar.low <= sl) if is_buy else (bar.high >= sl)
            tp_hit = (bar.high >= tp) if is_buy else (bar.low <= tp)

            exit_price: Optional[float] = None
            exit_reason = ""
            conflict_assumed_sl = False

            if sl_hit and tp_hit:
                # Conservative rule: unknown intrabar sequence -> assume SL hit first
                exit_price = sl
                exit_reason = "stop_loss"
                conflict_assumed_sl = True
            elif sl_hit:
                exit_price = sl
                exit_reason = "stop_loss"
            elif tp_hit:
                exit_price = tp
                exit_reason = "take_profit"
            elif i == len(filtered) - 1:
                exit_price = bar.close
                exit_reason = "end_of_data"

            if exit_price is not None:
                entry = open_pos["entry"]
                risk_dist = abs(entry - sl)
                raw_move = (exit_price - entry) if is_buy else (entry - exit_price)
                r_mult = raw_move / risk_dist if risk_dist > 0 else 0.0
                # Subtract round-trip transaction costs in R terms
                cost_amount = open_pos["notional_risk_base"] * cost_rate
                gross_pnl = open_pos["risk_amount"] * r_mult
                net_pnl = gross_pnl - cost_amount
                balance += net_pnl
                peak_balance = max(peak_balance, balance)
                dd_pct = ((peak_balance - balance) / peak_balance * 100.0) if peak_balance > 0 else 0.0
                max_drawdown_pct = max(max_drawdown_pct, dd_pct)

                trades.append(
                    BacktestTradeRecord(
                        trade_number=len(trades) + 1,
                        direction=open_pos["direction"],
                        entry_time=open_pos["entry_time"],
                        exit_time=bar.timestamp,
                        entry_price=round(entry, decimals),
                        stop_loss=round(sl, decimals),
                        take_profit=round(tp, decimals),
                        exit_price=round(exit_price, decimals),
                        exit_reason=exit_reason,
                        pattern=open_pos["pattern"],
                        regime=open_pos["regime"],
                        setup_score=open_pos["score"],
                        risk_reward_planned=open_pos["rr"],
                        r_multiple=round(net_pnl / open_pos["risk_amount"], 3)
                        if open_pos["risk_amount"] > 0
                        else 0.0,
                        pnl_amount=round(net_pnl, 2),
                        pnl_pct=round((net_pnl / (balance - net_pnl)) * 100.0, 2)
                        if (balance - net_pnl) > 0
                        else 0.0,
                        balance_after=round(balance, 2),
                        intrabar_conflict_assumed_sl=conflict_assumed_sl,
                    )
                )
                equity_curve.append(
                    {
                        "timestamp": bar.timestamp.isoformat(),
                        "balance": round(balance, 2),
                        "drawdown_pct": round(dd_pct, 2),
                    }
                )
                open_pos = None
            continue

        # 2. Evaluate new signal strictly from candles[:i+1] (no future data)
        if i >= len(filtered) - 1:
            break
        window = filtered[max(0, i - 140) : i + 1]
        patterns = detect_candlestick_patterns(window, lookback_tail=4)
        structure = analyze_market_structure(window)
        liquidity = analyze_liquidity_and_levels(window, structure)
        indicators, _ = evaluate_indicators(window)

        # Single-TF MTF proxy from primary timeframe structure (no future leakage)
        mtf_proxy = MultiTimeframeResult(
            primary_timeframe=req.timeframe,
            alignment_score=75.0 if structure.bias in (BiasDirection.BULLISH, BiasDirection.BEARISH) else 45.0,
            overall_bias=structure.bias,
            has_conflict=False,
            timeframes=[
                MultiTimeframeEntry(
                    timeframe=req.timeframe,
                    role="primary_timeframe",
                    available=True,
                    trend=structure.bias,
                    structure=structure.bias,
                    ema_alignment=indicators.ema_alignment,
                    rsi_14=indicators.rsi_14,
                )
            ],
            summary="Single-timeframe historical replay.",
        )

        candidate = determine_candidate_direction(structure, mtf_proxy, patterns, indicators)
        if candidate not in (BiasDirection.BULLISH, BiasDirection.BEARISH):
            continue

        levels = calculate_trade_levels(
            candles=window,
            direction=candidate,
            structure=structure,
            liquidity=liquidity,
            patterns=patterns,
            indicators=indicators,
            decimals=decimals,
        )
        if not levels.is_valid or levels.stop_loss is None or levels.take_profit_1 is None:
            continue

        rr = levels.risk_reward_tp1 or 0.0
        if rr < req.min_risk_reward:
            continue

        score_res = score_trade_setup(
            candidate_dir=candidate,
            structure=structure,
            patterns=patterns,
            liquidity=liquidity,
            indicators=indicators,
            mtf=mtf_proxy,
            levels=levels,
        )
        if score_res.total_score < req.min_setup_score:
            continue

        # Execute at NEXT bar open (bar i+1) to prevent same-bar close look-ahead
        next_bar = filtered[i + 1]
        entry_price = next_bar.open
        sl = levels.stop_loss
        risk_dist = abs(entry_price - sl)
        if risk_dist <= 0:
            continue
        if candidate == BiasDirection.BULLISH and sl >= entry_price:
            continue
        if candidate == BiasDirection.BEARISH and sl <= entry_price:
            continue

        if req.tp_methodology == "fixed_rr":
            tp = (
                entry_price + risk_dist * req.fixed_tp_rr
                if candidate == BiasDirection.BULLISH
                else entry_price - risk_dist * req.fixed_tp_rr
            )
            planned_rr = req.fixed_tp_rr
        else:
            tp = levels.take_profit_1
            planned_rr = round(abs(tp - entry_price) / risk_dist, 2)
            if planned_rr < req.min_risk_reward:
                continue

        risk_amount = balance * (req.risk_per_trade_pct / 100.0)
        notional_base = risk_amount * (entry_price / risk_dist)
        open_pos = {
            "direction": "BUY" if candidate == BiasDirection.BULLISH else "SELL",
            "entry": entry_price,
            "entry_time": next_bar.timestamp,
            "sl": sl,
            "tp": tp,
            "rr": planned_rr,
            "risk_amount": risk_amount,
            "notional_risk_base": notional_base,
            "pattern": patterns[0].name if patterns else "Structure/Indicator",
            "regime": structure.regime,
            "score": score_res.total_score,
        }

    # Performance statistics
    total = len(trades)
    wins = [t for t in trades if t.pnl_amount > 0]
    losses = [t for t in trades if t.pnl_amount <= 0]
    gross_profit = sum(t.pnl_amount for t in wins)
    gross_loss = abs(sum(t.pnl_amount for t in losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else None)
    win_rate = round((len(wins) / total) * 100.0, 2) if total > 0 else 0.0
    net_ret = round(balance - req.initial_balance, 2)
    net_ret_pct = round((net_ret / req.initial_balance) * 100.0, 2)
    avg_win = round(gross_profit / len(wins), 2) if wins else 0.0
    avg_loss = round(-gross_loss / len(losses), 2) if losses else 0.0
    avg_rr = round(sum(t.risk_reward_planned for t in trades) / total, 2) if total > 0 else 0.0
    expectancy_r = round(sum(t.r_multiple for t in trades) / total, 3) if total > 0 else 0.0
    expectancy_amt = round(net_ret / total, 2) if total > 0 else 0.0

    def build_breakdown(key_fn) -> List[BacktestBreakdownItem]:
        buckets = defaultdict(list)
        for t in trades:
            buckets[key_fn(t)].append(t)
        out = []
        for k, grp in buckets.items():
            w = sum(1 for x in grp if x.pnl_amount > 0)
            out.append(
                BacktestBreakdownItem(
                    key=k,
                    trades=len(grp),
                    wins=w,
                    losses=len(grp) - w,
                    win_rate_pct=round((w / len(grp)) * 100.0, 1),
                    net_pnl=round(sum(x.pnl_amount for x in grp), 2),
                    avg_r=round(sum(x.r_multiple for x in grp) / len(grp), 2),
                )
            )
        return out

    overfitting_warnings = [
        "Past historical backtest results do not guarantee future performance.",
    ]
    if total < 30:
        overfitting_warnings.append(
            f"Low sample size ({total} trades < 30): statistical reliability is limited and susceptible to variance."
        )
    if is_demo:
        overfitting_warnings.append(
            "Backtest ran on static Demo Historical sample data; validate on real historical market feeds before trusting metrics."
        )

    methodology_notes = [
        "Signals computed strictly on historical bars <= signal bar (no look-ahead).",
        "Entries executed at next bar open with spread, slippage, and round-trip commission deducted.",
        "Intrabar ambiguity rule: when both SL and TP fall inside the same bar's high-low range, SL is assumed triggered first.",
    ]

    return BacktestResult(
        backtest_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        symbol=norm,
        timeframe=req.timeframe,
        data_source=data_source,
        is_demo=is_demo,
        candles_evaluated=len(filtered),
        total_trades=total,
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate_pct=win_rate,
        profit_factor=profit_factor,
        average_rr=avg_rr,
        net_return_amount=net_ret,
        net_return_pct=net_ret_pct,
        max_drawdown_pct=round(max_drawdown_pct, 2),
        average_win=avg_win,
        average_loss=avg_loss,
        expectancy_r=expectancy_r,
        expectancy_amount=expectancy_amt,
        final_balance=round(balance, 2),
        equity_curve=equity_curve,
        by_pattern=build_breakdown(lambda t: t.pattern),
        by_regime=build_breakdown(lambda t: t.regime),
        by_timeframe=build_breakdown(lambda _: req.timeframe.value),
        by_instrument=build_breakdown(lambda _: norm),
        trades=trades,
        overfitting_warnings=overfitting_warnings,
        methodology_notes=methodology_notes,
    )


async def execute_backtest(req: BacktestRequest) -> BacktestResult:
    settings = await repo.get_settings()
    resp = await market_data_manager.get_market_data(
        symbol=req.symbol,
        timeframe=req.timeframe,
        provider_override=settings.data_provider,
        limit=600,
        allow_demo=req.use_demo_if_unavailable,
    )
    if not resp.candles:
        raise ValueError(
            resp.overview.status_message
            or f"No historical candles available for {req.symbol} ({req.timeframe.value})."
        )
    result = run_backtest_on_candles(
        candles=resp.candles,
        req=req,
        data_source=resp.overview.data_source,
        is_demo=resp.overview.is_demo,
    )
    await repo.save_backtest(result)
    return result
