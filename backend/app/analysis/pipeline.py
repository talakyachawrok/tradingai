"""End-to-end quantitative analysis pipeline orchestrating all engines."""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.analysis.decision import evaluate_trade_decision
from app.analysis.explanation import generate_trade_explanation
from app.analysis.liquidity import analyze_liquidity_and_levels
from app.analysis.mtf import evaluate_multi_timeframe, select_mtf_roles
from app.analysis.scoring import determine_candidate_direction, score_trade_setup
from app.core.instruments import instrument_registry, normalize_symbol
from app.data.manager import compute_market_session, market_data_manager
from app.database.repositories import repo
from app.indicators.engine import evaluate_indicators
from app.ml.probability import probability_manager
from app.models.analysis import (
    BiasDirection,
    DecisionType,
    TradeAnalysisReport,
)
from app.models.journal import JournalEntry, NotificationItem, PaperAccountSummary
from app.models.market import DataConnectionStatus, OHLCVCandle, Timeframe
from app.patterns.engine import detect_candlestick_patterns
from app.risk.levels import calculate_trade_levels
from app.structure.engine import analyze_market_structure


async def run_full_analysis(
    symbol: str,
    timeframe: Timeframe,
    provider_override: Optional[str] = None,
    allow_demo: bool = False,
    paper_account: Optional[PaperAccountSummary] = None,
    news_blackout_active: bool = False,
    news_blackout_reason: str = "",
) -> TradeAnalysisReport:
    """
    Execute the complete quantitative + AI explanation pipeline on validated OHLCV data.
    Raises ValueError if market data is missing or insufficient.
    """
    settings = await repo.get_settings()
    norm_symbol = normalize_symbol(symbol)
    spec = instrument_registry.get(norm_symbol)
    decimals = spec.decimals if spec else 5

    primary_resp = await market_data_manager.get_market_data(
        symbol=norm_symbol,
        timeframe=timeframe,
        provider_override=provider_override or settings.data_provider,
        limit=300,
        allow_demo=allow_demo,
    )
    candles = primary_resp.candles
    if len(candles) < 30:
        raise ValueError(
            primary_resp.overview.status_message
            or f"Insufficient market data for {norm_symbol} ({timeframe.value}): found {len(candles)} candles (minimum 30 required)."
        )

    if primary_resp.integrity.is_stale and not primary_resp.overview.is_demo:
        raise ValueError(
            f"Market data for {norm_symbol} ({timeframe.value}) is stale "
            f"({primary_resp.integrity.stale_seconds}s old). Analysis refused."
        )

    # Fetch confirmation timeframes for Multi-Timeframe Analysis
    roles = select_mtf_roles(timeframe, settings.timeframes.confirmation_timeframes)
    candles_by_tf: Dict[Timeframe, List[OHLCVCandle]] = {timeframe: candles}
    for tf in roles:
        if tf == timeframe:
            continue
        tf_resp = await market_data_manager.get_market_data(
            symbol=norm_symbol,
            timeframe=tf,
            provider_override=provider_override or settings.data_provider,
            limit=220,
            allow_demo=allow_demo or primary_resp.overview.is_demo,
        )
        candles_by_tf[tf] = tf_resp.candles

    # Core analytical engines
    patterns = detect_candlestick_patterns(candles, settings.patterns)
    structure = analyze_market_structure(candles, settings.structure)
    liquidity = analyze_liquidity_and_levels(candles, structure, settings.structure)
    indicators, overlays = evaluate_indicators(candles, settings.indicators)
    mtf = evaluate_multi_timeframe(
        timeframe, candles_by_tf, roles, settings.indicators, settings.structure
    )

    candidate_dir = determine_candidate_direction(structure, mtf, patterns, indicators)
    levels = calculate_trade_levels(
        candles=candles,
        direction=candidate_dir,
        structure=structure,
        liquidity=liquidity,
        patterns=patterns,
        indicators=indicators,
        risk_settings=settings.risk,
        decimals=decimals,
    )
    score = score_trade_setup(
        candidate_dir=candidate_dir,
        structure=structure,
        patterns=patterns,
        liquidity=liquidity,
        indicators=indicators,
        mtf=mtf,
        levels=levels,
        weights_cfg=settings.scoring_weights,
        thresholds_cfg=settings.scoring_thresholds,
    )

    decision, decision_reason, risk_warnings = evaluate_trade_decision(
        candidate_dir=candidate_dir,
        integrity=primary_resp.integrity,
        mtf=mtf,
        score=score,
        levels=levels,
        risk_settings=settings.risk,
        paper_account=paper_account,
        news_blackout_active=news_blackout_active,
        news_blackout_reason=news_blackout_reason,
        is_demo=primary_resp.overview.is_demo,
    )

    probability = probability_manager.predict(candles)
    explanation = await generate_trade_explanation(
        symbol=norm_symbol,
        timeframe=timeframe.value,
        current_price=candles[-1].close,
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

    session_name, _ = compute_market_session()
    trend = (
        structure.bias
        if structure.bias in (BiasDirection.BULLISH, BiasDirection.BEARISH)
        else mtf.overall_bias
    )

    facts_summary = [
        f"Instrument: {norm_symbol} ({timeframe.value}) via {primary_resp.overview.data_source} [{primary_resp.overview.connection_status.value}]",
        f"Latest Close: {candles[-1].close:.{decimals}f} at {candles[-1].timestamp.isoformat()}",
        f"Valid Candles Audited: {primary_resp.integrity.valid_count} (gaps: {primary_resp.integrity.time_gaps_detected})",
        f"Session: {session_name}",
    ]
    calculated_findings = [
        f"Structure: {structure.bias.value} ({structure.regime})",
        f"Indicators: EMA={indicators.ema_alignment}, RSI={indicators.rsi_14}, ATR={indicators.atr_14}",
        f"MTF Alignment: {mtf.alignment_score}/100 (conflict={mtf.has_conflict})",
        f"Setup Score: {score.total_score}/100 ({score.grade_label})",
    ]

    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    report = TradeAnalysisReport(
        analysis_id=analysis_id,
        created_at=now,
        symbol=norm_symbol,
        provider=primary_resp.overview.data_source,
        connection_status=primary_resp.overview.connection_status,
        is_demo=primary_resp.overview.is_demo,
        timeframe=timeframe,
        current_price=candles[-1].close,
        data_timestamp=candles[-1].timestamp,
        market_session=session_name,
        market_trend=trend,
        market_structure=structure,
        patterns=patterns,
        liquidity=liquidity,
        indicators=indicators,
        overlays=overlays,
        multi_timeframe=mtf,
        setup_score=score,
        trade_levels=levels,
        probability=probability,
        explanation=explanation,
        final_decision=decision,
        decision_reason=decision_reason,
        risk_warnings=risk_warnings,
        facts_summary=facts_summary,
        calculated_findings=calculated_findings,
    )

    # Persist analysis and automatic journal entry (including rejected setups)
    await repo.save_analysis(analysis_id, report.model_dump(mode="json"), now.isoformat())
    journal_entry = JournalEntry(
        id=analysis_id,
        created_at=now,
        symbol=norm_symbol,
        timeframe=timeframe,
        provider=primary_resp.overview.data_source,
        connection_status=primary_resp.overview.connection_status,
        is_demo=primary_resp.overview.is_demo,
        data_timestamp=candles[-1].timestamp,
        current_price=candles[-1].close,
        patterns=[p.name for p in patterns[:3]],
        market_trend=trend.value,
        setup_score=score.total_score,
        decision=decision,
        decision_reason=decision_reason,
        entry_price=levels.entry_price,
        stop_loss=levels.stop_loss,
        take_profit_1=levels.take_profit_1,
        take_profit_2=levels.take_profit_2,
        take_profit_3=levels.take_profit_3,
        risk_reward=levels.risk_reward_tp1,
        probability_estimate=probability.estimated_win_probability,
        probability_status=probability.status_label,
        outcome="pending" if decision in (DecisionType.BUY_SETUP, DecisionType.SELL_SETUP) else "rejected",
        ai_explanation_summary=explanation.trade_rationale,
        snapshot={
            "score_breakdown": [b.model_dump(mode="json") for b in score.breakdown],
            "rsi_14": indicators.rsi_14,
            "atr_14": indicators.atr_14,
            "regime": structure.regime,
        },
    )
    await repo.save_journal_entry(journal_entry)

    # Emit notification
    if settings.notifications_enabled:
        sev = "success" if decision in (DecisionType.BUY_SETUP, DecisionType.SELL_SETUP) else "info"
        await repo.save_notification(
            NotificationItem(
                id=str(uuid.uuid4()),
                created_at=now,
                category="setup" if sev == "success" else "pattern",
                severity=sev,
                title=f"{norm_symbol} ({timeframe.value}): {decision.value}",
                message=decision_reason,
                metadata={"analysis_id": analysis_id, "score": score.total_score},
            )
        )

    return report
