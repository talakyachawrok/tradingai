"""End-to-end verification tests for ML feature extraction, calibration, artifact loading, and API integration."""

from copy import deepcopy
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from app.analysis.decision import evaluate_trade_decision
from app.analysis.pipeline import run_full_analysis
from app.data.providers.demo_historical import DemoHistoricalProvider
from app.data.validator import validate_and_clean_candles
from app.database.connection import db_store
from app.main import app
from app.ml.features import (
    FEATURE_NAMES,
    MIN_FEATURE_BARS,
    extract_bar_features,
    precompute_indicator_bundle,
)
from app.ml.probability import DEFAULT_ARTIFACT_FILE, ProbabilityModelManager, probability_manager
from app.models.analysis import BiasDirection, DecisionType
from app.models.market import OHLCVCandle, Timeframe


@pytest.mark.asyncio
async def test_ml_features_are_strictly_leakage_free():
    provider = DemoHistoricalProvider()
    res = await provider.fetch_candles("BTCUSD", Timeframe.H1, limit=200)
    candles, _ = validate_and_clean_candles(res.raw_candles, Timeframe.H1, check_staleness=False)

    idx = 120
    bundle_before = precompute_indicator_bundle(candles)
    feat_before = extract_bar_features(candles, idx, bundle_before)
    assert feat_before is not None
    vec_before, _ = feat_before
    assert len(vec_before) == len(FEATURE_NAMES)

    # Perturb all future candles (> idx) dramatically; feature vector at idx must be bit-identical
    mutated = deepcopy(candles)
    for j in range(idx + 1, len(mutated)):
        mutated[j].open *= 1.8
        mutated[j].high *= 2.1
        mutated[j].low *= 0.4
        mutated[j].close *= 1.9

    bundle_after = precompute_indicator_bundle(mutated)
    feat_after = extract_bar_features(mutated, idx, bundle_after)
    assert feat_after is not None
    vec_after, _ = feat_after
    assert vec_before == vec_after


def test_ml_artifact_loads_and_handles_missing_and_insufficient_data(tmp_path: Path):
    assert DEFAULT_ARTIFACT_FILE.exists(), "Pre-trained production artifact must exist in app/ml/artifacts/"
    prod_mgr = ProbabilityModelManager()
    assert prod_mgr.model_available is True
    assert prod_mgr.validated is True
    assert prod_mgr.calibration_method == "platt_sigmoid_val_split"

    # Missing artifact stays gracefully unavailable without fake numbers
    empty_mgr = ProbabilityModelManager(artifact_path=tmp_path / "missing.joblib", auto_load=True)
    assert empty_mgr.model_available is False
    assert empty_mgr.validated is False

    # Insufficient candle history returns ML UNAVAILABLE without crashing
    import asyncio

    provider = DemoHistoricalProvider()
    res = asyncio.run(provider.fetch_candles("XAUUSD", Timeframe.H1, limit=80))
    candles, _ = validate_and_clean_candles(res.raw_candles, Timeframe.H1, check_staleness=False)

    short_pred = prod_mgr.predict(candles[:35])
    assert short_pred.estimated_win_probability is None
    assert "INSUFFICIENT" in short_pred.status_label

    unavail_pred = empty_mgr.predict(candles)
    assert unavail_pred.estimated_win_probability is None
    assert "UNAVAILABLE" in unavail_pred.status_label

    # Corrupt OHLC (close <= 0 simulated via model_copy) is rejected cleanly by feature validator
    bad_candles = deepcopy(candles)
    bad_candles[-1] = bad_candles[-1].model_copy(update={"close": 0.0})
    corrupt_pred = prod_mgr.predict(bad_candles)
    assert corrupt_pred.estimated_win_probability is None
    assert "ML UNAVAILABLE" in corrupt_pred.status_label

    # Valid candles produce real calibrated probability distinct from hardcoded constants
    valid_pred = prod_mgr.predict(candles)
    assert valid_pred.model_validated is True
    assert valid_pred.estimated_win_probability is not None
    assert 0.0 < valid_pred.estimated_win_probability < 1.0
    assert valid_pred.raw_probability is not None
    assert "statistical" in valid_pred.definition.lower()


@pytest.mark.asyncio
async def test_ml_save_reload_roundtrip_and_experimental_demo_flag(tmp_path: Path):
    provider = DemoHistoricalProvider()
    res = await provider.fetch_candles("XAUUSD", Timeframe.H1, limit=600)
    candles, _ = validate_and_clean_candles(res.raw_candles, Timeframe.H1, check_staleness=False)

    artifact_file = tmp_path / "test_model.joblib"
    mgr = ProbabilityModelManager(artifact_path=artifact_file, auto_load=False)
    report = mgr.train_and_validate(
        candles=candles,
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        model_type="logistic_regression",
        horizon_bars=12,
        is_demo=True,
        data_source="demo_historical",
        save_artifact=True,
    )
    assert report["validated"] is True
    assert report["is_experimental"] is True
    assert artifact_file.exists()

    reloaded = ProbabilityModelManager(artifact_path=artifact_file, auto_load=True)
    assert reloaded.model_available is True
    assert reloaded.validated is True
    assert reloaded.is_experimental is True
    assert reloaded.predict(candles).estimated_win_probability == mgr.predict(candles).estimated_win_probability


def test_ml_routes_and_analyzer_integration():
    db_store.reset()
    with TestClient(app) as client:
        h = client.get("/api/health").json()
        assert h["ml_model_available"] is True
        assert h["ml_model_validated"] is True

        st = client.get("/api/ml/status")
        assert st.status_code == 200
        st_json = st.json()
        assert st_json["artifact_loaded"] is True
        assert st_json["feature_count"] == len(FEATURE_NAMES)
        assert st_json["current_runtime"]["validated"] is True

        # Analysis integrates calibrated ML output while keeping risk rules in control
        ana = client.post(
            "/api/analysis/run",
            json={"symbol": "XAUUSD", "timeframe": "1h", "allow_demo": True, "limit": 120},
        )
        assert ana.status_code == 200
        body = ana.json()
        prob = body["probability"]
        assert prob["model_available"] is True
        assert prob["model_validated"] is True
        assert 0.0 < prob["estimated_win_probability"] < 1.0
        assert prob["calibration_method"] == "platt_sigmoid_val_split"
        assert prob["explanation"]

        # Insufficient training candles cleanly fail with 422 without corrupting loaded model
        bad_train = client.post(
            "/api/ml/train",
            json={"symbol": "XAUUSD", "timeframe": "1h", "model_type": "logistic_regression", "allow_demo": False},
        )
        assert bad_train.status_code == 422
        assert client.get("/api/ml/status").json()["artifact_loaded"] is True

        # Training on demo historical candles succeeds and marks report as experimental
        ok_train = client.post(
            "/api/ml/train",
            json={"symbol": "XAUUSD", "timeframe": "1h", "model_type": "random_forest", "horizon_bars": 12, "allow_demo": True},
        )
        assert ok_train.status_code == 200
        assert ok_train.json()["validated"] is True
        assert ok_train.json()["is_experimental"] is True

        # Restore production baseline artifact on singleton so subsequent tests stay deterministic
        assert probability_manager.load_saved_model() is True
        assert probability_manager.is_experimental is False
