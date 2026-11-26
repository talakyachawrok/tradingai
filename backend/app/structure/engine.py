"""Market structure detection engine (swings, HH/HL/LH/LL, BOS, CHoCH, regime)."""

from typing import List, Optional
from app.indicators.engine import compute_atr_series
from app.models.analysis import (
    BiasDirection,
    MarketStructureResult,
    StructureEvent,
    SwingPoint,
)
from app.models.market import OHLCVCandle
from app.models.settings import StructureSettings


def analyze_market_structure(
    candles: List[OHLCVCandle], settings: StructureSettings | None = None
) -> MarketStructureResult:
    """
    Identify confirmed swing highs/lows using left/right fractal lookback + ATR significance filter,
    label HH/HL/LH/LL, detect BOS and CHoCH breaks, and classify market regime.
    """
    cfg = settings or StructureSettings()
    n = len(candles)
    if n < max(20, cfg.swing_left_bars + cfg.swing_right_bars + 5):
        return MarketStructureResult(
            bias=BiasDirection.UNCLEAR,
            regime="unclear",
            explanation="Insufficient candle history to establish reliable swing structure.",
        )

    atr_series = compute_atr_series(candles, 14)
    fallback_atr = sum(c.high - c.low for c in candles[-14:]) / 14.0

    raw_swings: List[SwingPoint] = []
    left = cfg.swing_left_bars
    right = cfg.swing_right_bars

    for i in range(left, n - right):
        win_highs = [candles[j].high for j in range(i - left, i + right + 1)]
        win_lows = [candles[j].low for j in range(i - left, i + right + 1)]
        local_atr = atr_series[i] or fallback_atr
        min_move = local_atr * cfg.min_swing_atr_distance

        is_sh = (
            candles[i].high == max(win_highs)
            and candles[i].high >= candles[i - 1].high
            and candles[i].high > candles[i + 1].high
        )
        is_sl = (
            candles[i].low == min(win_lows)
            and candles[i].low <= candles[i - 1].low
            and candles[i].low < candles[i + 1].low
        )

        if is_sh:
            if raw_swings and raw_swings[-1].kind == "swing_high":
                if candles[i].high > raw_swings[-1].price:
                    raw_swings[-1] = SwingPoint(
                        index=i,
                        timestamp=candles[i].timestamp,
                        price=candles[i].high,
                        kind="swing_high",
                        label="SH",
                    )
            elif not raw_swings or abs(candles[i].high - raw_swings[-1].price) >= min_move:
                raw_swings.append(
                    SwingPoint(
                        index=i,
                        timestamp=candles[i].timestamp,
                        price=candles[i].high,
                        kind="swing_high",
                        label="SH",
                    )
                )

        if is_sl:
            if raw_swings and raw_swings[-1].kind == "swing_low":
                if candles[i].low < raw_swings[-1].price:
                    raw_swings[-1] = SwingPoint(
                        index=i,
                        timestamp=candles[i].timestamp,
                        price=candles[i].low,
                        kind="swing_low",
                        label="SL",
                    )
            elif not raw_swings or abs(candles[i].low - raw_swings[-1].price) >= min_move:
                raw_swings.append(
                    SwingPoint(
                        index=i,
                        timestamp=candles[i].timestamp,
                        price=candles[i].low,
                        kind="swing_low",
                        label="SL",
                    )
                )

    # Label HH, LH, HL, LL
    prev_high: Optional[float] = None
    prev_low: Optional[float] = None
    for sp in raw_swings:
        if sp.kind == "swing_high":
            if prev_high is None:
                sp.label = "SH"
            elif sp.price > prev_high:
                sp.label = "HH"
            else:
                sp.label = "LH"
            prev_high = sp.price
        else:
            if prev_low is None:
                sp.label = "SL"
            elif sp.price > prev_low:
                sp.label = "HL"
            else:
                sp.label = "LL"
            prev_low = sp.price

    # Detect BOS and CHoCH using candle closes past confirmed prior swing highs/lows
    events: List[StructureEvent] = []
    running_bias = BiasDirection.NEUTRAL
    last_sh: Optional[SwingPoint] = None
    last_sl: Optional[SwingPoint] = None
    broken_high_indices = set()
    broken_low_indices = set()
    swing_by_index = {sp.index: sp for sp in raw_swings}

    for i in range(n):
        if i in swing_by_index:
            sp = swing_by_index[i]
            if sp.kind == "swing_high":
                last_sh = sp
            else:
                last_sl = sp

        c = candles[i]
        # Require close beyond confirmed swing (at least `right` bars after swing formed)
        if last_sh and i >= last_sh.index + right and last_sh.index not in broken_high_indices:
            if c.close > last_sh.price:
                broken_high_indices.add(last_sh.index)
                ev_type = "CHoCH" if running_bias == BiasDirection.BEARISH else "BOS"
                events.append(
                    StructureEvent(
                        event_type=ev_type,
                        direction=BiasDirection.BULLISH,
                        index=i,
                        timestamp=c.timestamp,
                        break_price=c.close,
                        reference_swing_price=last_sh.price,
                        reference_swing_timestamp=last_sh.timestamp,
                        explanation=(
                            f"Candle closed at {c.close:.5g} above prior swing high {last_sh.price:.5g} "
                            f"({ev_type} bullish {'reversal' if ev_type == 'CHoCH' else 'continuation'})."
                        ),
                    )
                )
                running_bias = BiasDirection.BULLISH

        if last_sl and i >= last_sl.index + right and last_sl.index not in broken_low_indices:
            if c.close < last_sl.price:
                broken_low_indices.add(last_sl.index)
                ev_type = "CHoCH" if running_bias == BiasDirection.BULLISH else "BOS"
                events.append(
                    StructureEvent(
                        event_type=ev_type,
                        direction=BiasDirection.BEARISH,
                        index=i,
                        timestamp=c.timestamp,
                        break_price=c.close,
                        reference_swing_price=last_sl.price,
                        reference_swing_timestamp=last_sl.timestamp,
                        explanation=(
                            f"Candle closed at {c.close:.5g} below prior swing low {last_sl.price:.5g} "
                            f"({ev_type} bearish {'reversal' if ev_type == 'CHoCH' else 'continuation'})."
                        ),
                    )
                )
                running_bias = BiasDirection.BEARISH

    # Determine current overall bias & regime from recent swings + events
    recent_highs = [s for s in raw_swings if s.kind == "swing_high"][-3:]
    recent_lows = [s for s in raw_swings if s.kind == "swing_low"][-3:]
    recent_bos = next((e for e in reversed(events) if e.event_type == "BOS"), None)
    recent_choch = next((e for e in reversed(events) if e.event_type == "CHoCH"), None)

    high_labels = [s.label for s in recent_highs]
    low_labels = [s.label for s in recent_lows]

    if "HH" in high_labels[-2:] and "HL" in low_labels[-2:]:
        bias = BiasDirection.BULLISH
        regime = "trending_bullish"
    elif "LH" in high_labels[-2:] and "LL" in low_labels[-2:]:
        bias = BiasDirection.BEARISH
        regime = "trending_bearish"
    elif running_bias in (BiasDirection.BULLISH, BiasDirection.BEARISH) and events:
        last_ev = events[-1]
        if n - 1 - last_ev.index <= 35:
            bias = last_ev.direction
            regime = f"trending_{last_ev.direction.value}"
        else:
            bias = BiasDirection.NEUTRAL
            regime = "range_bound"
    elif len(raw_swings) >= 4:
        bias = BiasDirection.NEUTRAL
        recent_range = max(c.high for c in candles[-25:]) - min(c.low for c in candles[-25:])
        avg_atr = fallback_atr if fallback_atr > 0 else 1.0
        regime = "consolidation" if (recent_range / avg_atr) < 4.5 else "range_bound"
    else:
        bias = BiasDirection.UNCLEAR
        regime = "unclear"

    swing_summary = ", ".join(f"{s.label}@{s.price:.5g}" for s in raw_swings[-6:])
    explanation = (
        f"Market structure is classified as {bias.value.upper()} ({regime.replace('_', ' ')}). "
        f"Recent swing sequence: [{swing_summary or 'none'}]. "
    )
    if events:
        explanation += f"Latest structural break: {events[-1].event_type} ({events[-1].direction.value}) at {events[-1].break_price:.5g}."
    else:
        explanation += "No recent confirmed BOS/CHoCH break detected within current swing tolerance."

    return MarketStructureResult(
        bias=bias,
        regime=regime,
        swing_points=raw_swings[-20:],
        structure_events=events[-12:],
        recent_bos=recent_bos,
        recent_choch=recent_choch,
        explanation=explanation,
    )
