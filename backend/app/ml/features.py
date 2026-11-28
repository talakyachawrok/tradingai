"""Leakage-free feature engineering and triple-barrier setup labeling for ML probability estimation."""

from dataclasses import dataclass
import math
from typing import List, Optional, Tuple
from app.indicators.engine import (
    compute_atr_series,
    compute_ema_series,
    compute_macd_series,
    compute_rsi_series,
)
from app.models.analysis import BiasDirection, CandlestickPattern, MarketStructureResult, TradeLevels
from app.models.market import OHLCVCandle
from app.patterns.engine import compute_candle_metrics


MIN_FEATURE_BARS = 55

FEATURE_NAMES: List[str] = [
    "body_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "candle_dir_aligned",
    "rsi_14",
    "rsi_slope_3",
    "atr_pct",
    "volatility_ratio",
    "realized_vol_14",
    "ema20_dist_atr",
    "ema50_dist_atr",
    "sma20_dist_atr",
    "sma50_dist_atr",
    "ema20_50_spread_atr",
    "macd_norm_atr",
    "macd_hist_norm_atr",
    "ret_1_atr",
    "ret_5_atr",
    "ret_12_atr",
    "dist_to_swing_high_atr",
    "dist_to_swing_low_atr",
    "pattern_alignment",
    "trend_alignment_score",
    "stop_dist_atr",
    "target_dist_atr",
    "rr_planned",
    "session_utc_hour_sin",
    "session_utc_hour_cos",
    "setup_direction",
]


def compute_sma_series(values: List[float], period: int) -> List[Optional[float]]:
    """Calculate Simple Moving Average series using strictly past values."""
    n = len(values)
    result: List[Optional[float]] = [None] * n
    if n < period or period < 1:
        return result
    rolling_sum = sum(values[:period])
    result[period - 1] = rolling_sum / period
    for i in range(period, n):
        rolling_sum += values[i] - values[i - period]
        result[i] = rolling_sum / period
    return result


@dataclass
class IndicatorSeriesBundle:
    ema20: List[Optional[float]]
    ema50: List[Optional[float]]
    sma20: List[Optional[float]]
    sma50: List[Optional[float]]
    rsi14: List[Optional[float]]
    atr14: List[Optional[float]]
    macd_line: List[Optional[float]]
    macd_signal: List[Optional[float]]
    macd_hist: List[Optional[float]]


def precompute_indicator_bundle(candles: List[OHLCVCandle]) -> IndicatorSeriesBundle:
    """Compute causal indicator arrays once across a candle sequence."""
    closes = [c.close for c in candles]
    macd_line, macd_signal, macd_hist = compute_macd_series(closes, 12, 26, 9)
    return IndicatorSeriesBundle(
        ema20=compute_ema_series(closes, 20),
        ema50=compute_ema_series(closes, 50),
        sma20=compute_sma_series(closes, 20),
        sma50=compute_sma_series(closes, 50),
        rsi14=compute_rsi_series(closes, 14),
        atr14=compute_atr_series(candles, 14),
        macd_line=macd_line,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _past_pattern_bias(candles: List[OHLCVCandle], idx: int) -> float:
    """Compute signed pattern bias [-1, +1] using strictly bars <= idx."""
    if idx < 2:
        return 0.0
    prev_c = candles[idx - 1]
    curr_c = candles[idx]
    pm = compute_candle_metrics(prev_c)
    cm = compute_candle_metrics(curr_c)

    # Engulfing checks
    bull_engulf = (
        pm.is_bearish
        and cm.is_bullish
        and curr_c.open <= prev_c.close
        and curr_c.close >= prev_c.open
        and cm.body_ratio >= 0.45
    )
    bear_engulf = (
        pm.is_bullish
        and cm.is_bearish
        and curr_c.open >= prev_c.close
        and curr_c.close <= prev_c.open
        and cm.body_ratio >= 0.45
    )
    if bull_engulf:
        return 1.0
    if bear_engulf:
        return -1.0

    # Pinbar / hammer / shooting star
    bull_hammer = cm.lower_wick_ratio >= 0.55 and cm.upper_wick_ratio <= 0.20 and cm.body_ratio <= 0.35
    bear_star = cm.upper_wick_ratio >= 0.55 and cm.lower_wick_ratio <= 0.20 and cm.body_ratio <= 0.35
    if bull_hammer:
        return 0.75
    if bear_star:
        return -0.75

    return 0.35 if (cm.is_bullish and cm.body_ratio >= 0.65) else (-0.35 if (cm.is_bearish and cm.body_ratio >= 0.65) else 0.0)


def derive_past_setup_geometry(
    candles: List[OHLCVCandle],
    idx: int,
    bundle: IndicatorSeriesBundle,
    candidate_dir: Optional[BiasDirection] = None,
    levels: Optional[TradeLevels] = None,
) -> Optional[Tuple[float, float, float, float]]:
    """
    Determine (setup_sign, stop_dist_atr, target_dist_atr, rr_planned) strictly from
    past-only indicators/structure or active trade plan levels without lookahead.
    """
    atr = bundle.atr14[idx]
    ema20 = bundle.ema20[idx]
    ema50 = bundle.ema50[idx]
    if atr is None or atr <= 0 or ema20 is None or ema50 is None:
        return None

    if candidate_dir == BiasDirection.BULLISH:
        setup_sign = 1.0
    elif candidate_dir == BiasDirection.BEARISH:
        setup_sign = -1.0
    else:
        macd_h = bundle.macd_hist[idx]
        if ema20 != ema50:
            setup_sign = 1.0 if ema20 > ema50 else -1.0
        elif macd_h is not None and macd_h != 0:
            setup_sign = 1.0 if macd_h > 0 else -1.0
        else:
            setup_sign = 1.0 if candles[idx].close >= ema50 else -1.0

    if (
        levels is not None
        and levels.entry_price is not None
        and levels.stop_loss is not None
        and levels.take_profit_1 is not None
        and atr > 0
    ):
        stop_dist_atr = _clamp(abs(levels.entry_price - levels.stop_loss) / atr, 0.3, 6.0)
        target_dist_atr = _clamp(abs(levels.take_profit_1 - levels.entry_price) / atr, 0.3, 12.0)
        rr_planned = _clamp(target_dist_atr / max(stop_dist_atr, 1e-6), 0.2, 8.0)
        return setup_sign, stop_dist_atr, target_dist_atr, rr_planned

    win_start = max(0, idx - 20)
    recent_high = max(c.high for c in candles[win_start : idx + 1])
    recent_low = min(c.low for c in candles[win_start : idx + 1])
    close = candles[idx].close
    if setup_sign > 0:
        struct_stop = (close - recent_low) / atr
        struct_target = (recent_high - close) / atr
    else:
        struct_stop = (recent_high - close) / atr
        struct_target = (close - recent_low) / atr

    stop_dist_atr = _clamp(max(struct_stop, 1.15), 0.9, 2.8)
    target_dist_atr = _clamp(max(struct_target, stop_dist_atr * 1.65), 1.5, 4.2)
    rr_planned = _clamp(target_dist_atr / max(stop_dist_atr, 1e-6), 1.0, 4.0)
    return setup_sign, stop_dist_atr, target_dist_atr, rr_planned


def extract_bar_features(
    candles: List[OHLCVCandle],
    idx: int,
    bundle: IndicatorSeriesBundle,
    candidate_dir: Optional[BiasDirection] = None,
    levels: Optional[TradeLevels] = None,
    patterns: Optional[List[CandlestickPattern]] = None,
    structure: Optional[MarketStructureResult] = None,
) -> Optional[Tuple[List[float], str]]:
    """
    Extract a validated, finite feature vector strictly from bars <= idx.
    Returns None when warmup is insufficient or any indicator is missing/non-finite.
    """
    if idx < 50 or idx >= len(candles):
        return None

    e20 = bundle.ema20[idx]
    e50 = bundle.ema50[idx]
    s20 = bundle.sma20[idx]
    s50 = bundle.sma50[idx]
    rsi = bundle.rsi14[idx]
    rsi_prev3 = bundle.rsi14[idx - 3] if idx >= 3 else None
    atr = bundle.atr14[idx]
    macd_l = bundle.macd_line[idx]
    macd_s = bundle.macd_signal[idx]
    macd_h = bundle.macd_hist[idx]

    if any(
        v is None
        for v in (e20, e50, s20, s50, rsi, rsi_prev3, atr, macd_l, macd_s, macd_h)
    ):
        return None

    geom = derive_past_setup_geometry(candles, idx, bundle, candidate_dir=candidate_dir, levels=levels)
    if geom is None:
        return None
    setup_sign, stop_dist_atr, target_dist_atr, rr_planned = geom

    atr_f = max(float(atr), 1e-12)  # type: ignore[arg-type]
    c = candles[idx]
    if c.close <= 0 or c.high < c.low:
        return None

    m = compute_candle_metrics(c)
    candle_dir_raw = 1.0 if m.is_bullish else (-1.0 if m.is_bearish else 0.0)
    candle_dir_aligned = candle_dir_raw * setup_sign

    atr_pct = (atr_f / c.close) * 100.0
    valid_atrs = [float(x) for x in bundle.atr14[max(0, idx - 19) : idx + 1] if x is not None and x > 0]
    avg_atr = sum(valid_atrs) / len(valid_atrs) if valid_atrs else atr_f
    volatility_ratio = _clamp(atr_f / max(avg_atr, 1e-12), 0.2, 5.0)

    # 14-bar realized return volatility (%)
    rets: List[float] = []
    for k in range(max(1, idx - 13), idx + 1):
        prev_close = candles[k - 1].close
        if prev_close > 0:
            rets.append((candles[k].close - prev_close) / prev_close)
    if len(rets) >= 2:
        mean_r = sum(rets) / len(rets)
        realized_vol_14 = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / len(rets)) * 100.0
    else:
        realized_vol_14 = atr_pct

    ema20_dist_atr = ((c.close - float(e20)) / atr_f) * setup_sign  # type: ignore[arg-type]
    ema50_dist_atr = ((c.close - float(e50)) / atr_f) * setup_sign  # type: ignore[arg-type]
    sma20_dist_atr = ((c.close - float(s20)) / atr_f) * setup_sign  # type: ignore[arg-type]
    sma50_dist_atr = ((c.close - float(s50)) / atr_f) * setup_sign  # type: ignore[arg-type]
    ema20_50_spread_atr = ((float(e20) - float(e50)) / atr_f) * setup_sign  # type: ignore[arg-type]
    macd_norm_atr = (float(macd_l) / atr_f) * setup_sign  # type: ignore[arg-type]
    macd_hist_norm_atr = (float(macd_h) / atr_f) * setup_sign  # type: ignore[arg-type]
    rsi_slope_3 = (float(rsi) - float(rsi_prev3)) * setup_sign  # type: ignore[arg-type]

    ret_1_atr = ((c.close - candles[idx - 1].close) / atr_f) * setup_sign
    ret_5_atr = ((c.close - candles[idx - 5].close) / atr_f) * setup_sign
    ret_12_atr = ((c.close - candles[idx - 12].close) / atr_f) * setup_sign

    win_high = max(bar.high for bar in candles[max(0, idx - 19) : idx + 1])
    win_low = min(bar.low for bar in candles[max(0, idx - 19) : idx + 1])
    dist_to_swing_high_atr = (win_high - c.close) / atr_f
    dist_to_swing_low_atr = (c.close - win_low) / atr_f

    # Candlestick pattern signal aligned with setup
    pat_raw = _past_pattern_bias(candles, idx)
    if patterns:
        best_p = max(patterns, key=lambda p: p.strength_score)
        p_sign = (
            1.0
            if best_p.classification == BiasDirection.BULLISH
            else (-1.0 if best_p.classification == BiasDirection.BEARISH else 0.0)
        )
        if p_sign != 0.0:
            pat_raw = 0.5 * pat_raw + 0.5 * p_sign * (best_p.strength_score / 100.0)
    pattern_alignment = _clamp(pat_raw * setup_sign, -1.0, 1.0)

    # Trend & structure alignment (-1..+1)
    votes = 0.0
    votes += 1.0 if float(e20) > float(e50) else -1.0  # type: ignore[arg-type]
    votes += 1.0 if c.close > float(s20) else -1.0  # type: ignore[arg-type]
    votes += 1.0 if c.close > float(s50) else -1.0  # type: ignore[arg-type]
    votes += 1.0 if float(macd_l) > float(macd_s) else -1.0  # type: ignore[arg-type]
    if structure is not None and structure.bias in (BiasDirection.BULLISH, BiasDirection.BEARISH):
        votes += 1.0 if structure.bias == BiasDirection.BULLISH else -1.0
        trend_alignment_score = _clamp((votes * setup_sign) / 5.0, -1.0, 1.0)
    else:
        trend_alignment_score = _clamp((votes * setup_sign) / 4.0, -1.0, 1.0)

    hr = c.timestamp.hour
    hr_sin = math.sin(2.0 * math.pi * hr / 24.0)
    hr_cos = math.cos(2.0 * math.pi * hr / 24.0)

    raw_spread = (float(e20) - float(e50)) / atr_f  # type: ignore[arg-type]
    regime = "trending_bull" if raw_spread > 0.4 else ("trending_bear" if raw_spread < -0.4 else "ranging")

    vec = [
        m.body_ratio,
        m.upper_wick_ratio,
        m.lower_wick_ratio,
        candle_dir_aligned,
        float(rsi),  # type: ignore[arg-type]
        rsi_slope_3,
        atr_pct,
        volatility_ratio,
        realized_vol_14,
        ema20_dist_atr,
        ema50_dist_atr,
        sma20_dist_atr,
        sma50_dist_atr,
        ema20_50_spread_atr,
        macd_norm_atr,
        macd_hist_norm_atr,
        ret_1_atr,
        ret_5_atr,
        ret_12_atr,
        dist_to_swing_high_atr,
        dist_to_swing_low_atr,
        pattern_alignment,
        trend_alignment_score,
        stop_dist_atr,
        target_dist_atr,
        rr_planned,
        hr_sin,
        hr_cos,
        setup_sign,
    ]
    if any(not math.isfinite(val) for val in vec):
        return None
    return vec, regime


@dataclass
class LabeledSample:
    timestamp: float
    symbol: str
    features: List[float]
    label: int
    regime: str


def build_labeled_samples(
    candles: List[OHLCVCandle],
    symbol: str = "UNKNOWN",
    horizon_bars: int = 24,
) -> List[LabeledSample]:
    """
    Create strictly causal historical setup samples using triple-barrier labeling.
    Label = 1 iff TP1 is reached strictly before SL within `horizon_bars` forward bars.
    If both SL and TP1 are touched in the same future bar, conservatively label = 0.
    """
    if len(candles) <= MIN_FEATURE_BARS + horizon_bars:
        return []

    bundle = precompute_indicator_bundle(candles)
    samples: List[LabeledSample] = []

    for i in range(50, len(candles) - horizon_bars):
        feat = extract_bar_features(candles, i, bundle)
        geom = derive_past_setup_geometry(candles, i, bundle)
        atr = bundle.atr14[i]
        if feat is None or geom is None or atr is None or atr <= 0:
            continue
        vec, regime = feat
        setup_sign, stop_mult, target_mult, _ = geom
        entry = candles[i].close
        if setup_sign > 0:
            sl = entry - float(atr) * stop_mult
            tp = entry + float(atr) * target_mult
        else:
            sl = entry + float(atr) * stop_mult
            tp = entry - float(atr) * target_mult

        label = 0
        for j in range(i + 1, i + 1 + horizon_bars):
            bar = candles[j]
            if setup_sign > 0:
                sl_hit = bar.low <= sl
                tp_hit = bar.high >= tp
            else:
                sl_hit = bar.high >= sl
                tp_hit = bar.low <= tp
            # Conservative tie-breaking: SL assumed hit first if both occur on same bar
            if sl_hit:
                label = 0
                break
            if tp_hit:
                label = 1
                break

        samples.append(
            LabeledSample(
                timestamp=candles[i].timestamp.timestamp(),
                symbol=symbol,
                features=vec,
                label=label,
                regime=regime,
            )
        )

    return samples


def build_labeled_dataset(
    candles: List[OHLCVCandle],
    horizon_bars: int = 24,
) -> Tuple[List[List[float]], List[int], List[str]]:
    """Backwards-compatible wrapper returning (X, y, regimes) for single-series callers."""
    samples = build_labeled_samples(candles, horizon_bars=horizon_bars)
    return (
        [s.features for s in samples],
        [s.label for s in samples],
        [s.regime for s in samples],
    )
