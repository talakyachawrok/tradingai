"""Transparent 0-100 Setup Scoring Engine with configurable weights and thresholds."""

from typing import List, Tuple
from app.models.analysis import (
    BiasDirection,
    CandlestickPattern,
    IndicatorSnapshot,
    LiquidityAnalysisResult,
    MarketStructureResult,
    MultiTimeframeResult,
    ScoreBreakdownItem,
    SetupScoreResult,
    TradeLevels,
)
from app.models.settings import ScoringThresholds, ScoringWeights


def determine_candidate_direction(
    structure: MarketStructureResult,
    mtf: MultiTimeframeResult,
    patterns: List[CandlestickPattern],
    indicators: IndicatorSnapshot,
) -> BiasDirection:
    """Infer directional candidate from quantitative signals without forcing a side."""
    bull_votes = 0.0
    bear_votes = 0.0

    if structure.bias == BiasDirection.BULLISH:
        bull_votes += 2.5
    elif structure.bias == BiasDirection.BEARISH:
        bear_votes += 2.5

    if mtf.overall_bias == BiasDirection.BULLISH:
        bull_votes += 2.0
    elif mtf.overall_bias == BiasDirection.BEARISH:
        bear_votes += 2.0

    if "bullish" in indicators.ema_alignment:
        bull_votes += 1.5
    elif "bearish" in indicators.ema_alignment:
        bear_votes += 1.5

    if patterns:
        top = patterns[0]
        if top.classification == BiasDirection.BULLISH:
            bull_votes += 1.5
        elif top.classification == BiasDirection.BEARISH:
            bear_votes += 1.5

    if bull_votes >= bear_votes + 1.5 and bull_votes >= 3.0:
        return BiasDirection.BULLISH
    if bear_votes >= bull_votes + 1.5 and bear_votes >= 3.0:
        return BiasDirection.BEARISH
    return BiasDirection.NEUTRAL


def _grade_score(score: float, thresholds: ScoringThresholds) -> str:
    if score <= thresholds.avoid_max:
        return "Avoid"
    if score <= thresholds.weak_max:
        return "Weak setup"
    if score <= thresholds.wait_max:
        return "Wait for confirmation"
    if score <= thresholds.qualified_max:
        return "Qualified setup"
    return "Strongly qualified setup"


def score_trade_setup(
    candidate_dir: BiasDirection,
    structure: MarketStructureResult,
    patterns: List[CandlestickPattern],
    liquidity: LiquidityAnalysisResult,
    indicators: IndicatorSnapshot,
    mtf: MultiTimeframeResult,
    levels: TradeLevels,
    weights_cfg: ScoringWeights | None = None,
    thresholds_cfg: ScoringThresholds | None = None,
) -> SetupScoreResult:
    """Compute explainable weighted setup score from 0 to 100."""
    weights = (weights_cfg or ScoringWeights()).normalized_weights()
    thresholds = thresholds_cfg or ScoringThresholds()
    items: List[ScoreBreakdownItem] = []

    def add(category_key: str, label: str, ratio: float, reason: str) -> None:
        max_pts = round(weights[category_key], 2)
        pts = round(max_pts * max(0.0, min(1.0, ratio)), 2)
        items.append(ScoreBreakdownItem(category=label, score=pts, max_score=max_pts, reason=reason))

    if candidate_dir not in (BiasDirection.BULLISH, BiasDirection.BEARISH):
        # Neutral / unclear market cannot score high
        add("trend_alignment", "Trend alignment", 0.2, f"EMA alignment is {indicators.ema_alignment}; no clear directional trend.")
        add("market_structure", "Market structure", 0.25, f"Structure is {structure.bias.value} ({structure.regime}).")
        add("candlestick_pattern", "Candlestick pattern", 0.25 if patterns else 0.0, patterns[0].name if patterns else "No decisive directional candle pattern.")
        add("liquidity", "Liquidity", 0.2, "No directional sweep/zone alignment.")
        add("support_resistance", "Support & resistance", 0.3, f"{len(liquidity.support_resistance)} S/R zones mapped.")
        add("indicator_confirmation", "Indicator confirmation", 0.2, "Mixed/neutral momentum indicators.")
        add("multi_timeframe_alignment", "Multi-timeframe alignment", mtf.alignment_score / 100.0 * 0.5, mtf.summary)
        add("volatility_suitability", "Volatility suitability", 0.5, indicators.volatility_condition)
        add("risk_reward_quality", "Risk/reward quality", 0.0, "No valid directional trade plan.")
        total = round(sum(i.score for i in items), 1)
        return SetupScoreResult(
            total_score=total,
            grade_label=_grade_score(total, thresholds),
            breakdown=items,
            direction_candidate=candidate_dir,
        )

    is_bull = candidate_dir == BiasDirection.BULLISH

    # 1. Trend alignment
    if (is_bull and indicators.ema_alignment == "strong_bullish_stack") or (
        not is_bull and indicators.ema_alignment == "strong_bearish_stack"
    ):
        add("trend_alignment", "Trend alignment", 1.0, f"EMAs 20/50/200 in {indicators.ema_alignment}.")
    elif (is_bull and "bullish" in indicators.ema_alignment) or (
        not is_bull and "bearish" in indicators.ema_alignment
    ):
        add("trend_alignment", "Trend alignment", 0.72, f"EMAs show {indicators.ema_alignment}.")
    else:
        add("trend_alignment", "Trend alignment", 0.2, f"EMAs ({indicators.ema_alignment}) do not confirm {candidate_dir.value} bias.")

    # 2. Market structure
    if structure.bias == candidate_dir:
        ratio = 1.0 if (structure.recent_bos or structure.recent_choch) else 0.8
        add("market_structure", "Market structure", ratio, structure.explanation)
    elif structure.bias == BiasDirection.NEUTRAL:
        add("market_structure", "Market structure", 0.4, "Structure is range-bound/neutral.")
    else:
        add("market_structure", "Market structure", 0.1, f"Structure ({structure.bias.value}) opposes candidate.")

    # 3. Candlestick pattern
    aligned_patterns = [p for p in patterns if p.classification == candidate_dir]
    if aligned_patterns:
        best = aligned_patterns[0]
        add("candlestick_pattern", "Candlestick pattern", best.strength_score / 100.0, f"{best.name} (strength {best.strength_score}/100).")
    elif patterns:
        add("candlestick_pattern", "Candlestick pattern", 0.25, f"Latest pattern ({patterns[0].name}) is {patterns[0].classification.value}.")
    else:
        add("candlestick_pattern", "Candlestick pattern", 0.0, "No recent candlestick pattern detected.")

    # 4. Liquidity
    aligned_sweeps = [s for s in liquidity.sweep_events if s.direction == candidate_dir]
    aligned_zones = [z for z in liquidity.liquidity_zones if z.bias == candidate_dir]
    if aligned_sweeps:
        add("liquidity", "Liquidity", 1.0, aligned_sweeps[-1].explanation)
    elif aligned_zones:
        add("liquidity", "Liquidity", 0.6, f"{len(aligned_zones)} aligned demand/supply or liquidity zone(s).")
    else:
        add("liquidity", "Liquidity", 0.25, "No recent liquidity sweep or aligned zone.")

    # 5. Support & Resistance
    if (is_bull and "bullish" in liquidity.pullback_retest_status) or (
        not is_bull and "bearish" in liquidity.pullback_retest_status
    ):
        add("support_resistance", "Support & resistance", 0.95, f"Price action confirms {liquidity.pullback_retest_status.replace('_', ' ')}.")
    elif liquidity.support_resistance:
        add("support_resistance", "Support & resistance", 0.65, f"{len(liquidity.support_resistance)} structural S/R zones mapped.")
    else:
        add("support_resistance", "Support & resistance", 0.3, "Limited nearby S/R definition.")

    # 6. Indicator confirmation
    ind_ratio = 0.5
    if indicators.rsi_14 is not None:
        if is_bull and 45 <= indicators.rsi_14 <= 68:
            ind_ratio += 0.25
        elif not is_bull and 32 <= indicators.rsi_14 <= 55:
            ind_ratio += 0.25
        elif (is_bull and indicators.rsi_14 >= 72) or (not is_bull and indicators.rsi_14 <= 28):
            ind_ratio -= 0.25
    if is_bull and "Bullish" in indicators.macd_condition:
        ind_ratio += 0.25
    elif not is_bull and "Bearish" in indicators.macd_condition:
        ind_ratio += 0.25
    if indicators.conflicts:
        ind_ratio -= 0.15 * len(indicators.conflicts)
    add(
        "indicator_confirmation",
        "Indicator confirmation",
        ind_ratio,
        f"RSI: {indicators.rsi_condition}; MACD: {indicators.macd_condition}.",
    )

    # 7. Multi-timeframe alignment
    mtf_ratio = mtf.alignment_score / 100.0
    if mtf.has_conflict:
        mtf_ratio = min(mtf_ratio, 0.35)
    add("multi_timeframe_alignment", "Multi-timeframe alignment", mtf_ratio, mtf.summary)

    # 8. Volatility suitability
    if "Normal" in indicators.volatility_condition:
        add("volatility_suitability", "Volatility suitability", 1.0, indicators.volatility_condition)
    elif "Elevated" in indicators.volatility_condition or "High" in indicators.volatility_condition:
        add("volatility_suitability", "Volatility suitability", 0.6, indicators.volatility_condition)
    else:
        add("volatility_suitability", "Volatility suitability", 0.35, indicators.volatility_condition)

    # 9. Risk/Reward quality
    rr = levels.risk_reward_tp1 or 0.0
    if rr >= 2.5:
        add("risk_reward_quality", "Risk/reward quality", 1.0, f"Strong R:R of {rr:.2f}:1 to TP1.")
    elif rr >= 1.8:
        add("risk_reward_quality", "Risk/reward quality", 0.85, f"Favorable R:R of {rr:.2f}:1 to TP1.")
    elif rr >= 1.5:
        add("risk_reward_quality", "Risk/reward quality", 0.65, f"Acceptable R:R of {rr:.2f}:1 to TP1.")
    else:
        add("risk_reward_quality", "Risk/reward quality", 0.0, f"Insufficient R:R ({rr:.2f}:1).")

    total = round(min(100.0, max(0.0, sum(i.score for i in items))), 1)
    return SetupScoreResult(
        total_score=total,
        grade_label=_grade_score(total, thresholds),
        breakdown=items,
        direction_candidate=candidate_dir,
    )
