"""AI Trade Explanation Engine with deterministic grounded narrative + optional LLM adapter."""

import json
from typing import Any, Dict, List, Optional
import httpx
from app.core.config import get_settings
from app.models.analysis import (
    BeginnerExplanation,
    BiasDirection,
    CandlestickPattern,
    DecisionType,
    IndicatorSnapshot,
    LiquidityAnalysisResult,
    MarketStructureResult,
    MultiTimeframeResult,
    PatternStory,
    SetupScoreResult,
    SignalStatus,
    SimpleTradePlan,
    TradeExplanation,
    TradeLevels,
)


def build_rule_based_explanation(
    symbol: str,
    timeframe: str,
    current_price: float,
    patterns: List[CandlestickPattern],
    structure: MarketStructureResult,
    liquidity: LiquidityAnalysisResult,
    indicators: IndicatorSnapshot,
    mtf: MultiTimeframeResult,
    score: SetupScoreResult,
    levels: TradeLevels,
    decision: DecisionType,
    decision_reason: str,
) -> TradeExplanation:
    """Generate a thorough, plain-language explanation strictly from computed quantitative facts."""

    # A. Pattern explanation
    if patterns:
        p = patterns[0]
        others = ", ".join(x.name for x in patterns[1:3])
        pattern_exp = (
            f"Primary pattern detected: {p.name} ({p.classification.value}, strength {p.strength_score}/100). "
            f"{p.explanation} Confirmation requires: {'; '.join(p.confirmation_conditions)}. "
            f"Invalidation occurs on: {'; '.join(p.invalidation_conditions)}."
        )
        if others:
            pattern_exp += f" Secondary recent patterns: {others}."
    else:
        pattern_exp = (
            f"No high-conviction candlestick pattern formed in the recent lookback window on {symbol} {timeframe}. "
            "Price action alone does not justify an immediate directional trigger."
        )

    # B. Market structure explanation
    bos_text = (
        f"Latest BOS: {structure.recent_bos.direction.value} break at {structure.recent_bos.break_price:.5g}."
        if structure.recent_bos
        else "No recent BOS event."
    )
    choch_text = (
        f"Latest CHoCH: {structure.recent_choch.direction.value} break at {structure.recent_choch.break_price:.5g}."
        if structure.recent_choch
        else "No recent CHoCH reversal event."
    )
    structure_exp = f"{structure.explanation} {bos_text} {choch_text}"

    # C. Liquidity explanation
    sweep_text = (
        f"Rule-confirmed sweep detected: {liquidity.sweep_events[-1].explanation}"
        if liquidity.sweep_events
        else "No rule-confirmed liquidity sweep was detected in the recent window."
    )
    zone_names = ", ".join(
        f"{z.zone_type.replace('_', ' ')} ({z.price_low:.5g}–{z.price_high:.5g}, {z.certainty.value})"
        for z in liquidity.liquidity_zones[:3]
    )
    liquidity_exp = (
        f"{liquidity.summary} {sweep_text} "
        + (f"Key mapped zones: {zone_names}. " if zone_names else "")
        + "Note: Equal highs/lows represent inferred resting liquidity, not guaranteed targets."
    )

    # D. Indicator explanation
    conflict_note = (
        " Conflicts detected: " + " ".join(indicators.conflicts)
        if indicators.conflicts
        else " Indicators show no major internal divergence."
    )
    indicator_exp = (
        f"EMA alignment: {indicators.ema_alignment} (EMA20={indicators.ema_20}, EMA50={indicators.ema_50}, EMA200={indicators.ema_200}). "
        f"RSI(14): {indicators.rsi_condition}. MACD: {indicators.macd_condition}. "
        f"ATR volatility: {indicators.volatility_condition}. Volume: {indicators.volume_condition}.{conflict_note}"
    )

    # E. Multi-timeframe explanation
    tf_lines = [
        f"{e.timeframe.value} ({e.role.replace('_', ' ')}): trend={e.trend.value}, RSI={e.rsi_14}"
        if e.available
        else f"{e.timeframe.value} ({e.role.replace('_', ' ')}): UNAVAILABLE"
        for e in mtf.timeframes
    ]
    mtf_exp = f"{mtf.summary} Breakdown: " + "; ".join(tf_lines) + "."

    # F. Trade rationale
    if decision in (DecisionType.BUY_SETUP, DecisionType.SELL_SETUP):
        rationale = (
            f"Decision is {decision.value} on {symbol} ({timeframe}) at {current_price:.5g}. "
            f"Weighted setup score reached {score.total_score}/100 ({score.grade_label}). "
            f"{levels.entry_condition} Planned stop-loss is {levels.stop_loss} and TP1 is {levels.take_profit_1} "
            f"(R:R {levels.risk_reward_tp1}:1)."
        )
    elif decision == DecisionType.WAIT:
        rationale = (
            f"Decision is WAIT on {symbol} ({timeframe}). {decision_reason} "
            f"Current score is {score.total_score}/100 ({score.grade_label}); patience is prioritized over forcing an entry."
        )
    else:
        rationale = (
            f"Decision is NO VALID SETUP on {symbol} ({timeframe}). {decision_reason} "
            f"Setup score is {score.total_score}/100 ({score.grade_label}). Capital preservation rules reject entry."
        )

    # G. Invalidation
    if levels.stop_loss is not None:
        invalidation_exp = (
            f"Setup is invalidated if price breaches {levels.stop_loss} ({levels.stop_loss_explanation})"
        )
    else:
        invalidation_exp = (
            "No active trade levels were qualified; any structural break against the candidate bias or stale feed invalidates evaluation."
        )
    if patterns:
        invalidation_exp += f" Pattern invalidation: {'; '.join(patterns[0].invalidation_conditions)}."

    # H. Risk assessment
    obstacles = [
        f"{lvl.level_type} at {lvl.price:.5g}" for lvl in liquidity.support_resistance[:3]
    ]
    weak_points = [item.category for item in score.breakdown if item.max_score > 0 and (item.score / item.max_score) < 0.45]
    risk_exp = (
        f"Risk/Reward to TP1: {levels.risk_reward_tp1 if levels.risk_reward_tp1 is not None else 'N/A'}. "
        f"Volatility: {indicators.volatility_condition}. "
        + (f"Nearby S/R obstacles: {', '.join(obstacles)}. " if obstacles else "")
        + (f"Weakest scoring factors: {', '.join(weak_points)}. " if weak_points else "")
        + (f"Rejection/warning notes: {'; '.join(levels.rejection_reasons)}." if levels.rejection_reasons else "Ensure position size respects account risk limits.")
    )

    return TradeExplanation(
        engine_mode="RULE_BASED_EXPLANATION",
        pattern_explanation=pattern_exp,
        market_structure_explanation=structure_exp,
        liquidity_explanation=liquidity_exp,
        indicator_explanation=indicator_exp,
        multi_timeframe_explanation=mtf_exp,
        trade_rationale=rationale,
        invalidation=invalidation_exp,
        risk_assessment=risk_exp,
    )


async def generate_trade_explanation(
    symbol: str,
    timeframe: str,
    current_price: float,
    patterns: List[CandlestickPattern],
    structure: MarketStructureResult,
    liquidity: LiquidityAnalysisResult,
    indicators: IndicatorSnapshot,
    mtf: MultiTimeframeResult,
    score: SetupScoreResult,
    levels: TradeLevels,
    decision: DecisionType,
    decision_reason: str,
) -> TradeExplanation:
    """
    Produce structured explanation. Uses deterministic engine by default and optionally
    refines prose with a configured LLM provider strictly grounded on computed JSON facts.
    """
    base = build_rule_based_explanation(
        symbol=symbol,
        timeframe=timeframe,
        current_price=current_price,
        patterns=patterns,
        structure=structure,
        liquidity=liquidity,
        indicators=indicators,
        mtf=mtf,
        score=score,
        levels=levels,
        decision=decision,
        decision_reason=decision_reason,
    )

    settings = get_settings()
    provider = settings.ai_provider.lower().strip()
    if provider in ("", "none") or not settings._is_ai_configured():
        return base

    structured_facts = {
        "symbol": symbol,
        "timeframe": timeframe,
        "current_price": current_price,
        "decision": decision.value,
        "decision_reason": decision_reason,
        "setup_score": score.total_score,
        "grade": score.grade_label,
        "patterns": [p.model_dump(mode="json") for p in patterns[:3]],
        "structure": {"bias": structure.bias.value, "regime": structure.regime, "explanation": structure.explanation},
        "liquidity": liquidity.summary,
        "indicators": indicators.model_dump(mode="json"),
        "mtf": {"alignment_score": mtf.alignment_score, "has_conflict": mtf.has_conflict, "summary": mtf.summary},
        "trade_levels": levels.model_dump(mode="json"),
    }

    prompt = (
        "You are a quantitative trading analyst explaining computed technical analysis. "
        "STRICT RULES: Use ONLY the numbers and facts in the JSON below. Never invent prices, indicators, "
        "probabilities, or override the decision. Return valid JSON with keys: "
        "pattern_explanation, market_structure_explanation, liquidity_explanation, indicator_explanation, "
        "multi_timeframe_explanation, trade_rationale, invalidation, risk_assessment.\n\n"
        f"FACTS:\n{json.dumps(structured_facts)}"
    )

    try:
        parsed = await _call_llm_provider(provider, prompt, settings)
        if parsed:
            return TradeExplanation(
                engine_mode=f"LLM_ASSISTED_EXPLANATION ({provider})",
                pattern_explanation=parsed.get("pattern_explanation", base.pattern_explanation),
                market_structure_explanation=parsed.get("market_structure_explanation", base.market_structure_explanation),
                liquidity_explanation=parsed.get("liquidity_explanation", base.liquidity_explanation),
                indicator_explanation=parsed.get("indicator_explanation", base.indicator_explanation),
                multi_timeframe_explanation=parsed.get("multi_timeframe_explanation", base.multi_timeframe_explanation),
                trade_rationale=parsed.get("trade_rationale", base.trade_rationale),
                invalidation=parsed.get("invalidation", base.invalidation),
                risk_assessment=parsed.get("risk_assessment", base.risk_assessment),
            )
    except Exception:
        pass

    return base


async def _call_llm_provider(provider: str, prompt: str, settings: Any) -> Optional[Dict[str, str]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        if provider == "openai":
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)

        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
            resp = await client.post(
                url,
                params={"key": settings.gemini_api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
                },
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)

        if provider == "anthropic":
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": settings.anthropic_model,
                    "max_tokens": 1200,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"]
            return json.loads(text)

        if provider == "ollama":
            resp = await client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/generate",
                json={"model": settings.ollama_model, "prompt": prompt, "format": "json", "stream": False},
            )
            resp.raise_for_status()
            return json.loads(resp.json()["response"])
    return None


def build_beginner_explanation(
    symbol: str,
    timeframe: str,
    signal_status: SignalStatus,
    decision: DecisionType,
    decision_reason: str,
    patterns: List[CandlestickPattern],
    structure: MarketStructureResult,
    liquidity: LiquidityAnalysisResult,
    indicators: IndicatorSnapshot,
    mtf: MultiTimeframeResult,
    levels: TradeLevels,
    confirmations_met: List[str],
    confirmations_missing: List[str],
) -> BeginnerExplanation:
    """Build beginner-friendly plain-English summary strictly from computed market metrics."""
    why_bullets: List[str] = []

    if signal_status in (SignalStatus.BUY_SIGNAL, SignalStatus.SELL_SIGNAL):
        is_buy = signal_status == SignalStatus.BUY_SIGNAL
        headline = f"{'BUY' if is_buy else 'SELL'} SETUP DETECTED"

        if "bullish" in indicators.ema_alignment or "bearish" in indicators.ema_alignment:
            why_bullets.append(
                f"The market is showing short-term {'bullish (upward)' if is_buy else 'bearish (downward)'} momentum."
            )
        if patterns:
            top = patterns[0]
            why_bullets.append(f"A {top.name.lower()} candle pattern was detected.")
        if structure.bias in (BiasDirection.BULLISH, BiasDirection.BEARISH):
            why_bullets.append(
                f"The market price pattern (structure) supports a possible {'upward' if is_buy else 'downward'} move."
            )
        if liquidity.support_resistance or liquidity.sweep_events or liquidity.pullback_retest_status != "none":
            zone_word = "support (price floor)" if is_buy else "resistance (price ceiling)"
            why_bullets.append(f"Price reacted near an important {zone_word} zone.")
        if not mtf.has_conflict:
            why_bullets.append("The bigger-picture chart timeframe agrees with this direction.")
        if levels.risk_reward_tp1:
            why_bullets.append(
                f"The potential profit is {levels.risk_reward_tp1:.2f}x larger than the stop-loss risk."
            )

        what_it_means = (
            f"{'Buyers' if is_buy else 'Sellers'} are currently showing signs of strength on {symbol} ({timeframe}). "
            f"The AI has found conditions that may support a price {'increase' if is_buy else 'drop'}, "
            "but no trade is ever guaranteed—always stick to the Stop Loss."
        )
        return BeginnerExplanation(
            headline=headline,
            why_bullets=why_bullets,
            what_it_means=what_it_means,
            confirmations_met=confirmations_met,
            confirmations_missing=confirmations_missing,
            no_trade_category=None,
        )

    # Non-trade / Wait / Low Quality / Data Unavailable explanations
    no_trade_cat = "NO TRADE"
    if signal_status == SignalStatus.DATA_UNAVAILABLE:
        no_trade_cat = "DATA UNAVAILABLE"
        headline = "DATA UNAVAILABLE"
        what_it_means = (
            "The market data is missing or outdated. The AI cannot generate a reliable analysis until fresh prices arrive."
        )
    elif decision == DecisionType.WAIT:
        no_trade_cat = "WAIT"
        headline = "WAIT FOR CONFIRMATION"
        if levels.requires_confirmation:
            what_it_means = (
                "A potential setup has started forming, but the required confirmation candle or breakout has not finished yet. Wait before acting."
            )
        elif mtf.has_conflict:
            what_it_means = (
                "The shorter and longer charts disagree on direction right now. Waiting avoids getting caught in a tug-of-war."
            )
        else:
            what_it_means = (
                "Conditions are developing, but one or more confirmation checks are still missing. Patience protects your capital."
            )
    elif levels.rejection_reasons and any("risk/reward" in r.lower() for r in levels.rejection_reasons):
        no_trade_cat = "LOW QUALITY SETUP"
        headline = "LOW QUALITY SETUP — NO TRADE"
        what_it_means = (
            "The potential reward compared with the risk is below your configured minimum. Skipping low-reward trades protects your account."
        )
    else:
        headline = "NO TRADE — CONDITIONS UNCLEAR"
        what_it_means = (
            "Market conditions are unclear or choppy, and the trend and price structure do not give a clean edge. The AI is staying on the sidelines."
        )

    if patterns:
        why_bullets.append(f"Recent candle pattern seen: {patterns[0].name} ({patterns[0].classification.value}).")
    why_bullets.append(f"Current chart trend/structure: {structure.bias.value} ({structure.regime.replace('_', ' ')}).")
    if mtf.has_conflict:
        why_bullets.append("Different chart timeframes currently disagree.")
    for m in confirmations_missing[:3]:
        why_bullets.append(f"Missing check: {m}.")
    if not why_bullets:
        why_bullets.append(decision_reason)

    return BeginnerExplanation(
        headline=headline,
        why_bullets=why_bullets,
        what_it_means=what_it_means,
        confirmations_met=confirmations_met,
        confirmations_missing=confirmations_missing,
        no_trade_category=no_trade_cat,
    )


def build_pattern_story(
    patterns: List[CandlestickPattern],
    structure: MarketStructureResult,
    indicators: IndicatorSnapshot,
) -> PatternStory:
    """Create a plain-language story explaining the detected candlestick pattern."""
    if not patterns:
        return PatternStory(
            detected=False,
            pattern_name="No decisive candle pattern",
            direction="neutral",
            candles_involved=[],
            what_happened="Recent candles did not form a clear reversal or momentum candlestick pattern.",
            why_considered="Without a clear candle signal, price direction remains unconfirmed by bar shape.",
            confirmation_found="None yet — waiting for a stronger closing candle.",
            what_makes_it_fail="Sideways choppy bars inside a tight range.",
        )

    p = patterns[0]
    ts_list = [ts.strftime("%Y-%m-%d %H:%M UTC") for ts in p.timestamps]
    is_bull = p.classification == BiasDirection.BULLISH
    is_bear = p.classification == BiasDirection.BEARISH

    if "Engulfing" in p.name:
        what_happened = (
            f"The previous candle showed {'selling' if is_bull else 'buying'} pressure. "
            f"The latest {'bullish' if is_bull else 'bearish'} candle completely covered the prior candle's body, "
            f"suggesting {'buyers' if is_bull else 'sellers'} may be taking control."
        )
    elif "Hammer" in p.name or "Pin Bar" in p.name or "Shooting Star" in p.name:
        what_happened = (
            f"Price pushed {'down' if is_bull else 'up'} sharply during the candle, but "
            f"{'buyers' if is_bull else 'sellers'} rejected that move and pushed price back before the candle closed, leaving a long tail."
        )
    elif "Doji" in p.name:
        what_happened = (
            "Buyers and sellers fought to a standstill, so the candle opened and closed at nearly the same price."
        )
    else:
        what_happened = p.explanation

    why_considered = (
        f"The candle pattern is evaluated alongside the overall trend ({indicators.ema_alignment.replace('_', ' ')}) "
        f"and market structure ({structure.bias.value})."
    )
    return PatternStory(
        detected=True,
        pattern_name=p.name,
        direction=p.classification.value,
        candles_involved=ts_list,
        what_happened=what_happened,
        why_considered=why_considered,
        confirmation_found="; ".join(p.confirmation_conditions) or "Candle close completed",
        what_makes_it_fail="; ".join(p.invalidation_conditions) or "Price breaking the opposite side of the pattern",
    )


def build_simple_trade_plan(
    decision: DecisionType,
    levels: TradeLevels,
    decimals: int = 5,
) -> SimpleTradePlan:
    """Create an easy-to-read Trade Plan with beginner SL and target explanations."""
    if levels.entry_price is None or levels.stop_loss is None or levels.take_profit_1 is None:
        return SimpleTradePlan(
            direction="NONE",
            why_stop_loss_here="No Stop Loss calculated because there is no qualified setup.",
            why_targets_selected="No targets set until valid market structure and risk/reward levels appear.",
        )

    fmt = lambda v: f"{v:.{decimals}f}" if v is not None else "N/A"
    direction_label = (
        "BUY"
        if decision == DecisionType.BUY_SETUP or levels.direction == BiasDirection.BULLISH
        else ("SELL" if decision == DecisionType.SELL_SETUP or levels.direction == BiasDirection.BEARISH else "NONE")
    )

    entry_str = fmt(levels.entry_price)
    if levels.entry_zone_low is not None and levels.entry_zone_high is not None:
        entry_str = f"{fmt(levels.entry_price)} (Zone: {fmt(levels.entry_zone_low)} – {fmt(levels.entry_zone_high)})"

    why_sl = (
        f"If price reaches {fmt(levels.stop_loss)}, the recent price floor/ceiling is broken and the trade idea is wrong. "
        f"({levels.stop_loss_explanation})"
    )
    why_tp = (
        f"Targets are placed at nearby price floors/ceilings where buyers or sellers often pause or take profits: "
        f"TP1 ({levels.tp1_explanation})"
        + (f" TP2 ({levels.tp2_explanation})" if levels.take_profit_2 else "")
    )

    return SimpleTradePlan(
        direction=direction_label,
        entry_display=entry_str,
        stop_loss_display=fmt(levels.stop_loss),
        tp1_display=fmt(levels.take_profit_1),
        tp2_display=fmt(levels.take_profit_2),
        tp3_display=fmt(levels.take_profit_3),
        risk_reward_display=f"{levels.risk_reward_tp1:.2f} : 1" if levels.risk_reward_tp1 else "N/A",
        why_stop_loss_here=why_sl,
        why_targets_selected=why_tp,
    )

