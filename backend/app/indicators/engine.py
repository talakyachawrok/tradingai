"""Technical indicator engine calculating EMA, RSI, ATR, MACD, and Volume metrics from OHLCV."""

from typing import List, Optional, Tuple
from app.models.analysis import IndicatorChartOverlay, IndicatorSnapshot
from app.models.market import OHLCVCandle
from app.models.settings import IndicatorSettings


def compute_ema_series(values: List[float], period: int) -> List[Optional[float]]:
    """Calculate Exponential Moving Average series seeded with SMA of first `period` points."""
    n = len(values)
    result: List[Optional[float]] = [None] * n
    if n < period or period < 1:
        return result
    sma = sum(values[:period]) / period
    result[period - 1] = sma
    k = 2.0 / (period + 1)
    ema = sma
    for i in range(period, n):
        ema = (values[i] - ema) * k + ema
        result[i] = ema
    return result


def compute_rsi_series(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Calculate Wilder's Relative Strength Index (RSI)."""
    n = len(closes)
    result: List[Optional[float]] = [None] * n
    if n <= period:
        return result

    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    result[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    for i in range(period + 1, n):
        diff = closes[i] - closes[i - 1]
        gain = max(diff, 0.0)
        loss = max(-diff, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))
    return result


def compute_atr_series(candles: List[OHLCVCandle], period: int = 14) -> List[Optional[float]]:
    """Calculate Wilder's Average True Range (ATR)."""
    n = len(candles)
    result: List[Optional[float]] = [None] * n
    if n <= period:
        return result

    trs: List[float] = [candles[0].high - candles[0].low]
    for i in range(1, n):
        c = candles[i]
        prev_c = candles[i - 1].close
        trs.append(max(c.high - c.low, abs(c.high - prev_c), abs(c.low - prev_c)))

    atr = sum(trs[1 : period + 1]) / period
    result[period] = atr
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + trs[i]) / period
        result[i] = atr
    return result


def compute_macd_series(
    closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Calculate MACD line, signal line, and histogram."""
    n = len(closes)
    ema_fast = compute_ema_series(closes, fast)
    ema_slow = compute_ema_series(closes, slow)
    macd_line: List[Optional[float]] = [None] * n
    valid_macd: List[float] = []
    valid_indices: List[int] = []

    for i in range(n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            val = ema_fast[i] - ema_slow[i]  # type: ignore[operator]
            macd_line[i] = val
            valid_macd.append(val)
            valid_indices.append(i)

    signal_line: List[Optional[float]] = [None] * n
    histogram: List[Optional[float]] = [None] * n
    if len(valid_macd) >= signal:
        sig_values = compute_ema_series(valid_macd, signal)
        for pos, idx in enumerate(valid_indices):
            if sig_values[pos] is not None:
                signal_line[idx] = sig_values[pos]
                histogram[idx] = macd_line[idx] - sig_values[pos]  # type: ignore[operator]

    return macd_line, signal_line, histogram


def evaluate_indicators(
    candles: List[OHLCVCandle], settings: IndicatorSettings | None = None
) -> Tuple[IndicatorSnapshot, IndicatorChartOverlay]:
    """Compute all technical indicators and diagnostic summaries."""
    cfg = settings or IndicatorSettings()
    if not candles:
        return IndicatorSnapshot(), IndicatorChartOverlay()

    closes = [c.close for c in candles]
    timestamps = [c.timestamp for c in candles]

    ema20 = compute_ema_series(closes, cfg.ema_fast)
    ema50 = compute_ema_series(closes, cfg.ema_medium)
    ema200 = compute_ema_series(closes, cfg.ema_slow)
    rsi = compute_rsi_series(closes, cfg.rsi_period)
    atr = compute_atr_series(candles, cfg.atr_period)
    macd_line, macd_sig, macd_hist = compute_macd_series(
        closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal
    )

    last_close = closes[-1]
    e20 = ema20[-1]
    e50 = ema50[-1]
    e200 = ema200[-1]
    last_rsi = rsi[-1]
    last_atr = atr[-1]
    last_macd = macd_line[-1]
    last_sig = macd_sig[-1]
    last_hist = macd_hist[-1]

    # Volume analysis where available
    vols = [c.volume for c in candles if c.volume is not None and c.volume > 0]
    vol_current = candles[-1].volume if candles[-1].volume and candles[-1].volume > 0 else None
    vol_sma = None
    vol_ratio = None
    vol_condition = "Volume data unavailable from provider"
    if vol_current is not None and len(vols) >= cfg.volume_sma_period:
        recent_vols = [
            c.volume for c in candles[-cfg.volume_sma_period :] if c.volume is not None
        ]
        if recent_vols:
            vol_sma = sum(recent_vols) / len(recent_vols)
            if vol_sma > 0:
                vol_ratio = vol_current / vol_sma
                if vol_ratio >= 1.5:
                    vol_condition = f"High volume expansion ({vol_ratio:.2f}x 20-SMA)"
                elif vol_ratio <= 0.6:
                    vol_condition = f"Low volume / thin participation ({vol_ratio:.2f}x 20-SMA)"
                else:
                    vol_condition = f"Normal volume ({vol_ratio:.2f}x 20-SMA)"

    # EMA alignment
    ema_alignment = "insufficient_data"
    if e20 is not None and e50 is not None and e200 is not None:
        if last_close > e20 > e50 > e200:
            ema_alignment = "strong_bullish_stack"
        elif last_close < e20 < e50 < e200:
            ema_alignment = "strong_bearish_stack"
        elif e20 > e50 and last_close > e50:
            ema_alignment = "bullish_bias"
        elif e20 < e50 and last_close < e50:
            ema_alignment = "bearish_bias"
        else:
            ema_alignment = "mixed_choppy"
    elif e20 is not None and e50 is not None:
        if last_close > e20 > e50:
            ema_alignment = "bullish_bias"
        elif last_close < e20 < e50:
            ema_alignment = "bearish_bias"
        else:
            ema_alignment = "mixed_choppy"

    # RSI condition
    rsi_condition = "insufficient_data"
    if last_rsi is not None:
        if last_rsi >= cfg.rsi_overbought:
            rsi_condition = f"Overbought ({last_rsi:.1f})"
        elif last_rsi <= cfg.rsi_oversold:
            rsi_condition = f"Oversold ({last_rsi:.1f})"
        elif last_rsi >= 55:
            rsi_condition = f"Bullish momentum ({last_rsi:.1f})"
        elif last_rsi <= 45:
            rsi_condition = f"Bearish momentum ({last_rsi:.1f})"
        else:
            rsi_condition = f"Neutral ({last_rsi:.1f})"

    # Volatility condition
    atr_pct = (last_atr / last_close) * 100.0 if (last_atr is not None and last_close > 0) else None
    volatility_condition = "insufficient_data"
    if atr_pct is not None:
        valid_atrs = [x for x in atr[-50:] if x is not None]
        avg_atr = sum(valid_atrs) / len(valid_atrs) if valid_atrs else last_atr
        ratio = last_atr / avg_atr if avg_atr and avg_atr > 0 else 1.0
        if ratio > 1.4:
            volatility_condition = f"High / Expanding ({atr_pct:.2f}%)"
        elif ratio < 0.7:
            volatility_condition = f"Low / Compressed ({atr_pct:.2f}%)"
        else:
            volatility_condition = f"Normal ({atr_pct:.2f}%)"

    # MACD condition
    macd_condition = "insufficient_data"
    if last_macd is not None and last_sig is not None and last_hist is not None:
        if last_macd > last_sig and last_hist > 0:
            macd_condition = "Bullish crossover / positive momentum"
        elif last_macd < last_sig and last_hist < 0:
            macd_condition = "Bearish crossover / negative momentum"
        else:
            macd_condition = "Flat / transitioning"

    # Check indicator conflicts
    conflicts: List[str] = []
    if "bullish" in ema_alignment and last_macd is not None and last_sig is not None and last_macd < last_sig:
        conflicts.append("EMAs show bullish stack while MACD momentum is bearish.")
    if "bearish" in ema_alignment and last_macd is not None and last_sig is not None and last_macd > last_sig:
        conflicts.append("EMAs show bearish stack while MACD momentum is bullish.")
    if last_rsi is not None and last_rsi >= cfg.rsi_overbought and "bullish" in ema_alignment:
        conflicts.append(f"RSI is overbought ({last_rsi:.1f}); chasing longs carries pullback risk.")
    if last_rsi is not None and last_rsi <= cfg.rsi_oversold and "bearish" in ema_alignment:
        conflicts.append(f"RSI is oversold ({last_rsi:.1f}); chasing shorts carries bounce risk.")

    def _round_list(seq: List[Optional[float]], digits: int = 6) -> List[Optional[float]]:
        return [round(v, digits) if v is not None else None for v in seq]

    snapshot = IndicatorSnapshot(
        ema_20=round(e20, 6) if e20 is not None else None,
        ema_50=round(e50, 6) if e50 is not None else None,
        ema_200=round(e200, 6) if e200 is not None else None,
        rsi_14=round(last_rsi, 2) if last_rsi is not None else None,
        atr_14=round(last_atr, 6) if last_atr is not None else None,
        atr_pct=round(atr_pct, 4) if atr_pct is not None else None,
        macd_line=round(last_macd, 6) if last_macd is not None else None,
        macd_signal=round(last_sig, 6) if last_sig is not None else None,
        macd_histogram=round(last_hist, 6) if last_hist is not None else None,
        volume_current=round(vol_current, 2) if vol_current is not None else None,
        volume_sma_20=round(vol_sma, 2) if vol_sma is not None else None,
        volume_ratio=round(vol_ratio, 2) if vol_ratio is not None else None,
        ema_alignment=ema_alignment,
        rsi_condition=rsi_condition,
        volatility_condition=volatility_condition,
        macd_condition=macd_condition,
        volume_condition=vol_condition,
        conflicts=conflicts,
    )

    overlay = IndicatorChartOverlay(
        timestamps=timestamps,
        ema_20=_round_list(ema20),
        ema_50=_round_list(ema50),
        ema_200=_round_list(ema200),
        rsi_14=_round_list(rsi, 2),
        atr_14=_round_list(atr),
    )
    return snapshot, overlay
