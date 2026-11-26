"""Machine-learning Probability Estimation Engine with chronological & walk-forward validation."""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from app.indicators.engine import (
    compute_atr_series,
    compute_ema_series,
    compute_rsi_series,
)
from app.models.analysis import ProbabilityEstimate
from app.models.market import OHLCVCandle, Timeframe
from app.patterns.engine import compute_candle_metrics

try:
    import numpy as np
    from sklearn.calibration import calibration_curve
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        accuracy_score,
        brier_score_loss,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    SKLEARN_AVAILABLE = True
except Exception:
    SKLEARN_AVAILABLE = False


FEATURE_NAMES = [
    "body_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "candle_dir",
    "rsi_14",
    "atr_pct",
    "ema20_dist_atr",
    "ema50_dist_atr",
    "ema20_50_spread_atr",
    "ret_5_atr",
    "stop_dist_atr",
    "target_dist_atr",
    "rr_planned",
    "session_utc_hour_sin",
    "session_utc_hour_cos",
]


def extract_bar_features(
    candles: List[OHLCVCandle],
    idx: int,
    ema20: List[Optional[float]],
    ema50: List[Optional[float]],
    rsi14: List[Optional[float]],
    atr14: List[Optional[float]],
    stop_mult: float = 1.5,
    target_mult: float = 2.5,
) -> Optional[Tuple[List[float], str]]:
    """Extract leakage-free feature vector strictly from bars <= idx."""
    if idx < 50 or atr14[idx] is None or rsi14[idx] is None or ema20[idx] is None or ema50[idx] is None:
        return None
    atr = max(float(atr14[idx]), 1e-12)
    c = candles[idx]
    m = compute_candle_metrics(c)
    candle_dir = 1.0 if m.is_bullish else (-1.0 if m.is_bearish else 0.0)
    atr_pct = (atr / c.close) * 100.0
    e20_dist = (c.close - float(ema20[idx])) / atr
    e50_dist = (c.close - float(ema50[idx])) / atr
    spread = (float(ema20[idx]) - float(ema50[idx])) / atr
    ret_5 = (c.close - candles[idx - 5].close) / atr
    hr = c.timestamp.hour
    hr_sin = math.sin(2.0 * math.pi * hr / 24.0)
    hr_cos = math.cos(2.0 * math.pi * hr / 24.0)
    rr = target_mult / stop_mult

    regime = "trending_bull" if spread > 0.4 else ("trending_bear" if spread < -0.4 else "ranging")
    vec = [
        m.body_ratio,
        m.upper_wick_ratio,
        m.lower_wick_ratio,
        candle_dir,
        float(rsi14[idx]),
        atr_pct,
        e20_dist,
        e50_dist,
        spread,
        ret_5,
        stop_mult,
        target_mult,
        rr,
        hr_sin,
        hr_cos,
    ]
    return vec, regime


def build_labeled_dataset(
    candles: List[OHLCVCandle],
    horizon_bars: int = 24,
    stop_atr_mult: float = 1.5,
    target_atr_mult: float = 2.5,
) -> Tuple[List[List[float]], List[int], List[str]]:
    """
    Create historical dataset where label=1 iff TP is reached before SL within `horizon_bars`
    in the direction of EMA20/EMA50 bias (conservative: if both touched same bar -> label=0).
    """
    closes = [c.close for c in candles]
    ema20 = compute_ema_series(closes, 20)
    ema50 = compute_ema_series(closes, 50)
    rsi14 = compute_rsi_series(closes, 14)
    atr14 = compute_atr_series(candles, 14)

    X: List[List[float]] = []
    y: List[int] = []
    regimes: List[str] = []

    for i in range(50, len(candles) - horizon_bars):
        feat = extract_bar_features(
            candles, i, ema20, ema50, rsi14, atr14, stop_atr_mult, target_atr_mult
        )
        if feat is None:
            continue
        vec, regime = feat
        atr = float(atr14[i])  # type: ignore[arg-type]
        entry = candles[i].close
        is_long = float(ema20[i]) >= float(ema50[i])  # type: ignore[arg-type]
        if is_long:
            sl = entry - atr * stop_atr_mult
            tp = entry + atr * target_atr_mult
        else:
            sl = entry + atr * stop_atr_mult
            tp = entry - atr * target_atr_mult

        label = 0
        for j in range(i + 1, i + 1 + horizon_bars):
            bar = candles[j]
            if is_long:
                sl_hit = bar.low <= sl
                tp_hit = bar.high >= tp
            else:
                sl_hit = bar.high >= sl
                tp_hit = bar.low <= tp
            # Conservative tie-breaking: SL assumed first if both in same bar
            if sl_hit:
                label = 0
                break
            if tp_hit:
                label = 1
                break

        X.append(vec)
        y.append(label)
        regimes.append(regime)

    return X, y, regimes


class ProbabilityModelManager:
    """Manages training, chronological walk-forward validation, and strict readiness gating."""

    def __init__(self) -> None:
        self.validated: bool = False
        self.model_name: Optional[str] = None
        self.model: Any = None
        self.evaluation_report: Dict[str, Any] = {
            "validated": False,
            "status": "PROBABILITY MODEL NOT YET VALIDATED",
            "sklearn_available": SKLEARN_AVAILABLE,
        }

    def train_and_validate(
        self,
        candles: List[OHLCVCandle],
        symbol: str,
        timeframe: Timeframe,
        model_type: str = "logistic_regression",
        horizon_bars: int = 24,
    ) -> Dict[str, Any]:
        if not SKLEARN_AVAILABLE:
            self.validated = False
            self.evaluation_report = {
                "validated": False,
                "status": "PROBABILITY MODEL NOT YET VALIDATED",
                "error": "scikit-learn is not installed in the runtime environment.",
            }
            return self.evaluation_report

        X_raw, y_raw, regimes = build_labeled_dataset(candles, horizon_bars=horizon_bars)
        if len(X_raw) < 90 or len(set(y_raw)) < 2:
            self.validated = False
            self.evaluation_report = {
                "validated": False,
                "status": "PROBABILITY MODEL NOT YET VALIDATED",
                "samples": len(X_raw),
                "error": "Insufficient historical samples (need >= 90 labeled samples with both win & loss outcomes) for chronological validation.",
            }
            return self.evaluation_report

        X = np.array(X_raw, dtype=float)
        y = np.array(y_raw, dtype=int)
        n = len(X)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)

        X_train, y_train = X[:train_end], y[:train_end]
        X_val, y_val = X[train_end:val_end], y[train_end:val_end]
        X_test, y_test = X[val_end:], y[val_end:]
        regimes_test = regimes[val_end:]

        if len(set(y_train)) < 2 or len(set(y_test)) < 2:
            self.validated = False
            self.evaluation_report = {
                "validated": False,
                "status": "PROBABILITY MODEL NOT YET VALIDATED",
                "error": "Chronological split lacks both outcome classes in train/test segments.",
            }
            return self.evaluation_report

        clf = self._build_estimator(model_type)
        clf.fit(X_train, y_train)
        val_probs = clf.predict_proba(X_val)[:, 1]
        test_probs = clf.predict_proba(X_test)[:, 1]
        test_preds = (test_probs >= 0.5).astype(int)

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

        roc_auc = (
            round(float(roc_auc_score(y_test, test_probs)), 4)
            if len(set(y_test)) > 1
            else None
        )
        brier = round(float(brier_score_loss(y_test, test_probs)), 4)
        prob_true, prob_pred = calibration_curve(y_test, test_probs, n_bins=5, strategy="uniform")

        regime_perf: Dict[str, Dict[str, Any]] = {}
        for r in set(regimes_test):
            idxs = [k for k, rv in enumerate(regimes_test) if rv == r]
            if idxs:
                r_y = y_test[idxs]
                r_p = test_preds[idxs]
                regime_perf[r] = {
                    "samples": len(idxs),
                    "accuracy": round(float(accuracy_score(r_y, r_p)), 4),
                    "positive_rate": round(float(r_y.mean()), 4),
                }

        self.model = clf
        self.model_name = model_type
        self.validated = True
        self.evaluation_report = {
            "validated": True,
            "status": f"VALIDATED ({model_type})",
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "timeframe": timeframe.value,
            "model_type": model_type,
            "samples_total": n,
            "split": {"train": len(X_train), "validation": len(X_val), "test": len(X_test)},
            "test_metrics": {
                "accuracy": round(float(accuracy_score(y_test, test_preds)), 4),
                "precision": round(float(precision_score(y_test, test_preds, zero_division=0)), 4),
                "recall": round(float(recall_score(y_test, test_preds, zero_division=0)), 4),
                "f1": round(float(f1_score(y_test, test_preds, zero_division=0)), 4),
                "roc_auc": roc_auc,
                "brier_score": brier,
                "val_brier_score": round(float(brier_score_loss(y_val, val_probs)), 4),
            },
            "walk_forward_fold_accuracies": wf_accuracies,
            "calibration": [
                {"predicted_mean": round(float(pp), 3), "empirical_freq": round(float(pt), 3)}
                for pt, pp in zip(prob_true, prob_pred)
            ],
            "by_regime": regime_perf,
            "leakage_note": "Strictly chronological split + expanding walk-forward validation; intrabar SL/TP conflicts labeled as loss.",
        }
        return self.evaluation_report

    def predict(self, candles: List[OHLCVCandle]) -> ProbabilityEstimate:
        if not self.validated or self.model is None or not SKLEARN_AVAILABLE:
            return ProbabilityEstimate(
                model_validated=False,
                status_label="PROBABILITY MODEL NOT YET VALIDATED",
                estimated_win_probability=None,
            )

        closes = [c.close for c in candles]
        ema20 = compute_ema_series(closes, 20)
        ema50 = compute_ema_series(closes, 50)
        rsi14 = compute_rsi_series(closes, 14)
        atr14 = compute_atr_series(candles, 14)
        feat = extract_bar_features(candles, len(candles) - 1, ema20, ema50, rsi14, atr14)
        if feat is None:
            return ProbabilityEstimate(
                model_validated=False,
                status_label="PROBABILITY MODEL NOT YET VALIDATED",
                estimated_win_probability=None,
            )

        vec, _ = feat
        prob = float(self.model.predict_proba(np.array([vec], dtype=float))[0, 1])
        return ProbabilityEstimate(
            model_validated=True,
            status_label=f"VALIDATED MODEL ({self.model_name})",
            model_name=self.model_name,
            estimated_win_probability=round(prob, 4),
            validation_metrics=self.evaluation_report.get("test_metrics", {}),
        )

    @staticmethod
    def _build_estimator(model_type: str) -> Any:
        mt = model_type.lower().strip()
        if mt == "random_forest":
            return RandomForestClassifier(n_estimators=120, max_depth=5, random_state=42)
        if mt == "gradient_boosting":
            return GradientBoostingClassifier(n_estimators=80, max_depth=3, random_state=42)
        return Pipeline(
            [
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(max_iter=500, random_state=42)),
            ]
        )


probability_manager = ProbabilityModelManager()
