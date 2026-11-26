"""Multi-timeframe analysis engine comparing higher, primary, and lower timeframes."""

from typing import Dict, List, Optional
from app.indicators.engine import evaluate_indicators
from app.models.analysis import (
    BiasDirection,
    MarketStructureResult,
    MultiTimeframeEntry,
    MultiTimeframeResult,
)
from app.models.market import TIMEFRAME_SECONDS, OHLCVCandle, Timeframe
from app.models.settings import IndicatorSettings, StructureSettings
from app.structure.engine import analyze_market_structure


def select_mtf_roles(
    primary: Timeframe, configured_confirmations: List[Timeframe]
) -> Dict[Timeframe, str]:
    """Map primary timeframe plus higher and lower confirmation timeframes."""
    primary_sec = TIMEFRAME_SECONDS[primary]
    roles: Dict[Timeframe, str] = {primary: "primary_timeframe"}

    higher = [tf for tf in configured_confirmations if TIMEFRAME_SECONDS[tf] > primary_sec]
    lower = [tf for tf in configured_confirmations if TIMEFRAME_SECONDS[tf] < primary_sec]

    if not higher:
        ordered = sorted(Timeframe, key=lambda t: TIMEFRAME_SECONDS[t])
        for tf in ordered:
            if TIMEFRAME_SECONDS[tf] > primary_sec:
                higher = [tf]
                break
    if not lower:
        ordered = sorted(Timeframe, key=lambda t: TIMEFRAME_SECONDS[t], reverse=True)
        for tf in ordered:
            if TIMEFRAME_SECONDS[tf] < primary_sec:
                lower = [tf]
                break

    for tf in higher[:1]:
        roles[tf] = "higher_timeframe"
    for tf in lower[:1]:
        roles[tf] = "lower_timeframe"
    return roles


def _derive_trend(structure: MarketStructureResult, ema_alignment: str) -> BiasDirection:
    if structure.bias in (BiasDirection.BULLISH, BiasDirection.BEARISH):
        return structure.bias
    if "bullish" in ema_alignment:
        return BiasDirection.BULLISH
    if "bearish" in ema_alignment:
        return BiasDirection.BEARISH
    if structure.bias == BiasDirection.NEUTRAL:
        return BiasDirection.NEUTRAL
    return BiasDirection.UNCLEAR


def evaluate_multi_timeframe(
    primary_tf: Timeframe,
    candles_by_tf: Dict[Timeframe, List[OHLCVCandle]],
    roles: Dict[Timeframe, str],
    indicator_settings: IndicatorSettings | None = None,
    structure_settings: StructureSettings | None = None,
) -> MultiTimeframeResult:
    """Compare structure, EMA trend, RSI, and key levels across timeframes."""
    entries: List[MultiTimeframeEntry] = []
    unavailable: List[Timeframe] = []
    trend_by_role: Dict[str, BiasDirection] = {}

    for tf, role in roles.items():
        tf_candles = candles_by_tf.get(tf, [])
        if len(tf_candles) < 25:
            unavailable.append(tf)
            entries.append(
                MultiTimeframeEntry(
                    timeframe=tf,
                    role=role,
                    available=False,
                    notes=f"Insufficient or unavailable data for {tf.value} ({len(tf_candles)} bars).",
                )
            )
            continue

        struct = analyze_market_structure(tf_candles, structure_settings)
        ind_snap, _ = evaluate_indicators(tf_candles, indicator_settings)
        trend = _derive_trend(struct, ind_snap.ema_alignment)
        trend_by_role[role] = trend

        recent_highs = [s.price for s in struct.swing_points if s.kind == "swing_high"]
        recent_lows = [s.price for s in struct.swing_points if s.kind == "swing_low"]
        entries.append(
            MultiTimeframeEntry(
                timeframe=tf,
                role=role,
                available=True,
                trend=trend,
                structure=struct.bias,
                ema_alignment=ind_snap.ema_alignment,
                rsi_14=ind_snap.rsi_14,
                key_support=recent_lows[-1] if recent_lows else None,
                key_resistance=recent_highs[-1] if recent_highs else None,
                notes=f"Structure {struct.bias.value} ({struct.regime}), EMA {ind_snap.ema_alignment}.",
            )
        )

    htf = trend_by_role.get("higher_timeframe")
    ptf = trend_by_role.get("primary_timeframe", BiasDirection.UNCLEAR)
    ltf = trend_by_role.get("lower_timeframe")

    conflict_reasons: List[str] = []
    if htf in (BiasDirection.BULLISH, BiasDirection.BEARISH) and ptf in (
        BiasDirection.BULLISH,
        BiasDirection.BEARISH,
    ):
        if htf != ptf:
            conflict_reasons.append(
                f"Higher timeframe is {htf.value} while primary timeframe ({primary_tf.value}) is {ptf.value}."
            )
    if ptf in (BiasDirection.BULLISH, BiasDirection.BEARISH) and ltf in (
        BiasDirection.BULLISH,
        BiasDirection.BEARISH,
    ):
        if ptf != ltf:
            conflict_reasons.append(
                f"Primary timeframe is {ptf.value} while lower timeframe execution bias is {ltf.value}."
            )
    if htf in (BiasDirection.BULLISH, BiasDirection.BEARISH) and ltf in (
        BiasDirection.BULLISH,
        BiasDirection.BEARISH,
    ):
        if htf != ltf and not conflict_reasons:
            conflict_reasons.append(
                f"Higher timeframe ({htf.value}) conflicts with lower timeframe ({ltf.value})."
            )

    # Alignment score
    score = 50.0
    if ptf in (BiasDirection.BULLISH, BiasDirection.BEARISH):
        score += 15.0
        if htf == ptf:
            score += 20.0
        elif htf in (BiasDirection.BULLISH, BiasDirection.BEARISH):
            score -= 25.0
        if ltf == ptf:
            score += 15.0
        elif ltf in (BiasDirection.BULLISH, BiasDirection.BEARISH):
            score -= 12.0
    else:
        score = 35.0

    if unavailable:
        score = max(20.0, score - 8.0 * len(unavailable))

    score = round(max(0.0, min(100.0, score)), 1)
    has_conflict = len(conflict_reasons) > 0

    if has_conflict:
        overall_bias = BiasDirection.NEUTRAL
    elif ptf in (BiasDirection.BULLISH, BiasDirection.BEARISH):
        overall_bias = ptf
    elif htf in (BiasDirection.BULLISH, BiasDirection.BEARISH):
        overall_bias = htf
    else:
        overall_bias = BiasDirection.UNCLEAR

    summary = (
        f"MTF alignment score {score:.1f}/100. "
        + ("CONFLICT DETECTED: " + " ".join(conflict_reasons) if has_conflict else f"Aligned bias: {overall_bias.value}.")
    )
    if unavailable:
        summary += f" Unavailable timeframes: {', '.join(t.value for t in unavailable)}."

    return MultiTimeframeResult(
        primary_timeframe=primary_tf,
        alignment_score=score,
        overall_bias=overall_bias,
        has_conflict=has_conflict,
        conflict_reasons=conflict_reasons,
        unavailable_timeframes=unavailable,
        timeframes=entries,
        summary=summary,
    )
