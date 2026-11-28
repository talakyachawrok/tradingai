"""Machine-learning Probability Estimation Engine with chronological validation, calibration & artifact persistence."""

from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from app.ml.features import (
    FEATURE_NAMES,
    MIN_FEATURE_BARS,
    LabeledSample,
    build_labeled_dataset,
    build_labeled_samples,
    extract_bar_features,
    precompute_indicator_bundle,
)
from app.models.analysis import (
    BiasDirection,
    CandlestickPattern,
    MarketStructureResult,
    ProbabilityEstimate,
    TradeLevels,
)
from app.models.market import OHLCVCandle, Timeframe

logger = logging.getLogger("ai_trading_analyzer")

MODEL_ARTIFACT_VERSION = "2.0.0"
DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_ARTIFACT_FILE = DEFAULT_ARTIFACT_DIR / "setup_probability_model.joblib"
DEFAULT_METADATA_FILE = DEFAULT_ARTIFACT_DIR / "model_metadata.json"

try:
    import joblib
    import numpy as np
    from sklearn.calibration import calibration_curve
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        accuracy_score,
        brier_score_loss,
        f1_score,
        log_loss,
        precision_score,
        recall_score,
        roc_auc_score,
    )
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    SKLEARN_AVAILABLE = True
except Exception:
    SKLEARN_AVAILABLE = False


def _logit_probs(probs: Any) -> Any:
    clipped = np.clip(probs, 1e-5, 1.0 - 1e-5)
    return np.log(clipped / (1.0 - clipped)).reshape(-1, 1)


def _apply_calibrator(calibrator: Any, raw_probs: Any) -> Any:
    if calibrator is None:
        return np.clip(raw_probs, 0.0, 1.0)
    return np.clip(calibrator.predict_proba(_logit_probs(raw_probs))[:, 1], 0.0, 1.0)


class ProbabilityModelManager:
    """Manages training, chronological walk-forward validation, calibration, artifact loading & prediction."""

    def __init__(
        self,
        artifact_path: Optional[Path] = None,
        auto_load: bool = True,
    ) -> None:
        self.artifact_path: Path = Path(artifact_path) if artifact_path else DEFAULT_ARTIFACT_FILE
        self.metadata_path: Path = self.artifact_path.parent / "model_metadata.json"
        self.validated: bool = False
        self.is_experimental: bool = True
        self.model_available: bool = False
        self.model_name: Optional[str] = None
        self.trained_on: Optional[str] = None
        self.calibration_method: Optional[str] = None
        self.model: Any = None
        self.calibrator: Any = None
        self.evaluation_report: Dict[str, Any] = self._unloaded_report()

        if auto_load:
            self.load_saved_model()

    @staticmethod
    def _unloaded_report(reason: str = "Trained model artifact not loaded yet.") -> Dict[str, Any]:
        return {
            "validated": False,
            "is_experimental": True,
            "model_available": False,
            "status": "PROBABILITY MODEL NOT YET VALIDATED",
            "reason": reason,
            "sklearn_available": SKLEARN_AVAILABLE,
            "feature_count": len(FEATURE_NAMES),
            "feature_names": FEATURE_NAMES,
        }

    def load_saved_model(self) -> bool:
        """Load persisted model pipeline, calibrator, and validation report from disk."""
        if not SKLEARN_AVAILABLE:
            self.model_available = False
            self.validated = False
            self.evaluation_report = self._unloaded_report("scikit-learn/joblib unavailable in runtime.")
            return False

        if not self.artifact_path.exists():
            self.model_available = False
            self.validated = False
            self.evaluation_report = self._unloaded_report(
                f"No saved model artifact found at {self.artifact_path.name}."
            )
            return False

        try:
            payload = joblib.load(self.artifact_path)
            if not isinstance(payload, dict):
                raise ValueError("Invalid model artifact format (expected dict payload).")
            saved_features = payload.get("feature_names")
            pipeline = payload.get("pipeline")
            if saved_features != FEATURE_NAMES:
                raise ValueError(
                    f"Feature schema mismatch (expected {len(FEATURE_NAMES)} features, got {len(saved_features or [])})."
                )
            if pipeline is None or not hasattr(pipeline, "predict_proba"):
                raise ValueError("Loaded artifact lacks a valid predict_proba pipeline.")

            report = dict(payload.get("evaluation_report") or {})
            self.model = pipeline
            self.calibrator = payload.get("calibrator")
            self.model_name = payload.get("model_name") or report.get("model_type")
            self.trained_on = payload.get("trained_on") or report.get("trained_on")
            self.calibration_method = payload.get("calibration_method") or report.get("calibration_method")
            self.validated = bool(payload.get("validated", report.get("validated", False)))
            self.is_experimental = bool(payload.get("is_experimental", report.get("is_experimental", True)))
            self.model_available = True
            self.evaluation_report = {
                **report,
                "artifact_loaded": True,
                "artifact_path": str(self.artifact_path.name),
                "model_available": True,
                "feature_count": len(FEATURE_NAMES),
                "feature_names": FEATURE_NAMES,
            }
            logger.info(
                "Loaded ML probability artifact %s (model=%s, validated=%s, experimental=%s, trained_on=%s)",
                self.artifact_path.name,
                self.model_name,
                self.validated,
                self.is_experimental,
                self.trained_on,
            )
            return True
        except Exception as exc:
            logger.warning("Failed to load ML model artifact %s: %s", self.artifact_path, exc)
            self.model = None
            self.calibrator = None
            self.model_available = False
            self.validated = False
            self.is_experimental = True
            self.evaluation_report = self._unloaded_report(f"Artifact load error: {exc}")
            return False

    def save_saved_model(self) -> Path:
        """Persist trained pipeline, calibrator, and JSON evaluation metadata."""
        if self.model is None or not SKLEARN_AVAILABLE:
            raise RuntimeError("Cannot save ML artifact: no trained model in memory.")
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "artifact_version": MODEL_ARTIFACT_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "model_name": self.model_name,
            "feature_names": FEATURE_NAMES,
            "pipeline": self.model,
            "calibrator": self.calibrator,
            "calibration_method": self.calibration_method,
            "validated": self.validated,
            "is_experimental": self.is_experimental,
            "trained_on": self.trained_on,
            "evaluation_report": self.evaluation_report,
        }
        joblib.dump(payload, self.artifact_path, compress=3)
        with self.metadata_path.open("w", encoding="utf-8") as fp:
            json.dump(self.evaluation_report, fp, indent=2)
        return self.artifact_path

    def train_and_validate(
        self,
        candles: List[OHLCVCandle],
        symbol: str,
        timeframe: Timeframe,
        model_type: str = "logistic_regression",
        horizon_bars: int = 24,
        is_demo: bool = False,
        data_source: str = "market_feed",
        save_artifact: bool = False,
    ) -> Dict[str, Any]:
        """Train and chronologically validate on a single instrument's historical candles."""
        samples = build_labeled_samples(candles, symbol=symbol, horizon_bars=horizon_bars)
        dataset_label = f"{symbol} ({timeframe.value}, {data_source})"
        return self.train_from_samples(
            samples=samples,
            dataset_label=dataset_label,
            symbol=symbol,
            timeframe=timeframe,
            model_type=model_type,
            horizon_bars=horizon_bars,
            is_demo=is_demo,
            save_artifact=save_artifact,
        )

    def train_multi_symbol(
        self,
        candles_by_symbol: Dict[str, List[OHLCVCandle]],
        timeframe: Timeframe,
        model_type: str = "logistic_regression",
        horizon_bars: int = 24,
        data_source: str = "binance_public",
        is_demo: bool = False,
        save_artifact: bool = True,
    ) -> Dict[str, Any]:
        """Build per-symbol causal samples (zero cross-symbol leakage), merge chronologically, train & save."""
        all_samples: List[LabeledSample] = []
        included_symbols: List[str] = []
        for sym, sym_candles in candles_by_symbol.items():
            sym_samples = build_labeled_samples(sym_candles, symbol=sym, horizon_bars=horizon_bars)
            if sym_samples:
                included_symbols.extend([sym] * 1)
                all_samples.extend(sym_samples)

        dataset_label = f"{', '.join(included_symbols)} ({timeframe.value}, {data_source})"
        return self.train_from_samples(
            samples=all_samples,
            dataset_label=dataset_label,
            symbol=",".join(included_symbols),
            timeframe=timeframe,
            model_type=model_type,
            horizon_bars=horizon_bars,
            is_demo=is_demo,
            save_artifact=save_artifact,
        )

    def train_from_samples(
        self,
        samples: List[LabeledSample],
        dataset_label: str,
        symbol: str,
        timeframe: Timeframe,
        model_type: str = "logistic_regression",
        horizon_bars: int = 24,
        is_demo: bool = False,
        save_artifact: bool = False,
    ) -> Dict[str, Any]:
        """
        Train on chronologically ordered historical setup samples:
        - 60% train (preprocessor + base estimator fitted strictly here)
        - 20% chronological validation (Platt sigmoid probability calibrator fitted here)
        - 20% holdout chronological test (unbiased out-of-sample calibrated metrics)
        + Expanding walk-forward folds.
        """
        if not SKLEARN_AVAILABLE:
            return {
                "validated": False,
                "is_experimental": True,
                "status": "PROBABILITY MODEL NOT YET VALIDATED",
                "error": "scikit-learn is not installed in the runtime environment.",
            }

        ordered = sorted(samples, key=lambda s: s.timestamp)
        y_all = [s.label for s in ordered]
        if len(ordered) < 90 or len(set(y_all)) < 2:
            return {
                "validated": False,
                "is_experimental": True,
                "status": "PROBABILITY MODEL NOT YET VALIDATED",
                "samples": len(ordered),
                "error": "Insufficient historical samples (need >= 90 labeled samples with both win & loss outcomes) for chronological validation.",
            }

        X = np.array([s.features for s in ordered], dtype=float)
        y = np.array(y_all, dtype=int)
        regimes = [s.regime for s in ordered]
        n = len(X)

        train_end = int(n * 0.60)
        val_end = int(n * 0.80)
        X_train, y_train = X[:train_end], y[:train_end]
        X_val, y_val = X[train_end:val_end], y[train_end:val_end]
        X_test, y_test = X[val_end:], y[val_end:]
        regimes_test = regimes[val_end:]

        if len(set(y_train)) < 2 or len(set(y_test)) < 2:
            return {
                "validated": False,
                "is_experimental": True,
                "status": "PROBABILITY MODEL NOT YET VALIDATED",
                "samples": n,
                "error": "Chronological split lacks both outcome classes in train/test segments.",
            }

        clf = self._build_estimator(model_type)
        clf.fit(X_train, y_train)

        raw_val_probs = clf.predict_proba(X_val)[:, 1]
        raw_test_probs = clf.predict_proba(X_test)[:, 1]

        # Fit out-of-sample Platt sigmoid calibrator strictly on chronological validation split
        calibrator = None
        calibration_method = "uncalibrated (single validation class)"
        if len(set(y_val)) >= 2 and len(y_val) >= 20:
            calibrator = LogisticRegression(C=1.0, max_iter=300, random_state=42)
            calibrator.fit(_logit_probs(raw_val_probs), y_val)
            calibration_method = "platt_sigmoid_val_split"

        cal_val_probs = _apply_calibrator(calibrator, raw_val_probs)
        cal_test_probs = _apply_calibrator(calibrator, raw_test_probs)
        test_preds = (cal_test_probs >= 0.5).astype(int)

        # Walk-forward expanding window validation (3 chronological folds)
        wf_accuracies: List[float] = []
        fold_size = max(20, (n - train_end) // 3)
        for fold_start in range(train_end, n - 10, fold_size):
            fold_end = min(n, fold_start + fold_size)
            if len(set(y[:fold_start])) < 2:
                continue
            wf_clf = self._build_estimator(model_type)
            wf_clf.fit(X[:fold_start], y[:fold_start])
            wf_preds = (wf_clf.predict_proba(X[fold_start:fold_end])[:, 1] >= 0.5).astype(int)
            wf_accuracies.append(round(float(accuracy_score(y[fold_start:fold_end], wf_preds)), 4))

        roc_auc = round(float(roc_auc_score(y_test, cal_test_probs)), 4) if len(set(y_test)) > 1 else None
        brier_cal = round(float(brier_score_loss(y_test, cal_test_probs)), 4)
        brier_raw = round(float(brier_score_loss(y_test, raw_test_probs)), 4)
        logloss_cal = round(float(log_loss(y_test, np.clip(cal_test_probs, 1e-5, 1 - 1e-5))), 4)
        prob_true, prob_pred = calibration_curve(y_test, cal_test_probs, n_bins=5, strategy="uniform")

        regime_perf: Dict[str, Dict[str, Any]] = {}
        for r in sorted(set(regimes_test)):
            idxs = [k for k, rv in enumerate(regimes_test) if rv == r]
            if idxs:
                r_y = y_test[idxs]
                r_p = test_preds[idxs]
                regime_perf[r] = {
                    "samples": len(idxs),
                    "accuracy": round(float(accuracy_score(r_y, r_p)), 4),
                    "positive_rate": round(float(r_y.mean()), 4),
                }

        # Honest experimental gating: demo data, small sample, or weak discrimination/calibration => experimental
        passes_quality = (
            not is_demo
            and n >= 200
            and roc_auc is not None
            and roc_auc >= 0.51
            and brier_cal <= 0.27
        )
        is_experimental = not passes_quality
        status_text = (
            f"VALIDATED CALIBRATED ({model_type})"
            if passes_quality
            else f"EXPERIMENTAL ({model_type})"
        )

        self.model = clf
        self.calibrator = calibrator
        self.calibration_method = calibration_method
        self.model_name = model_type
        self.trained_on = dataset_label
        self.validated = True
        self.is_experimental = is_experimental
        self.model_available = True
        self.evaluation_report = {
            "validated": True,
            "is_experimental": is_experimental,
            "model_available": True,
            "artifact_loaded": save_artifact,
            "status": status_text,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "trained_on": dataset_label,
            "symbol": symbol,
            "timeframe": timeframe.value,
            "model_type": model_type,
            "horizon_bars": horizon_bars,
            "is_demo": is_demo,
            "calibration_method": calibration_method,
            "feature_count": len(FEATURE_NAMES),
            "feature_names": FEATURE_NAMES,
            "samples_total": n,
            "base_positive_rate": round(float(y.mean()), 4),
            "split": {"train": len(X_train), "validation": len(X_val), "test": len(X_test)},
            "test_metrics": {
                "accuracy": round(float(accuracy_score(y_test, test_preds)), 4),
                "precision": round(float(precision_score(y_test, test_preds, zero_division=0)), 4),
                "recall": round(float(recall_score(y_test, test_preds, zero_division=0)), 4),
                "f1": round(float(f1_score(y_test, test_preds, zero_division=0)), 4),
                "roc_auc": roc_auc,
                "brier_score": brier_cal,
                "raw_brier_score": brier_raw,
                "log_loss": logloss_cal,
                "val_brier_score": round(float(brier_score_loss(y_val, cal_val_probs)), 4),
            },
            "walk_forward_fold_accuracies": wf_accuracies,
            "calibration": [
                {"predicted_mean": round(float(pp), 3), "empirical_freq": round(float(pt), 3)}
                for pt, pp in zip(prob_true, prob_pred)
            ],
            "by_regime": regime_perf,
            "leakage_note": (
                "Strictly chronological 60/20/20 split (preprocessor fitted on train, Platt calibration fitted "
                "on validation, evaluated on holdout test) + expanding walk-forward; intrabar SL/TP conflicts labeled as loss."
            ),
        }

        if save_artifact:
            path = self.save_saved_model()
            self.evaluation_report["artifact_path"] = str(path.name)

        return self.evaluation_report

    def predict(
        self,
        candles: List[OHLCVCandle],
        candidate_dir: Optional[BiasDirection] = None,
        levels: Optional[TradeLevels] = None,
        patterns: Optional[List[CandlestickPattern]] = None,
        structure: Optional[MarketStructureResult] = None,
    ) -> ProbabilityEstimate:
        """
        Compute calibrated probability of TP1-before-SL for the latest bar/setup.
        Never fabricates hardcoded percentages or crashes when data/model is unavailable.
        """
        if not SKLEARN_AVAILABLE or not self.model_available or self.model is None or not self.validated:
            return ProbabilityEstimate(
                model_validated=False,
                is_experimental=True,
                model_available=False,
                status_label="ML UNAVAILABLE: TRAINED MODEL NOT LOADED",
                estimated_win_probability=None,
                explanation=(
                    "No trained and validated ML artifact is currently loaded. "
                    "Train & validate a model in the Probability Lab or verify deployment artifacts."
                ),
            )

        if len(candles) < MIN_FEATURE_BARS:
            return ProbabilityEstimate(
                model_validated=self.validated,
                is_experimental=self.is_experimental,
                model_available=True,
                model_name=self.model_name,
                trained_on=self.trained_on,
                status_label="ML UNAVAILABLE: INSUFFICIENT CANDLE HISTORY",
                estimated_win_probability=None,
                explanation=(
                    f"Need at least {MIN_FEATURE_BARS} valid candles to extract rolling ML features "
                    f"(received {len(candles)})."
                ),
                validation_metrics=self.evaluation_report.get("test_metrics", {}),
            )

        try:
            bundle = precompute_indicator_bundle(candles)
            feat = extract_bar_features(
                candles=candles,
                idx=len(candles) - 1,
                bundle=bundle,
                candidate_dir=candidate_dir,
                levels=levels,
                patterns=patterns,
                structure=structure,
            )
            if feat is None:
                return ProbabilityEstimate(
                    model_validated=self.validated,
                    is_experimental=self.is_experimental,
                    model_available=True,
                    model_name=self.model_name,
                    trained_on=self.trained_on,
                    status_label="ML UNAVAILABLE: INVALID OR INCOMPLETE FEATURES",
                    estimated_win_probability=None,
                    explanation="Latest indicators or OHLC values were incomplete or non-finite for ML inference.",
                    validation_metrics=self.evaluation_report.get("test_metrics", {}),
                )

            vec, regime = feat
            arr = np.array([vec], dtype=float)
            if not np.all(np.isfinite(arr)):
                return ProbabilityEstimate(
                    model_validated=self.validated,
                    is_experimental=self.is_experimental,
                    model_available=True,
                    model_name=self.model_name,
                    trained_on=self.trained_on,
                    status_label="ML UNAVAILABLE: NON-FINITE INPUT FEATURES",
                    estimated_win_probability=None,
                    explanation="Extracted feature vector contained NaN or infinite values.",
                    validation_metrics=self.evaluation_report.get("test_metrics", {}),
                )

            raw_prob = float(self.model.predict_proba(arr)[0, 1])
            cal_prob = float(_apply_calibrator(self.calibrator, np.array([raw_prob]))[0])
            if not math.isfinite(cal_prob) or not math.isfinite(raw_prob):
                raise ValueError("Model returned non-finite probability.")

            status_prefix = "EXPERIMENTAL" if self.is_experimental else "VALIDATED MODEL"
            cal_tag = "calibrated" if self.calibrator is not None else "uncalibrated"
            rr_val = vec[FEATURE_NAMES.index("rr_planned")]
            dir_label = "bullish/long" if vec[-1] > 0 else "bearish/short"
            exp_note = (
                " Marked EXPERIMENTAL (requires larger multi-asset out-of-sample validation)."
                if self.is_experimental
                else ""
            )

            return ProbabilityEstimate(
                model_validated=True,
                is_experimental=self.is_experimental,
                model_available=True,
                status_label=f"{status_prefix} ({self.model_name}, {cal_tag})",
                model_name=self.model_name,
                estimated_win_probability=round(cal_prob, 4),
                raw_probability=round(raw_prob, 4),
                calibration_method=self.calibration_method,
                trained_on=self.trained_on,
                explanation=(
                    f"Model evaluated {dir_label} setup in {regime} regime with {rr_val:.2f}R planned target "
                    f"(trained on {self.trained_on or 'historical candles'}).{exp_note}"
                ),
                validation_metrics=self.evaluation_report.get("test_metrics", {}),
            )
        except Exception as exc:
            logger.exception("ML prediction failed gracefully: %s", exc)
            return ProbabilityEstimate(
                model_validated=False,
                is_experimental=True,
                model_available=self.model_available,
                model_name=self.model_name,
                status_label="ML UNAVAILABLE: PREDICTION ERROR",
                estimated_win_probability=None,
                explanation=f"ML inference error handled safely without affecting risk rules: {exc}",
            )

    @staticmethod
    def _build_estimator(model_type: str) -> Any:
        mt = model_type.lower().strip()
        if mt == "random_forest":
            clf: Any = RandomForestClassifier(
                n_estimators=160,
                max_depth=5,
                min_samples_leaf=12,
                random_state=42,
            )
        elif mt == "gradient_boosting":
            clf = GradientBoostingClassifier(
                n_estimators=90,
                max_depth=3,
                learning_rate=0.05,
                subsample=0.85,
                random_state=42,
            )
        else:
            clf = LogisticRegression(C=0.5, max_iter=800, random_state=42)

        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("clf", clf),
            ]
        )


probability_manager = ProbabilityModelManager()
