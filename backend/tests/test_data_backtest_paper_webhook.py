"""Tests for OHLCV validation, backtesting intrabar rules, paper trading, ML gating, and FastAPI/webhook routes."""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from app.backtesting.engine import run_backtest_on_candles
from app.data.providers.demo_historical import DemoHistoricalProvider
from app.data.validator import validate_and_clean_candles
from app.database.connection import db_store
from app.main import app
from app.ml.probability import ProbabilityModelManager
from app.models.journal import BacktestRequest
from app.models.market import OHLCVCandle, Timeframe


def test_data_validator_dedup_corruption_and_gaps():
    now = datetime.now(timezone.utc)
    raw = [
        {"timestamp": (now - timedelta(hours=3)).isoformat(), "open": 100, "high": 105, "low": 99, "close": 102},
        # Duplicate timestamp
        {"timestamp": (now - timedelta(hours=3)).isoformat(), "open": 100, "high": 105, "low": 99, "close": 102},
        # Invalid high < low
        {"timestamp": (now - timedelta(hours=2)).isoformat(), "open": 100, "high": 95, "low": 99, "close": 98},
        # Time gap (skipped hour -2 and -1 -> 3h jump)
        {"timestamp": (now - timedelta(minutes=5)).isoformat(), "open": 102, "high": 106, "low": 101, "close": 104, "volume": 500},
    ]
    candles, report = validate_and_clean_candles(raw, Timeframe.H1, stale_threshold_seconds=900, reference_now=now)
    assert report.duplicates_removed == 1
    assert report.invalid_candles_dropped == 1
    assert report.time_gaps_detected == 1
    assert report.is_stale is False
    assert len(candles) == 2


@pytest.mark.asyncio
async def test_backtest_lookahead_free_and_demo_run():
    provider = DemoHistoricalProvider()
    res = await provider.fetch_candles("BTCUSD", Timeframe.H1, limit=260)
    candles, _ = validate_and_clean_candles(res.raw_candles, Timeframe.H1, check_staleness=False)

    bt = run_backtest_on_candles(
        candles=candles,
        req=BacktestRequest(
            symbol="BTCUSD",
            timeframe=Timeframe.H1,
            initial_balance=10000.0,
            risk_per_trade_pct=1.0,
            min_setup_score=55.0,
            min_risk_reward=1.2,
        ),
        data_source="demo_historical",
        is_demo=True,
    )
    assert bt.candles_evaluated == len(candles)
    assert bt.is_demo is True
    assert bt.final_balance > 0
    for tr in bt.trades:
        assert tr.entry_time < tr.exit_time


@pytest.mark.asyncio
async def test_ml_model_strict_unvalidated_until_trained():
    mgr = ProbabilityModelManager(auto_load=False)
    provider = DemoHistoricalProvider()
    res = await provider.fetch_candles("XAUUSD", Timeframe.H1, limit=260)
    candles, _ = validate_and_clean_candles(res.raw_candles, Timeframe.H1, check_staleness=False)

    untrained_pred = mgr.predict(candles)
    assert untrained_pred.model_validated is False
    assert untrained_pred.estimated_win_probability is None
    assert "ML UNAVAILABLE" in untrained_pred.status_label

    report = mgr.train_and_validate(
        candles, "XAUUSD", Timeframe.H1, model_type="logistic_regression", horizon_bars=12, is_demo=True
    )
    assert "validated" in report
    if report["validated"]:
        trained_pred = mgr.predict(candles)
        assert trained_pred.model_validated is True
        assert trained_pred.is_experimental is True
        assert 0.0 <= (trained_pred.estimated_win_probability or 0.0) <= 1.0


def test_api_endpoints_webhook_dedup_and_paper_trading():
    db_store.reset()

    with TestClient(app) as client:
        # 1. Root /health and /api/health checks
        root_h = client.get("/health")
        assert root_h.status_code == 200
        assert root_h.json()["status"] == "ok"
        assert root_h.json()["storage"] == "ephemeral_in_memory"

        h = client.get("/api/health")
        assert h.status_code == 200
        assert h.json()["status"] == "ok"
        assert h.json()["database"]["backend"] == "in_memory_ephemeral"

        # 2. Missing live data for XAUUSD does NOT fake live prices
        mkt = client.get("/api/market/ohlcv?symbol=XAUUSD&timeframe=1h&allow_demo=false")
        assert mkt.status_code == 200
        assert mkt.json()["overview"]["connection_status"] in ("DATA_UNAVAILABLE", "WEBHOOK_CACHE")

        # 3. Demo mode works explicitly and flags is_demo=True
        demo_mkt = client.get("/api/market/ohlcv?symbol=XAUUSD&timeframe=1h&allow_demo=true")
        assert demo_mkt.status_code == 200
        assert demo_mkt.json()["overview"]["is_demo"] is True
        assert demo_mkt.json()["overview"]["connection_status"] == "DEMO_MODE"

        # 4. Run full analysis on Demo data
        ana = client.post(
            "/api/analysis/run",
            json={"symbol": "XAUUSD", "timeframe": "1h", "allow_demo": True},
        )
        assert ana.status_code == 200
        ana_json = ana.json()
        assert ana_json["final_decision"] in ("BUY SETUP", "SELL SETUP", "WAIT", "NO VALID SETUP")
        assert ana_json["probability"]["model_validated"] is True
        assert 0.0 < ana_json["probability"]["estimated_win_probability"] < 1.0

        # 5. Journal automatically recorded the analysis
        j = client.get("/api/journal")
        assert j.status_code == 200
        assert len(j.json()) >= 1

        # 6. Webhook rejects wrong secret, accepts valid secret, and deduplicates repeat
        bad_wh = client.post(
            "/api/webhooks/tradingview",
            json={"symbol": "XAUUSD", "timeframe": "1h", "close": 2685.0, "secret": "wrong"},
        )
        assert bad_wh.status_code == 401

        payload = {
            "symbol": "OANDA:XAUUSD",
            "timeframe": "60",
            "close": 2685.0,
            "timestamp": "2026-02-15T12:00:00Z",
            "event": "analysis_trigger",
            "secret": "change-me-to-a-strong-random-secret",
        }
        ok_wh = client.post("/api/webhooks/tradingview", json=payload)
        assert ok_wh.status_code == 202
        assert ok_wh.json()["status"] == "queued"

        dup_wh = client.post("/api/webhooks/tradingview", json=payload)
        assert dup_wh.status_code == 202
        assert dup_wh.json()["status"] == "duplicate_ignored"

        # 7. Paper trading open & close
        order = client.post(
            "/api/paper/order",
            json={
                "symbol": "XAUUSD",
                "direction": "BUY",
                "entry_price": 2680.0,
                "stop_loss": 2670.0,
                "take_profit": 2700.0,
                "risk_percentage": 1.0,
                "is_demo_data": True,
            },
        )
        assert order.status_code == 200
        trade_id = order.json()["trade_id"]

        closed = client.post(f"/api/paper/close/{trade_id}?exit_price=2690.0")
        assert closed.status_code == 200
        assert closed.json()["realized_pnl"] > 0
