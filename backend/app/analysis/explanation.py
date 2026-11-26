"""AI Trade Explanation Engine with deterministic grounded narrative + optional LLM adapter."""

import json
from typing import Any, Dict, List, Optional
import httpx
from app.core.config import get_settings
from app.models.analysis import (
    CandlestickPattern,
    DecisionType,
    IndicatorSnapshot,
    LiquidityAnalysisResult,
    MarketStructureResult,
    MultiTimeframeResult,
    SetupScoreResult,
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
