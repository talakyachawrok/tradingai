"""Rule-based Entry, Stop-Loss, Take-Profit, and Risk/Reward calculation engine."""

from typing import List, Optional
from app.models.analysis import (
    BiasDirection,
    CandlestickPattern,
    IndicatorSnapshot,
    LiquidityAnalysisResult,
    MarketStructureResult,
    TradeLevels,
)
from app.models.market import OHLCVCandle
from app.models.settings import RiskSettings


def calculate_trade_levels(
    candles: List[OHLCVCandle],
    direction: BiasDirection,
    structure: MarketStructureResult,
    liquidity: LiquidityAnalysisResult,
    patterns: List[CandlestickPattern],
    indicators: IndicatorSnapshot,
    risk_settings: RiskSettings | None = None,
    decimals: int = 5,
) -> TradeLevels:
    """
    Compute defensible Entry, structural+ATR Stop-Loss, and TP1/TP2/TP3 targets.
    Never invents levels when direction is unclear or invalidation cannot be grounded.
    """
    cfg = risk_settings or RiskSettings()
    if len(candles) < 20 or direction not in (BiasDirection.BULLISH, BiasDirection.BEARISH):
        return TradeLevels(
            direction=direction,
            is_valid=False,
            rejection_reasons=["No directional bias established for entry/SL/TP calculation."],
        )

    last = candles[-1]
    atr = indicators.atr_14
    if atr is None or atr <= 0:
        atr = sum(c.high - c.low for c in candles[-14:]) / 14.0
    if atr <= 0:
        return TradeLevels(
            direction=direction,
            is_valid=False,
            rejection_reasons=["ATR is zero or unavailable; cannot size volatility buffer."],
        )

    rejection_reasons: List[str] = []
    if indicators.atr_pct is not None:
        if indicators.atr_pct < cfg.min_atr_pct:
            rejection_reasons.append(
                f"Volatility too compressed ({indicators.atr_pct:.3f}% < min {cfg.min_atr_pct:.3f}%)."
            )
        elif indicators.atr_pct > cfg.max_atr_pct:
            rejection_reasons.append(
                f"Volatility excessive ({indicators.atr_pct:.3f}% > max {cfg.max_atr_pct:.3f}%)."
            )

    entry_price = round(last.close, decimals)
    buffer = atr * cfg.atr_sl_buffer_multiple

    # Determine Entry Zone & Confirmation Condition
    requires_confirmation = False
    entry_condition = "Confirmed candle close aligned with structure."
    if liquidity.pullback_retest_status != "none":
        entry_condition = f"Entry supported by {liquidity.pullback_retest_status.replace('_', ' ')}."
    elif patterns and patterns[0].classification == direction:
        entry_condition = f"Triggered on {patterns[0].name} close at {entry_price:.{decimals}f}."
    else:
        requires_confirmation = True
        entry_condition = "Requires lower-timeframe break/retest or decisive pattern confirmation close."

    entry_zone_low = round(entry_price - atr * 0.2, decimals)
    entry_zone_high = round(entry_price + atr * 0.2, decimals)

    # Stop Loss based on structural invalidation + ATR buffer
    swing_lows = [s.price for s in structure.swing_points if s.kind == "swing_low"]
    swing_highs = [s.price for s in structure.swing_points if s.kind == "swing_high"]

    if direction == BiasDirection.BULLISH:
        recent_low = min(c.low for c in candles[-5:])
        valid_swings = [p for p in swing_lows if p < entry_price]
        structural_low = max(valid_swings) if valid_swings else recent_low
        # Choose the structural swing low if within reasonable 4*ATR, else recent 5-bar low
        if entry_price - structural_low > atr * 4.5:
            invalidation_anchor = recent_low
            anchor_label = "recent 5-bar swing low"
        else:
            invalidation_anchor = min(structural_low, recent_low)
            anchor_label = "structural higher-low / swing invalidation"
        stop_loss = round(invalidation_anchor - buffer, decimals)
        sl_explanation = (
            f"Placed below {anchor_label} ({invalidation_anchor:.{decimals}f}) "
            f"with a {cfg.atr_sl_buffer_multiple}x ATR volatility buffer ({buffer:.{decimals}f})."
        )
        risk_dist = entry_price - stop_loss
    else:
        recent_high = max(c.high for c in candles[-5:])
        valid_swings = [p for p in swing_highs if p > entry_price]
        structural_high = min(valid_swings) if valid_swings else recent_high
        if structural_high - entry_price > atr * 4.5:
            invalidation_anchor = recent_high
            anchor_label = "recent 5-bar swing high"
        else:
            invalidation_anchor = max(structural_high, recent_high)
            anchor_label = "structural lower-high / swing invalidation"
        stop_loss = round(invalidation_anchor + buffer, decimals)
        sl_explanation = (
            f"Placed above {anchor_label} ({invalidation_anchor:.{decimals}f}) "
            f"with a {cfg.atr_sl_buffer_multiple}x ATR volatility buffer ({buffer:.{decimals}f})."
        )
        risk_dist = stop_loss - entry_price

    if risk_dist <= 0 or stop_loss <= 0:
        return TradeLevels(
            direction=direction,
            entry_price=entry_price,
            is_valid=False,
            rejection_reasons=["Calculated stop-loss is inconsistent with entry direction."],
        )

    # Take Profits from structural S/R, liquidity zones, and R-multiples
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    tp1_exp = ""
    tp2_exp = ""
    tp3_exp = ""

    if direction == BiasDirection.BULLISH:
        overhead = sorted(
            {
                lvl.price
                for lvl in liquidity.support_resistance
                if lvl.level_type == "resistance" and lvl.price > entry_price + risk_dist * 1.1
            }
            | {
                lz.price_low
                for lz in liquidity.liquidity_zones
                if lz.zone_type in ("equal_highs", "supply_zone")
                and lz.price_low > entry_price + risk_dist * 1.2
            }
        )
        tp1 = round(overhead[0], decimals) if len(overhead) >= 1 else round(entry_price + risk_dist * max(cfg.min_risk_reward, 1.5), decimals)
        tp1_exp = (
            f"Nearest resistance/liquidity obstacle at {tp1:.{decimals}f}."
            if len(overhead) >= 1
            else f"1.5R structural extension target at {tp1:.{decimals}f}."
        )
        tp2 = round(overhead[1], decimals) if len(overhead) >= 2 and overhead[1] > tp1 else round(max(tp1 + risk_dist * 0.8, entry_price + risk_dist * 2.5), decimals)
        tp2_exp = (
            f"Secondary resistance/supply pool at {tp2:.{decimals}f}."
            if len(overhead) >= 2 and overhead[1] > tp1
            else f"2.5R trend-continuation target at {tp2:.{decimals}f}."
        )
        tp3 = round(max(tp2 + risk_dist * 0.9, entry_price + risk_dist * 3.5), decimals)
        tp3_exp = f"Extended swing projection (3.5R) at {tp3:.{decimals}f}."
        rr1 = round((tp1 - entry_price) / risk_dist, 2)
        rr2 = round((tp2 - entry_price) / risk_dist, 2)
        rr3 = round((tp3 - entry_price) / risk_dist, 2)
    else:
        underfoot = sorted(
            {
                lvl.price
                for lvl in liquidity.support_resistance
                if lvl.level_type == "support" and lvl.price < entry_price - risk_dist * 1.1
            }
            | {
                lz.price_high
                for lz in liquidity.liquidity_zones
                if lz.zone_type in ("equal_lows", "demand_zone")
                and lz.price_high < entry_price - risk_dist * 1.2
            },
            reverse=True,
        )
        tp1 = round(max(0.00001, underfoot[0]), decimals) if len(underfoot) >= 1 else round(max(0.00001, entry_price - risk_dist * max(cfg.min_risk_reward, 1.5)), decimals)
        tp1_exp = (
            f"Nearest support/liquidity target at {tp1:.{decimals}f}."
            if len(underfoot) >= 1
            else f"1.5R structural downside target at {tp1:.{decimals}f}."
        )
        tp2 = round(max(0.00001, underfoot[1]), decimals) if len(underfoot) >= 2 and underfoot[1] < tp1 else round(max(0.00001, min(tp1 - risk_dist * 0.8, entry_price - risk_dist * 2.5)), decimals)
        tp2_exp = (
            f"Secondary support/demand pool at {tp2:.{decimals}f}."
            if len(underfoot) >= 2 and underfoot[1] < tp1
            else f"2.5R bearish continuation target at {tp2:.{decimals}f}."
        )
        tp3 = round(max(0.00001, min(tp2 - risk_dist * 0.9, entry_price - risk_dist * 3.5)), decimals)
        tp3_exp = f"Extended swing projection (3.5R) at {tp3:.{decimals}f}."
        rr1 = round((entry_price - tp1) / risk_dist, 2)
        rr2 = round((entry_price - tp2) / risk_dist, 2)
        rr3 = round((entry_price - tp3) / risk_dist, 2)

    if rr1 < cfg.min_risk_reward:
        rejection_reasons.append(
            f"Risk/reward to TP1 ({rr1:.2f}:1) is below configured minimum ({cfg.min_risk_reward:.2f}:1)."
        )

    return TradeLevels(
        direction=direction,
        entry_price=entry_price,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        entry_condition=entry_condition,
        requires_confirmation=requires_confirmation,
        stop_loss=stop_loss,
        stop_loss_explanation=sl_explanation,
        take_profit_1=tp1,
        tp1_explanation=tp1_exp,
        take_profit_2=tp2,
        tp2_explanation=tp2_exp,
        take_profit_3=tp3,
        tp3_explanation=tp3_exp,
        risk_reward_tp1=rr1,
        risk_reward_tp2=rr2,
        risk_reward_tp3=rr3,
        is_valid=len(rejection_reasons) == 0,
        rejection_reasons=rejection_reasons,
    )
