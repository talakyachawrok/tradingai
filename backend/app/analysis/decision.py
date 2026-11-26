"""Rules-based trade eligibility, confirmation checks, and SignalStatus decision gate."""

from typing import List, Optional, Tuple
from app.models.analysis import (
    BiasDirection,
    CandlestickPattern,
    DecisionType,
    IndicatorSnapshot,
    LiquidityAnalysisResult,
    MarketStructureResult,
    MultiTimeframeResult,
    SetupScoreResult,
    SignalStatus,
    TradeLevels,
)
from app.models.journal import PaperAccountSummary
from app.models.market import DataIntegrityReport
from app.models.settings import ConfirmationSettings, RiskSettings


def evaluate_confirmations(
    candidate_dir: BiasDirection,
    structure: Optional[MarketStructureResult],
    patterns: List[CandlestickPattern],
    liquidity: Optional[LiquidityAnalysisResult],
    indicators: Optional[IndicatorSnapshot],
    mtf: MultiTimeframeResult,
    levels: TradeLevels,
    risk_settings: RiskSettings,
    confirmations: Optional[ConfirmationSettings],
) -> Tuple[List[str], List[str]]:
    """Evaluate all configurable confirmation gates against actual market calculations."""
    cfg = confirmations or ConfirmationSettings(
        require_candle_close=risk_settings.require_candle_close_confirmation,
        require_htf_alignment=risk_settings.require_htf_alignment,
    )
    met: List[str] = []
    missing: List[str] = []
    is_bull = candidate_dir == BiasDirection.BULLISH

    if cfg.require_candle_close:
        if not levels.requires_confirmation:
            met.append("Candle closed with confirmation")
        else:
            missing.append("Waiting for candle close / breakout confirmation")

    if cfg.require_market_structure and structure is not None:
        if structure.bias == candidate_dir:
            met.append(f"Market structure is {structure.bias.value} ({structure.regime.replace('_', ' ')})")
        else:
            missing.append(f"Market structure ({structure.bias.value}) does not confirm {candidate_dir.value} direction")

    if cfg.require_candlestick_pattern:
        aligned = [p for p in patterns if p.classification == candidate_dir]
        if aligned:
            met.append(f"Candlestick pattern confirmed ({aligned[0].name})")
        else:
            missing.append(f"No {candidate_dir.value} candlestick pattern detected")

    if cfg.require_trend_alignment and indicators is not None:
        if (is_bull and "bullish" in indicators.ema_alignment) or (
            not is_bull and "bearish" in indicators.ema_alignment
        ):
            met.append(f"Trend alignment supports {candidate_dir.value} move")
        else:
            missing.append(f"Trend alignment ({indicators.ema_alignment}) is not aligned")

    if cfg.require_htf_alignment or risk_settings.require_htf_alignment:
        if not mtf.has_conflict:
            met.append("Higher and lower timeframes agree")
        else:
            missing.append("Higher and lower timeframes conflict")

    if cfg.require_rsi_confirmation and indicators is not None:
        rsi = indicators.rsi_14
        if rsi is not None and ((is_bull and 42 <= rsi <= 68) or (not is_bull and 32 <= rsi <= 58)):
            met.append(f"RSI ({rsi:.1f}) supports entry without extreme exhaustion")
        else:
            missing.append(f"RSI ({rsi if rsi is not None else 'N/A'}) does not confirm entry")

    if cfg.require_ema_alignment and indicators is not None:
        if (is_bull and indicators.ema_alignment == "strong_bullish_stack") or (
            not is_bull and indicators.ema_alignment == "strong_bearish_stack"
        ):
            met.append(f"EMAs 20/50/200 are cleanly stacked ({indicators.ema_alignment})")
        else:
            missing.append(f"Full EMA 20/50/200 alignment not yet formed ({indicators.ema_alignment})")

    if cfg.require_liquidity_condition and liquidity is not None:
        aligned_sweeps = [s for s in liquidity.sweep_events if s.direction == candidate_dir]
        aligned_zones = [z for z in liquidity.liquidity_zones if z.bias == candidate_dir]
        if aligned_sweeps or aligned_zones or liquidity.pullback_retest_status != "none":
            met.append("Support/resistance or liquidity reaction zone present")
        else:
            missing.append("No liquidity sweep or key zone reaction detected")

    if cfg.require_min_risk_reward:
        rr = levels.risk_reward_tp1 or 0.0
        if rr >= risk_settings.min_risk_reward:
            met.append(f"Reward vs risk ({rr:.2f}:1) meets minimum ({risk_settings.min_risk_reward:.2f}:1)")
        else:
            missing.append(f"Reward vs risk ({rr:.2f}:1) is below minimum ({risk_settings.min_risk_reward:.2f}:1)")

    return met, missing


def map_decision_to_signal_status(
    decision: DecisionType,
    score_value: float,
    min_score: float,
    confirmations_missing: List[str],
    data_unavailable: bool = False,
) -> SignalStatus:
    """Map quantitative decision & confirmation state to user-facing SignalStatus."""
    if data_unavailable:
        return SignalStatus.DATA_UNAVAILABLE
    if decision == DecisionType.BUY_SETUP:
        return SignalStatus.BUY_SIGNAL
    if decision == DecisionType.SELL_SETUP:
        return SignalStatus.SELL_SIGNAL
    if decision == DecisionType.WAIT:
        if score_value >= max(55.0, min_score - 10.0) and confirmations_missing:
            return SignalStatus.WAIT_FOR_CONFIRMATION
        return SignalStatus.SETUP_FORMING
    return SignalStatus.NO_TRADE


def evaluate_trade_decision(
    candidate_dir: BiasDirection,
    integrity: DataIntegrityReport,
    mtf: MultiTimeframeResult,
    score: SetupScoreResult,
    levels: TradeLevels,
    risk_settings: RiskSettings,
    paper_account: PaperAccountSummary | None = None,
    news_blackout_active: bool = False,
    news_blackout_reason: str = "",
    is_demo: bool = False,
    confirmations: ConfirmationSettings | None = None,
    structure: MarketStructureResult | None = None,
    patterns: List[CandlestickPattern] | None = None,
    liquidity: LiquidityAnalysisResult | None = None,
    indicators: IndicatorSnapshot | None = None,
) -> Tuple[DecisionType, str, List[str]]:
    """
    Deterministic eligibility gate returning:
      BUY SETUP | SELL SETUP | WAIT | NO VALID SETUP
    """
    warnings: List[str] = list(integrity.warnings)

    if integrity.is_stale and not is_demo:
        return (
            DecisionType.NO_VALID_SETUP,
            "NO VALID SETUP — Market data is unavailable or outdated. The AI cannot generate a reliable analysis.",
            warnings,
        )

    if news_blackout_active:
        warnings.append(news_blackout_reason)
        return (
            DecisionType.WAIT,
            f"WAIT — High-impact news blackout active: {news_blackout_reason}",
            warnings,
        )

    if paper_account and paper_account.risk_limit_breached:
        warnings.extend(paper_account.risk_limit_reasons)
        return (
            DecisionType.NO_VALID_SETUP,
            "NO VALID SETUP — Account risk limits reached: " + "; ".join(paper_account.risk_limit_reasons),
            warnings,
        )

    if candidate_dir not in (BiasDirection.BULLISH, BiasDirection.BEARISH):
        return (
            DecisionType.NO_VALID_SETUP,
            "NO VALID SETUP — Market conditions are unclear. The trend and market structure are conflicting or sideways.",
            warnings,
        )

    if not levels.is_valid:
        reason = "; ".join(levels.rejection_reasons) if levels.rejection_reasons else "Invalid trade levels."
        return (
            DecisionType.NO_VALID_SETUP,
            f"NO VALID SETUP — {reason}",
            warnings,
        )

    _, missing = evaluate_confirmations(
        candidate_dir=candidate_dir,
        structure=structure,
        patterns=patterns or [],
        liquidity=liquidity,
        indicators=indicators,
        mtf=mtf,
        levels=levels,
        risk_settings=risk_settings,
        confirmations=confirmations,
    )

    if (confirmations.require_htf_alignment if confirmations else risk_settings.require_htf_alignment) and mtf.has_conflict:
        return (
            DecisionType.WAIT,
            "WAIT — Higher and lower/primary timeframes conflict (" + " ".join(mtf.conflict_reasons) + ")",
            warnings,
        )

    if (confirmations.require_candle_close if confirmations else risk_settings.require_candle_close_confirmation) and levels.requires_confirmation:
        return (
            DecisionType.WAIT,
            "WAIT — A potential setup is forming, but candle close or breakout confirmation has not completed yet.",
            warnings,
        )

    if missing:
        return (
            DecisionType.WAIT,
            "WAIT — Confirmation rules not yet satisfied: " + "; ".join(missing),
            warnings,
        )

    if score.total_score < risk_settings.min_setup_score:
        if score.total_score >= max(50.0, risk_settings.min_setup_score - 12.0):
            return (
                DecisionType.WAIT,
                f"WAIT — Setup score {score.total_score:.1f}/100 is below qualification minimum ({risk_settings.min_setup_score:.1f}).",
                warnings,
            )
        return (
            DecisionType.NO_VALID_SETUP,
            f"NO VALID SETUP — Setup score {score.total_score:.1f}/100 is too weak ({score.grade_label}).",
            warnings,
        )

    if candidate_dir == BiasDirection.BULLISH:
        return (
            DecisionType.BUY_SETUP,
            f"BUY SETUP QUALIFIED — Score {score.total_score:.1f}/100 ({score.grade_label}), R:R {levels.risk_reward_tp1}:1.",
            warnings,
        )
    return (
        DecisionType.SELL_SETUP,
        f"SELL SETUP QUALIFIED — Score {score.total_score:.1f}/100 ({score.grade_label}), R:R {levels.risk_reward_tp1}:1.",
        warnings,
    )
