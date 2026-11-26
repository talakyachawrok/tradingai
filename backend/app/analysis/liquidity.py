"""Liquidity, Support/Resistance, Supply/Demand, FVG, Sweep, and Breakout engine."""

from typing import List
from app.indicators.engine import compute_atr_series
from app.models.analysis import (
    BiasDirection,
    CertaintyLevel,
    FairValueGap,
    LiquidityAnalysisResult,
    LiquiditySweepEvent,
    LiquidityZone,
    MarketStructureResult,
    SupportResistanceLevel,
)
from app.models.market import OHLCVCandle
from app.models.settings import StructureSettings


def analyze_liquidity_and_levels(
    candles: List[OHLCVCandle],
    structure: MarketStructureResult,
    settings: StructureSettings | None = None,
) -> LiquidityAnalysisResult:
    """
    Identify measurable S/R clusters, equal highs/lows, supply/demand zones,
    liquidity sweeps (distinguishing inferred vs rule-confirmed), FVGs, and breakouts.
    """
    cfg = settings or StructureSettings()
    n = len(candles)
    if n < 20:
        return LiquidityAnalysisResult(summary="Insufficient candles for liquidity and level analysis.")

    atr_series = compute_atr_series(candles, 14)
    atr = atr_series[-1] or (sum(c.high - c.low for c in candles[-14:]) / 14.0)
    atr = max(atr, 1e-12)
    eq_tol = atr * cfg.equal_level_tolerance_atr
    sr_tol = atr * cfg.sr_cluster_tolerance_atr

    # 1. Support and Resistance clusters from swing points
    sr_levels: List[SupportResistanceLevel] = []
    for sp in structure.swing_points:
        kind = "resistance" if sp.kind == "swing_high" else "support"
        matched = None
        for lvl in sr_levels:
            if lvl.level_type == kind and abs(lvl.price - sp.price) <= sr_tol:
                matched = lvl
                break
        if matched:
            matched.touches += 1
            matched.price = (matched.price + sp.price) / 2.0
            matched.zone_low = min(matched.zone_low, sp.price - sr_tol * 0.35)
            matched.zone_high = max(matched.zone_high, sp.price + sr_tol * 0.35)
            matched.last_touched = max(matched.last_touched, sp.timestamp)
            matched.strength = min(100.0, 45.0 + matched.touches * 16.0)
            matched.explanation = (
                f"{kind.capitalize()} zone around {matched.price:.5g} tested {matched.touches} times across swing fractals."
            )
        else:
            sr_levels.append(
                SupportResistanceLevel(
                    level_type=kind,
                    price=sp.price,
                    zone_low=sp.price - sr_tol * 0.35,
                    zone_high=sp.price + sr_tol * 0.35,
                    touches=1,
                    strength=50.0,
                    last_touched=sp.timestamp,
                    certainty=CertaintyLevel.CONFIRMED_RULE,
                    explanation=f"Swing {kind} pivot identified at {sp.price:.5g}.",
                )
            )
    sr_levels.sort(key=lambda x: (x.touches, x.strength), reverse=True)
    sr_levels = sr_levels[:8]

    # 2. Equal Highs / Equal Lows (resting liquidity pools)
    liquidity_zones: List[LiquidityZone] = []
    swing_highs = [s for s in structure.swing_points if s.kind == "swing_high"]
    swing_lows = [s for s in structure.swing_points if s.kind == "swing_low"]

    for i in range(len(swing_highs)):
        for j in range(i + 1, len(swing_highs)):
            if abs(swing_highs[i].price - swing_highs[j].price) <= eq_tol:
                p_low = min(swing_highs[i].price, swing_highs[j].price) - eq_tol * 0.2
                p_high = max(swing_highs[i].price, swing_highs[j].price) + eq_tol * 0.2
                liquidity_zones.append(
                    LiquidityZone(
                        zone_type="equal_highs",
                        bias=BiasDirection.BEARISH,
                        price_low=p_low,
                        price_high=p_high,
                        reference_timestamps=[swing_highs[i].timestamp, swing_highs[j].timestamp],
                        certainty=CertaintyLevel.POSSIBLE_INTERPRETATION,
                        explanation=(
                            f"Equal highs detected between {swing_highs[i].price:.5g} and {swing_highs[j].price:.5g} "
                            f"(within {cfg.equal_level_tolerance_atr}x ATR); potential buy-side stop liquidity."
                        ),
                    )
                )
                break

    for i in range(len(swing_lows)):
        for j in range(i + 1, len(swing_lows)):
            if abs(swing_lows[i].price - swing_lows[j].price) <= eq_tol:
                p_low = min(swing_lows[i].price, swing_lows[j].price) - eq_tol * 0.2
                p_high = max(swing_lows[i].price, swing_lows[j].price) + eq_tol * 0.2
                liquidity_zones.append(
                    LiquidityZone(
                        zone_type="equal_lows",
                        bias=BiasDirection.BULLISH,
                        price_low=p_low,
                        price_high=p_high,
                        reference_timestamps=[swing_lows[i].timestamp, swing_lows[j].timestamp],
                        certainty=CertaintyLevel.POSSIBLE_INTERPRETATION,
                        explanation=(
                            f"Equal lows detected between {swing_lows[i].price:.5g} and {swing_lows[j].price:.5g} "
                            f"(within {cfg.equal_level_tolerance_atr}x ATR); potential sell-side stop liquidity."
                        ),
                    )
                )
                break

    # 3. Supply / Demand zones (origin candle before strong displacement > 1.5x ATR)
    for i in range(max(2, n - 50), n - 2):
        c_origin = candles[i]
        c_disp = candles[i + 1]
        disp_move = c_disp.close - c_disp.open
        if disp_move > atr * 1.4 and c_origin.close <= c_origin.open:
            liquidity_zones.append(
                LiquidityZone(
                    zone_type="demand_zone",
                    bias=BiasDirection.BULLISH,
                    price_low=c_origin.low,
                    price_high=max(c_origin.open, c_origin.close),
                    reference_timestamps=[c_origin.timestamp],
                    certainty=CertaintyLevel.DETECTED_EVENT,
                    explanation=f"Demand origin candle ({c_origin.low:.5g}–{max(c_origin.open, c_origin.close):.5g}) preceding {disp_move/atr:.2f}x ATR bullish displacement.",
                )
            )
        elif -disp_move > atr * 1.4 and c_origin.close >= c_origin.open:
            liquidity_zones.append(
                LiquidityZone(
                    zone_type="supply_zone",
                    bias=BiasDirection.BEARISH,
                    price_low=min(c_origin.open, c_origin.close),
                    price_high=c_origin.high,
                    reference_timestamps=[c_origin.timestamp],
                    certainty=CertaintyLevel.DETECTED_EVENT,
                    explanation=f"Supply origin candle ({min(c_origin.open, c_origin.close):.5g}–{c_origin.high:.5g}) preceding {-disp_move/atr:.2f}x ATR bearish displacement.",
                )
            )

    # 4. Liquidity Sweeps (wick pierced prior swing high/low & closed back inside)
    sweep_events: List[LiquiditySweepEvent] = []
    tail_start = max(10, n - 12)
    for i in range(tail_start, n):
        c = candles[i]
        for sh in swing_highs:
            if sh.index < i - 1 and c.high > sh.price and c.close < sh.price:
                sweep_events.append(
                    LiquiditySweepEvent(
                        direction=BiasDirection.BEARISH,
                        swept_level=sh.price,
                        sweep_extreme=c.high,
                        close_price=c.close,
                        timestamp=c.timestamp,
                        index=i,
                        certainty=CertaintyLevel.CONFIRMED_RULE,
                        explanation=(
                            f"Wick swept above prior swing high {sh.price:.5g} (high {c.high:.5g}) "
                            f"and closed back below at {c.close:.5g}; rule-based bearish sweep rejection."
                        ),
                    )
                )
                break
        for sl in swing_lows:
            if sl.index < i - 1 and c.low < sl.price and c.close > sl.price:
                sweep_events.append(
                    LiquiditySweepEvent(
                        direction=BiasDirection.BULLISH,
                        swept_level=sl.price,
                        sweep_extreme=c.low,
                        close_price=c.close,
                        timestamp=c.timestamp,
                        index=i,
                        certainty=CertaintyLevel.CONFIRMED_RULE,
                        explanation=(
                            f"Wick swept below prior swing low {sl.price:.5g} (low {c.low:.5g}) "
                            f"and closed back above at {c.close:.5g}; rule-based bullish sweep reclaim."
                        ),
                    )
                )
                break

    # 5. Fair Value Gaps (3-candle imbalance: bar[i-2].high < bar[i].low or bar[i-2].low > bar[i].high)
    fvgs: List[FairValueGap] = []
    for i in range(max(2, n - 45), n):
        c0 = candles[i - 2]
        c2 = candles[i]
        if c2.low > c0.high and (c2.low - c0.high) >= atr * 0.15:
            filled = any(candles[k].low <= c0.high for k in range(i + 1, n))
            fvgs.append(
                FairValueGap(
                    direction=BiasDirection.BULLISH,
                    gap_low=c0.high,
                    gap_high=c2.low,
                    created_at=candles[i - 1].timestamp,
                    index=i - 1,
                    filled=filled,
                    explanation=f"Bullish FVG imbalance between {c0.high:.5g} and {c2.low:.5g} ({'filled' if filled else 'unfilled'}).",
                )
            )
        elif c2.high < c0.low and (c0.low - c2.high) >= atr * 0.15:
            filled = any(candles[k].high >= c0.low for k in range(i + 1, n))
            fvgs.append(
                FairValueGap(
                    direction=BiasDirection.BEARISH,
                    gap_low=c2.high,
                    gap_high=c0.low,
                    created_at=candles[i - 1].timestamp,
                    index=i - 1,
                    filled=filled,
                    explanation=f"Bearish FVG imbalance between {c2.high:.5g} and {c0.low:.5g} ({'filled' if filled else 'unfilled'}).",
                )
            )

    # 6. Breakout / Failed Breakout / Pullback-Retest evaluation on latest candle
    last = candles[-1]
    prev = candles[-2]
    breakout_status = "none"
    pullback_retest_status = "none"

    res_levels = [l for l in sr_levels if l.level_type == "resistance"]
    sup_levels = [l for l in sr_levels if l.level_type == "support"]

    if res_levels:
        nearest_res = min(res_levels, key=lambda l: abs(l.price - last.close))
        if last.close > nearest_res.zone_high and prev.close <= nearest_res.zone_high:
            breakout_status = "bullish_breakout"
        elif last.high > nearest_res.zone_high and last.close < nearest_res.zone_low:
            breakout_status = "failed_bullish_breakout"
        elif nearest_res.zone_low <= last.low <= nearest_res.zone_high and last.close > nearest_res.price:
            pullback_retest_status = "bullish_retest_of_broken_resistance"

    if sup_levels:
        nearest_sup = min(sup_levels, key=lambda l: abs(l.price - last.close))
        if last.close < nearest_sup.zone_low and prev.close >= nearest_sup.zone_low:
            breakout_status = "bearish_breakout"
        elif last.low < nearest_sup.zone_low and last.close > nearest_sup.zone_high:
            breakout_status = "failed_bearish_breakout"
        elif nearest_sup.zone_low <= last.high <= nearest_sup.zone_high and last.close < nearest_sup.price:
            pullback_retest_status = "bearish_retest_of_broken_support"

    # Trim zones to most relevant recent ones
    liquidity_zones = liquidity_zones[-8:]
    fvgs = [f for f in fvgs if not f.filled][-6:] or fvgs[-4:]

    summary_parts = [
        f"Identified {len(sr_levels)} S/R zones",
        f"{len(liquidity_zones)} liquidity/supply-demand zones",
        f"{len(sweep_events)} recent rule-based sweep events",
        f"{len([f for f in fvgs if not f.filled])} unfilled FVGs",
    ]
    if breakout_status != "none":
        summary_parts.append(f"breakout status: {breakout_status}")
    if pullback_retest_status != "none":
        summary_parts.append(f"retest status: {pullback_retest_status}")

    return LiquidityAnalysisResult(
        support_resistance=sr_levels,
        liquidity_zones=liquidity_zones,
        sweep_events=sweep_events[-6:],
        fair_value_gaps=fvgs,
        breakout_status=breakout_status,
        pullback_retest_status=pullback_retest_status,
        summary="; ".join(summary_parts) + ".",
    )
