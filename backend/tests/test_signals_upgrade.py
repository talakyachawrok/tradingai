"""Tests for AI Trade Signal lifecycle, confirmations, beginner explanations, tracking, and dedup."""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from app.analysis.decision import (
    evaluate_confirmations,
    evaluate_trade_decision,
    map_decision_to_signal_status,
)
from app.analysis.explanation import build_beginner_explanation, build_pattern_story, build_simple_trade_plan
from app.core.config import get_settings
from app.data.providers.webhook_cache import webhook_cache_provider
from app.database.connection import db_store
from app.database.repositories import repo
from app.main import app
from app.models.analysis import (
    BeginnerExplanation,
    BiasDirection,
    DecisionType,
    IndicatorSnapshot,
    LiquidityAnalysisResult,
    MarketStructureResult,
    MultiTimeframeResult,
    PatternStory,
    SetupScoreResult,
    SignalStatus,
    SimpleTradePlan,
    TradeAnalysisReport,
    TradeLevels,
    TradeSignalRecord,
)
from app.models.market import DataConnectionStatus, DataIntegrityReport, OHLCVCandle, Timeframe
from app.models.settings import AlertSettings, AppUserSettings, ConfirmationSettings, RiskSettings
from app.services.signals import evaluate_signal_against_candles, record_signal_from_report


def _sample_report(ts: datetime, decision: DecisionType = DecisionType.BUY_SETUP) -> TradeAnalysisReport:
    return TradeAnalysisReport(
        analysis_id="ana-1",
        signal_status=SignalStatus.BUY_SIGNAL if decision == DecisionType.BUY_SETUP else SignalStatus.NO_TRADE,
        created_at=ts,
        symbol="XAUUSD",
        provider="demo_historical",
        connection_status=DataConnectionStatus.DEMO_MODE,
        is_demo=True,
        timeframe=Timeframe.H1,
        current_price=2685.0,
        data_timestamp=ts,
        market_session="London / New York Overlap",
        market_trend=BiasDirection.BULLISH,
        market_structure=MarketStructureResult(
            bias=BiasDirection.BULLISH,
            regime="trending_bullish",
            explanation="Higher highs and higher lows detected.",
        ),
        liquidity=LiquidityAnalysisResult(summary="Support reaction confirmed."),
        indicators=IndicatorSnapshot(ema_alignment="strong_bullish_stack", rsi_14=56.0, atr_14=5.0),
        overlays={"timestamps": [], "ema_20": [], "ema_50": [], "ema_200": [], "rsi_14": [], "atr_14": []},
        multi_timeframe=MultiTimeframeResult(
            primary_timeframe=Timeframe.H1,
            alignment_score=85.0,
            overall_bias=BiasDirection.BULLISH,
            has_conflict=False,
            summary="Aligned bullish across H4 and H1.",
        ),
        setup_score=SetupScoreResult(
            total_score=82.0,
            grade_label="Qualified setup",
            direction_candidate=BiasDirection.BULLISH,
        ),
        trade_levels=TradeLevels(
            direction=BiasDirection.BULLISH,
            entry_price=2685.0,
            entry_zone_low=2683.0,
            entry_zone_high=2686.0,
            entry_condition="Confirmed close",
            requires_confirmation=False,
            stop_loss=2675.0,
            stop_loss_explanation="Below swing low 2677 with ATR buffer",
            take_profit_1=2705.0,
            tp1_explanation="Resistance level 2705",
            take_profit_2=2720.0,
            tp2_explanation="Upper liquidity zone",
            risk_reward_tp1=2.0,
            is_valid=True,
        ),
        probability={"model_validated": False, "status_label": "PROBABILITY MODEL NOT YET VALIDATED"},
        explanation={
            "engine_mode": "RULE_BASED_EXPLANATION",
            "pattern_explanation": "Bullish engulfing.",
            "market_structure_explanation": "Bullish HH/HL.",
            "liquidity_explanation": "Support bounce.",
            "indicator_explanation": "EMA bullish.",
            "multi_timeframe_explanation": "H4 agrees.",
            "trade_rationale": "Strong bullish alignment.",
            "invalidation": "Close below 2675.",
            "risk_assessment": "2.0:1 R:R.",
        },
        final_decision=decision,
        decision_reason="BUY SETUP QUALIFIED — Score 82.0/100, R:R 2.0:1.",
    )


def test_confirmation_rules_and_beginner_explanations():
    ts = datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc)
    rep = _sample_report(ts)

    # Require candlestick pattern when patterns=[] -> must withhold BUY and return WAIT FOR CONFIRMATION
    confirm_cfg = ConfirmationSettings(require_candlestick_pattern=True)
    met, missing = evaluate_confirmations(
        candidate_dir=BiasDirection.BULLISH,
        structure=rep.market_structure,
        patterns=[],
        liquidity=rep.liquidity,
        indicators=rep.indicators,
        mtf=rep.multi_timeframe,
        levels=rep.trade_levels,
        risk_settings=RiskSettings(),
        confirmations=confirm_cfg,
    )
    assert any("candlestick pattern" in m.lower() for m in missing)

    decision, _, _ = evaluate_trade_decision(
        candidate_dir=BiasDirection.BULLISH,
        integrity=DataIntegrityReport(raw_count=100, valid_count=100, is_stale=False),
        mtf=rep.multi_timeframe,
        score=rep.setup_score,
        levels=rep.trade_levels,
        risk_settings=RiskSettings(),
        confirmations=confirm_cfg,
        structure=rep.market_structure,
        patterns=[],
        liquidity=rep.liquidity,
        indicators=rep.indicators,
    )
    assert decision == DecisionType.WAIT
    status = map_decision_to_signal_status(decision, 82.0, 75.0, missing)
    assert status == SignalStatus.WAIT_FOR_CONFIRMATION

    beginner = build_beginner_explanation(
        symbol="XAUUSD",
        timeframe="1h",
        signal_status=SignalStatus.BUY_SIGNAL,
        decision=DecisionType.BUY_SETUP,
        decision_reason="Qualified",
        patterns=[],
        structure=rep.market_structure,
        liquidity=rep.liquidity,
        indicators=rep.indicators,
        mtf=rep.multi_timeframe,
        levels=rep.trade_levels,
        confirmations_met=met,
        confirmations_missing=[],
    )
    assert beginner.headline == "BUY SETUP DETECTED"
    assert len(beginner.why_bullets) >= 3
    plan = build_simple_trade_plan(DecisionType.BUY_SETUP, rep.trade_levels, decimals=2)
    assert plan.direction == "BUY"
    assert "2675.00" in plan.why_stop_loss_here


@pytest.mark.asyncio
async def test_signal_deduplication_and_notification_preferences(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "local_db_path", str(tmp_path / "sig_test.db"))
    await db_store.initialize()

    ts = datetime(2026, 2, 15, 14, 0, tzinfo=timezone.utc)
    rep = _sample_report(ts)
    beginner = BeginnerExplanation(headline="BUY SETUP DETECTED", why_bullets=["Bullish"], what_it_means="Strength.")
    story = PatternStory(detected=False)
    plan = build_simple_trade_plan(DecisionType.BUY_SETUP, rep.trade_levels, decimals=2)

    # 1. Disable BUY alerts -> signal is saved, but notification is suppressed
    settings_no_buy = AppUserSettings(alerts=AlertSettings(enable_buy_alerts=False))
    sig1 = await record_signal_from_report(rep, SignalStatus.BUY_SIGNAL, beginner, story, plan, settings_no_buy)
    assert sig1.notified is False
    notifs = await repo.list_notifications()
    assert len(notifs) == 0

    # 2. Re-running on same candle+direction returns existing signal (non-repainting dedup)
    sig_dup = await record_signal_from_report(rep, SignalStatus.BUY_SIGNAL, beginner, story, plan, AppUserSettings())
    assert sig_dup.signal_id == sig1.signal_id

    # 3. New candle with BUY alerts enabled emits exactly 1 notification
    rep2 = _sample_report(ts + timedelta(hours=1))
    rep2.analysis_id = "ana-2"
    sig2 = await record_signal_from_report(rep2, SignalStatus.BUY_SIGNAL, beginner, story, plan, AppUserSettings())
    assert sig2.notified is True
    notifs2 = await repo.list_notifications()
    assert len(notifs2) == 1
    assert "BUY SIGNAL — XAUUSD" in notifs2[0].title


def test_signal_tracking_tp_sl_expiry_and_ambiguous_intrabar():
    t0 = datetime(2026, 2, 15, 10, 0, tzinfo=timezone.utc)
    base_sig = TradeSignalRecord(
        signal_id="sig-1",
        dedup_key="k1",
        analysis_id="a1",
        created_at=t0,
        candle_timestamp=t0,
        expires_at=t0 + timedelta(hours=4),
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        provider="demo_historical",
        connection_status=DataConnectionStatus.DEMO_MODE,
        is_demo=True,
        direction="BUY",
        status=SignalStatus.BUY_SIGNAL,
        entry_price=2685.0,
        entry_zone_low=2683.0,
        entry_zone_high=2686.0,
        stop_loss=2675.0,
        take_profit_1=2705.0,
        take_profit_2=2720.0,
        risk_reward=2.0,
        setup_score=82.0,
        beginner_explanation=BeginnerExplanation(headline="BUY", what_it_means="Test"),
        pattern_story=PatternStory(),
        simple_trade_plan=SimpleTradePlan(),
    )

    # Case A: Intrabar ambiguity (single bar touches both 2675 SL and 2705 TP1) -> unresolved
    amb_bar = OHLCVCandle(
        timestamp=t0 + timedelta(hours=1),
        open=2685.0,
        high=2710.0,
        low=2670.0,
        close=2690.0,
    )
    amb_sig, ev = evaluate_signal_against_candles(base_sig.model_copy(deep=True), [amb_bar], now=t0 + timedelta(hours=1))
    assert amb_sig.tracking.ambiguous_intrabar is True
    assert amb_sig.status == SignalStatus.BUY_SIGNAL
    assert ev is None

    # Case B: Entry reached then TP1 and TP2 hit cleanly
    bar1 = OHLCVCandle(timestamp=t0 + timedelta(hours=1), open=2686.0, high=2692.0, low=2684.0, close=2690.0)
    bar2 = OHLCVCandle(timestamp=t0 + timedelta(hours=2), open=2690.0, high=2722.0, low=2689.0, close=2718.0)
    tp_sig, ev_tp = evaluate_signal_against_candles(base_sig.model_copy(deep=True), [bar1, bar2], now=t0 + timedelta(hours=2))
    assert tp_sig.tracking.entry_reached is True
    assert tp_sig.tracking.tp1_reached is True
    assert tp_sig.tracking.tp2_reached is True
    assert tp_sig.status == SignalStatus.TARGET_HIT
    assert "TARGET HIT" in (ev_tp or "")

    # Case C: Signal expires if past expires_at without SL or TP1
    exp_sig, ev_exp = evaluate_signal_against_candles(base_sig.model_copy(deep=True), [bar1], now=t0 + timedelta(hours=5))
    assert exp_sig.tracking.expired is True
    assert exp_sig.status == SignalStatus.SIGNAL_EXPIRED
    assert "SIGNAL EXPIRED" in (ev_exp or "")


def test_signals_api_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "local_db_path", str(tmp_path / "sig_api.db"))
    webhook_cache_provider._store.clear()
    with TestClient(app) as client:
        ana = client.post(
            "/api/analysis/run",
            json={"symbol": "XAUUSD", "timeframe": "1h", "allow_demo": True},
        )
        assert ana.status_code == 200
        body = ana.json()
        assert "signal_status" in body
        assert "beginner_explanation" in body
        assert "pattern_story" in body
        assert "simple_trade_plan" in body

        sigs = client.get("/api/signals")
        assert sigs.status_code == 200
        assert len(sigs.json()) >= 1

        tracked = client.post("/api/signals/track?allow_demo=true")
        assert tracked.status_code == 200
