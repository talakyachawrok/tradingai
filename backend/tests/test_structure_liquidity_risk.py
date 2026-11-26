"""Tests for market structure, liquidity/FVG, SL/TP, position sizing, scoring, and decision gates."""

from datetime import datetime, timedelta, timezone
from app.analysis.decision import evaluate_trade_decision
from app.analysis.liquidity import analyze_liquidity_and_levels
from app.analysis.scoring import determine_candidate_direction, score_trade_setup
from app.core.instruments import InstrumentSpec, instrument_registry
from app.indicators.engine import evaluate_indicators
from app.models.analysis import (
    BiasDirection,
    DecisionType,
    MultiTimeframeResult,
    PositionSizeRequest,
)
from app.models.market import DataIntegrityReport, OHLCVCandle, Timeframe
from app.models.settings import RiskSettings
from app.patterns.engine import detect_candlestick_patterns
from app.risk.levels import calculate_trade_levels
from app.risk.position_sizing import calculate_position_size
from app.structure.engine import analyze_market_structure


def build_trending_wave_candles() -> list[OHLCVCandle]:
    # Construct clear HH/HL bullish swing structure with an FVG and sweep
    prices = [
        100, 102, 104, 106, 105, 103, 102, 104, 107, 109,
        111, 109, 107, 106, 108, 112, 115, 117, 114, 112,
        111, 113, 116, 119, 121, 118, 116, 115, 118, 122,
        125, 127, 124, 122, 121, 124, 128, 131, 129, 127,
    ]
    candles = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, p in enumerate(prices):
        prev = prices[i - 1] if i > 0 else p - 1
        o = float(prev)
        c = float(p)
        h = max(o, c) + 0.8
        l = min(o, c) - 0.8
        candles.append(OHLCVCandle(timestamp=start + timedelta(hours=i), open=o, high=h, low=l, close=c, volume=1200.0))
    return candles


def test_structure_and_liquidity_detection():
    candles = build_trending_wave_candles()
    structure = analyze_market_structure(candles)
    assert structure.bias == BiasDirection.BULLISH
    assert len(structure.swing_points) >= 4
    labels = {s.label for s in structure.swing_points}
    assert "HH" in labels or "HL" in labels
    assert len(structure.structure_events) >= 1

    liq = analyze_liquidity_and_levels(candles, structure)
    assert len(liq.support_resistance) >= 1


def test_sl_tp_rr_and_decision_rejection():
    candles = build_trending_wave_candles()
    structure = analyze_market_structure(candles)
    liquidity = analyze_liquidity_and_levels(candles, structure)
    patterns = detect_candlestick_patterns(candles)
    indicators, _ = evaluate_indicators(candles)

    levels = calculate_trade_levels(
        candles=candles,
        direction=BiasDirection.BULLISH,
        structure=structure,
        liquidity=liquidity,
        patterns=patterns,
        indicators=indicators,
        risk_settings=RiskSettings(min_risk_reward=1.5),
        decimals=2,
    )
    assert levels.stop_loss is not None and levels.entry_price is not None
    assert levels.stop_loss < levels.entry_price
    assert levels.take_profit_1 is not None and levels.take_profit_1 > levels.entry_price
    assert (levels.risk_reward_tp1 or 0) >= 1.5

    # Decision engine must reject conflicting MTF when require_htf_alignment=True
    conflicting_mtf = MultiTimeframeResult(
        primary_timeframe=Timeframe.H1,
        alignment_score=40.0,
        overall_bias=BiasDirection.NEUTRAL,
        has_conflict=True,
        conflict_reasons=["4H bearish conflicts with 1H bullish"],
        summary="Conflict",
    )
    score = score_trade_setup(
        BiasDirection.BULLISH, structure, patterns, liquidity, indicators, conflicting_mtf, levels
    )
    decision, reason, _ = evaluate_trade_decision(
        candidate_dir=BiasDirection.BULLISH,
        integrity=DataIntegrityReport(raw_count=40, valid_count=40, is_stale=False),
        mtf=conflicting_mtf,
        score=score,
        levels=levels,
        risk_settings=RiskSettings(require_htf_alignment=True),
    )
    assert decision == DecisionType.WAIT
    assert "conflict" in reason.lower()


def test_position_sizing_exact_and_missing_specs_refusal():
    res = calculate_position_size(
        PositionSizeRequest(
            symbol="EURUSD",
            account_balance=10000.0,
            risk_percentage=1.0,  # $100 risk
            entry_price=1.1000,
            stop_loss=1.0950,  # 50 pips = 500 ticks -> $500/lot -> 0.20 lots
        )
    )
    assert res.specs_available is True
    assert res.risk_amount == 100.0
    assert res.recommended_lots == 0.20

    # Custom symbol without contract specs must refuse to guess
    instrument_registry.add_or_update(
        InstrumentSpec(
            symbol="CUSTOMXYZ",
            display_name="Custom Incomplete",
            asset_class="forex",
            base_currency="CUS",
            quote_currency="USD",
            decimals=4,
            specs_complete=False,
            is_custom=True,
        )
    )
    res_incomplete = calculate_position_size(
        PositionSizeRequest(
            symbol="CUSTOMXYZ",
            account_balance=10000.0,
            risk_percentage=1.0,
            entry_price=1.2000,
            stop_loss=1.1900,
        )
    )
    assert res_incomplete.specs_available is False
    assert res_incomplete.recommended_lots is None
    assert "incomplete or missing" in (res_incomplete.warning or "").lower()
