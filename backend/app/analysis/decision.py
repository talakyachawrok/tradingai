"""Rules-based trade eligibility and decision gate (AI cannot override risk rules)."""

from typing import List, Tuple
from app.models.analysis import (
    BiasDirection,
    DecisionType,
    MultiTimeframeResult,
    SetupScoreResult,
    TradeLevels,
)
from app.models.journal import PaperAccountSummary
from app.models.market import DataIntegrityReport
from app.models.settings import RiskSettings


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
) -> Tuple[DecisionType, str, List[str]]:
    """
    Deterministic eligibility gate returning:
      BUY SETUP | SELL SETUP | WAIT | NO VALID SETUP
    """
    warnings: List[str] = list(integrity.warnings)

    if integrity.is_stale and not is_demo:
        return (
            DecisionType.NO_VALID_SETUP,
            "NO VALID SETUP — Market data is stale beyond configured freshness threshold.",
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
            "NO VALID SETUP — Market structure and indicators lack a clear directional edge.",
            warnings,
        )

    if not levels.is_valid:
        reason = "; ".join(levels.rejection_reasons) if levels.rejection_reasons else "Invalid trade levels."
        return (
            DecisionType.NO_VALID_SETUP,
            f"NO VALID SETUP — {reason}",
            warnings,
        )

    if risk_settings.require_htf_alignment and mtf.has_conflict:
        return (
            DecisionType.WAIT,
            "WAIT — Higher and lower/primary timeframes conflict (" + " ".join(mtf.conflict_reasons) + ")",
            warnings,
        )

    if risk_settings.require_candle_close_confirmation and levels.requires_confirmation:
        return (
            DecisionType.WAIT,
            "WAIT — Required candlestick/structure confirmation has not completed.",
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
