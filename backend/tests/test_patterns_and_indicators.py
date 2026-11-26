"""Tests for candlestick pattern detection and technical indicator calculations."""

from datetime import datetime, timedelta, timezone
import pytest
from app.indicators.engine import (
    compute_atr_series,
    compute_ema_series,
    compute_macd_series,
    compute_rsi_series,
    evaluate_indicators,
)
from app.models.analysis import BiasDirection
from app.models.market import OHLCVCandle
from app.patterns.engine import detect_candlestick_patterns


def make_candle(idx: int, o: float, h: float, l: float, c: float, v: float = 1000.0) -> OHLCVCandle:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=idx)
    return OHLCVCandle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v)


def test_bullish_engulfing_and_hammer_detection():
    base = [make_candle(i, 100.0 - i * 0.4, 100.5 - i * 0.4, 99.5 - i * 0.4, 99.7 - i * 0.4) for i in range(6)]
    # Bar 6: Hammer after downtrend (visible small body near high, long lower wick)
    hammer = make_candle(6, 97.0, 97.6, 94.8, 97.5)
    # Bar 7: Bearish bar, Bar 8: Bullish engulfing
    bear = make_candle(7, 97.6, 97.8, 96.8, 97.0)
    bull_eng = make_candle(8, 96.9, 98.4, 96.8, 98.2)
    candles = base + [hammer, bear, bull_eng]

    patterns = detect_candlestick_patterns(candles, lookback_tail=4)
    names = {p.name for p in patterns}
    assert "Hammer" in names
    assert "Bullish Engulfing" in names
    eng = next(p for p in patterns if p.name == "Bullish Engulfing")
    assert eng.classification == BiasDirection.BULLISH
    assert eng.strength_score > 65


def test_morning_star_and_doji_detection():
    base = [make_candle(i, 110.0, 111.0, 109.0, 110.2) for i in range(5)]
    c1 = make_candle(5, 110.0, 110.2, 106.0, 106.5)  # strong bearish
    c2 = make_candle(6, 106.3, 106.7, 105.8, 106.35)  # small doji middle
    c3 = make_candle(7, 106.4, 109.5, 106.2, 109.1)  # bullish past midpoint (108.25)
    patterns = detect_candlestick_patterns(base + [c1, c2, c3], lookback_tail=3)
    names = {p.name for p in patterns}
    assert "Doji" in names
    assert "Morning Star" in names


def test_three_white_soldiers_and_inside_bar():
    base = [make_candle(i, 100.0, 100.5, 99.5, 100.0) for i in range(4)]
    s1 = make_candle(4, 100.0, 102.2, 99.9, 102.0)
    s2 = make_candle(5, 102.0, 104.2, 101.9, 104.0)
    s3 = make_candle(6, 104.0, 106.3, 103.9, 106.0)
    inside = make_candle(7, 105.2, 105.9, 104.4, 105.5)
    patterns = detect_candlestick_patterns(base + [s1, s2, s3, inside], lookback_tail=3)
    names = {p.name for p in patterns}
    assert "Three White Soldiers" in names
    assert "Inside Bar" in names


def test_ema_rsi_atr_macd_exact_calculations():
    # Monotonic uptrend -> RSI near 100, EMA20 > EMA50, positive MACD
    candles = [
        make_candle(i, 100.0 + i, 101.5 + i, 99.5 + i, 101.0 + i, 1500.0)
        for i in range(70)
    ]
    closes = [c.close for c in candles]
    ema20 = compute_ema_series(closes, 20)
    ema50 = compute_ema_series(closes, 50)
    rsi = compute_rsi_series(closes, 14)
    atr = compute_atr_series(candles, 14)
    macd_line, sig_line, hist = compute_macd_series(closes)

    assert ema20[18] is None and ema20[19] is not None
    assert ema20[-1] > ema50[-1]  # type: ignore[operator]
    assert rsi[-1] == pytest.approx(100.0, abs=0.01)
    assert atr[-1] == pytest.approx(2.0, abs=0.05)
    assert macd_line[-1] is not None and sig_line[-1] is not None and hist[-1] is not None

    snap, overlay = evaluate_indicators(candles)
    assert snap.ema_alignment == "bullish_bias"
    assert snap.rsi_14 == pytest.approx(100.0, abs=0.01)
    assert len(overlay.ema_20) == 70
