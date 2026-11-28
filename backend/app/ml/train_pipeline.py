"""Reproducible ML training pipeline using real historical market OHLCV data."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, List, Optional
import httpx
from app.core.config import get_settings
from app.core.instruments import instrument_registry, normalize_symbol
from app.core.logging_config import logger
from app.data.providers.binance_public import BinancePublicProvider
from app.data.providers.twelvedata import TwelveDataProvider
from app.data.validator import validate_and_clean_candles
from app.ml.probability import DEFAULT_ARTIFACT_FILE, ProbabilityModelManager
from app.models.market import DataConnectionStatus, OHLCVCandle, Timeframe

DEFAULT_TRAINING_SYMBOLS = ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD"]


async def fetch_paginated_binance_history(
    symbol: str,
    timeframe: Timeframe,
    pages: int = 3,
    per_page: int = 1000,
) -> List[OHLCVCandle]:
    """
    Fetch multi-page real historical OHLCV candles from Binance public klines API,
    walking backwards via `endTime` so up to 3,000+ real chronological bars are gathered.
    """
    spec = instrument_registry.get(normalize_symbol(symbol))
    bsym = spec.provider_symbols.get("binance_public") if spec else None
    if not bsym:
        return []

    raw_rows: List[dict] = []
    end_time_ms: Optional[int] = None
    interval = timeframe.value

    async with httpx.AsyncClient(timeout=15.0) as client:
        for _ in range(pages):
            params: Dict[str, str | int] = {
                "symbol": bsym,
                "interval": interval,
                "limit": per_page,
            }
            if end_time_ms is not None:
                params["endTime"] = end_time_ms
            resp = await client.get("https://api.binance.com/api/v3/klines", params=params)
            if resp.status_code != 200:
                logger.warning("Binance history page fetch %s returned %s", bsym, resp.status_code)
                break
            rows = resp.json()
            if not rows or not isinstance(rows, list):
                break
            earliest_open_ms = int(rows[0][0])
            page_candles = [
                {
                    "timestamp": datetime.fromtimestamp(int(r[0]) / 1000.0, tz=timezone.utc).isoformat(),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5]),
                }
                for r in rows
            ]
            raw_rows.extend(page_candles)
            if len(rows) < per_page:
                break
            end_time_ms = earliest_open_ms - 1

    if not raw_rows:
        return []
    cleaned, _ = validate_and_clean_candles(raw_rows, timeframe=timeframe, check_staleness=False)
    return cleaned


async def fetch_real_training_corpus(
    symbols: List[str],
    timeframe: Timeframe = Timeframe.H1,
    pages: int = 3,
) -> Dict[str, List[OHLCVCandle]]:
    """Gather validated real historical candles per symbol without fabricating any rows."""
    cfg = get_settings()
    binance = BinancePublicProvider()
    twelvedata = TwelveDataProvider()
    corpus: Dict[str, List[OHLCVCandle]] = {}

    for sym in symbols:
        norm = normalize_symbol(sym)
        candles = await fetch_paginated_binance_history(norm, timeframe=timeframe, pages=pages)
        if len(candles) >= 150:
            corpus[norm] = candles
            continue

        # Fallback to single-shot Kraken/Binance public provider
        res = await binance.fetch_candles(norm, timeframe, limit=1000)
        if res.connection_status == DataConnectionStatus.LIVE and len(res.raw_candles) >= 150:
            cleaned, _ = validate_and_clean_candles(res.raw_candles, timeframe=timeframe, check_staleness=False)
            if len(cleaned) >= 150:
                corpus[norm] = cleaned
                continue

        # Optional TwelveData if key is present for FX / Gold / Stocks
        if cfg.twelvedata_api_key.strip():
            td_res = await twelvedata.fetch_candles(norm, timeframe, limit=1000)
            if td_res.connection_status == DataConnectionStatus.LIVE and len(td_res.raw_candles) >= 150:
                cleaned, _ = validate_and_clean_candles(
                    td_res.raw_candles, timeframe=timeframe, check_staleness=False
                )
                if len(cleaned) >= 150:
                    corpus[norm] = cleaned

    return corpus


async def run_training_pipeline(
    symbols: List[str],
    timeframe: Timeframe = Timeframe.H1,
    pages: int = 3,
    horizon_bars: int = 24,
    model_type: Optional[str] = None,
    artifact_path: Path = DEFAULT_ARTIFACT_FILE,
) -> dict:
    """
    Fetch real historical OHLCV market data, train candidate models chronologically,
    compare holdout Brier score + ROC-AUC, calibrate probabilities on validation split,
    and save the winning artifact.
    """
    corpus = await fetch_real_training_corpus(symbols=symbols, timeframe=timeframe, pages=pages)
    if not corpus:
        raise RuntimeError(
            "Unable to fetch real historical market candles for training. Check network/API connectivity."
        )

    candidates = [model_type] if model_type else ["logistic_regression", "random_forest", "gradient_boosting"]
    best_mgr: Optional[ProbabilityModelManager] = None
    best_score: float = float("-inf")
    comparison: List[dict] = []

    for candidate in candidates:
        mgr = ProbabilityModelManager(artifact_path=artifact_path, auto_load=False)
        report = mgr.train_multi_symbol(
            candles_by_symbol=corpus,
            timeframe=timeframe,
            model_type=candidate,
            horizon_bars=horizon_bars,
            data_source="binance_public",
            is_demo=False,
            save_artifact=False,
        )
        metrics = report.get("test_metrics") or {}
        brier = metrics.get("brier_score", 0.5)
        auc = metrics.get("roc_auc") or 0.5
        # Prefer lower Brier calibration error & stronger discrimination
        composite = (auc - 0.5) - (brier - 0.25)
        comparison.append(
            {
                "model_type": candidate,
                "validated": report.get("validated"),
                "is_experimental": report.get("is_experimental"),
                "test_metrics": metrics,
                "composite_score": round(float(composite), 5),
            }
        )
        if report.get("validated") and composite > best_score:
            best_score = composite
            best_mgr = mgr

    if best_mgr is None:
        raise RuntimeError(f"All candidate models failed chronological validation: {comparison}")

    saved_path = best_mgr.save_saved_model()
    best_mgr.evaluation_report["artifact_loaded"] = True
    best_mgr.evaluation_report["artifact_path"] = str(saved_path.name)
    best_mgr.evaluation_report["model_selection_comparison"] = comparison
    # Update JSON metadata file with comparison table too
    best_mgr.save_saved_model()
    return best_mgr.evaluation_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train & calibrate AI Trading Analyzer ML model on real data.")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_TRAINING_SYMBOLS)
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--horizon", type=int, default=24)
    parser.add_argument("--model-type", default=None)
    args = parser.parse_args()

    tf = Timeframe(args.timeframe)
    report = asyncio.run(
        run_training_pipeline(
            symbols=args.symbols,
            timeframe=tf,
            pages=args.pages,
            horizon_bars=args.horizon,
            model_type=args.model_type,
        )
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
