"""Rule-based candlestick pattern detection engine using exact OHLC calculations."""

from dataclasses import dataclass
from typing import List
from app.models.analysis import BiasDirection, CandlestickPattern
from app.models.market import OHLCVCandle
from app.models.settings import PatternSettings


@dataclass
class CandleMetrics:
    open: float
    high: float
    low: float
    close: float
    body: float
    candle_range: float
    upper_wick: float
    lower_wick: float
    body_ratio: float
    upper_wick_ratio: float
    lower_wick_ratio: float
    is_bullish: bool
    is_bearish: bool


def compute_candle_metrics(candle: OHLCVCandle) -> CandleMetrics:
    """Compute exact OHLC body, wicks, range, and ratio metrics."""
    body = abs(candle.close - candle.open)
    candle_range = max(candle.high - candle.low, 1e-12)
    upper_wick = candle.high - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.low
    return CandleMetrics(
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        body=body,
        candle_range=candle_range,
        upper_wick=max(0.0, upper_wick),
        lower_wick=max(0.0, lower_wick),
        body_ratio=body / candle_range,
        upper_wick_ratio=max(0.0, upper_wick) / candle_range,
        lower_wick_ratio=max(0.0, lower_wick) / candle_range,
        is_bullish=candle.close > candle.open,
        is_bearish=candle.close < candle.open,
    )


def _recent_atr(candles: List[OHLCVCandle], end_idx: int, period: int = 14) -> float:
    start = max(1, end_idx - period + 1)
    trs: List[float] = []
    for i in range(start, end_idx + 1):
        c = candles[i]
        prev_close = candles[i - 1].close
        trs.append(max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close)))
    return sum(trs) / len(trs) if trs else (candles[end_idx].high - candles[end_idx].low)


def _prior_context(candles: List[OHLCVCandle], idx: int, lookback: int = 5) -> str:
    if idx < 2:
        return "neutral"
    start = max(0, idx - lookback)
    change = candles[idx - 1].close - candles[start].open
    atr = max(_recent_atr(candles, idx - 1), 1e-12)
    if change > atr * 0.6:
        return "uptrend"
    if change < -atr * 0.6:
        return "downtrend"
    return "consolidation"


def detect_candlestick_patterns(
    candles: List[OHLCVCandle],
    settings: PatternSettings | None = None,
    lookback_tail: int = 8,
) -> List[CandlestickPattern]:
    """
    Detect contextual candlestick patterns over the most recent `lookback_tail` bars.
    Returns structured patterns sorted from most recent & strongest.
    """
    cfg = settings or PatternSettings()
    if len(candles) < 5:
        return []

    metrics = [compute_candle_metrics(c) for c in candles]
    detected: List[CandlestickPattern] = []
    start_idx = max(3, len(candles) - lookback_tail)

    for i in range(start_idx, len(candles)):
        c = candles[i]
        m = metrics[i]
        prev_c = candles[i - 1]
        prev_m = metrics[i - 1]
        atr = max(_recent_atr(candles, i), 1e-12)
        rel_size = m.candle_range / atr
        context = _prior_context(candles, i)

        def add_pattern(
            name: str,
            classification: BiasDirection,
            strength: float,
            indices: List[int],
            explanation: str,
            confirmations: List[str],
            invalidations: List[str],
        ) -> None:
            detected.append(
                CandlestickPattern(
                    name=name,
                    classification=classification,
                    strength_score=round(min(100.0, max(10.0, strength)), 1),
                    candle_indices=indices,
                    timestamps=[candles[idx].timestamp for idx in indices],
                    explanation=explanation,
                    confirmation_conditions=confirmations,
                    invalidation_conditions=invalidations,
                    metrics={
                        "body_ratio": round(m.body_ratio, 3),
                        "upper_wick_ratio": round(m.upper_wick_ratio, 3),
                        "lower_wick_ratio": round(m.lower_wick_ratio, 3),
                        "relative_size_atr": round(rel_size, 2),
                    },
                )
            )

        # 1 & 2. Bullish / Bearish Engulfing
        if (
            prev_m.is_bearish
            and m.is_bullish
            and m.open <= prev_m.close
            and m.close >= prev_m.open
            and m.body > prev_m.body * 1.05
        ):
            score = 68.0 + min(20.0, (m.body / max(prev_m.body, 1e-12)) * 8.0) + (10.0 if context == "downtrend" else 0.0)
            add_pattern(
                "Bullish Engulfing",
                BiasDirection.BULLISH,
                score,
                [i - 1, i],
                f"Bullish candle body ({m.body:.5g}) completely engulfed prior bearish candle body ({prev_m.body:.5g}) in {context} context.",
                ["Next candle holds above engulfing midpoint", "Price breaks above engulfing high"],
                [f"Candle close below engulfing low ({min(c.low, prev_c.low):.5g})"],
            )
        elif (
            prev_m.is_bullish
            and m.is_bearish
            and m.open >= prev_m.close
            and m.close <= prev_m.open
            and m.body > prev_m.body * 1.05
        ):
            score = 68.0 + min(20.0, (m.body / max(prev_m.body, 1e-12)) * 8.0) + (10.0 if context == "uptrend" else 0.0)
            add_pattern(
                "Bearish Engulfing",
                BiasDirection.BEARISH,
                score,
                [i - 1, i],
                f"Bearish candle body ({m.body:.5g}) engulfed prior bullish candle body ({prev_m.body:.5g}) in {context} context.",
                ["Follow-through close below engulfing low", "Rejection of engulfing midpoint"],
                [f"Candle close above engulfing high ({max(c.high, prev_c.high):.5g})"],
            )

        # 3, 4, 5, 6, 16, 17. Hammer, Hanging Man, Shooting Star, Inverted Hammer, Pin Bars
        body_eff = max(m.body, m.candle_range * 0.03)
        lower_to_body = m.lower_wick / body_eff
        upper_to_body = m.upper_wick / body_eff

        if (
            lower_to_body >= cfg.pin_bar_min_wick_to_body
            and m.upper_wick_ratio <= cfg.pin_bar_max_opposite_wick_ratio
            and m.body_ratio > cfg.doji_max_body_ratio
        ):
            if context == "downtrend":
                add_pattern(
                    "Hammer",
                    BiasDirection.BULLISH,
                    66.0 + min(22.0, lower_to_body * 4.5),
                    [i],
                    f"Lower wick is {lower_to_body:.2f}x body after a pullback/downtrend, showing buying absorption off {c.low:.5g}.",
                    ["Bullish close above hammer high"],
                    [f"Close below hammer low ({c.low:.5g})"],
                )
            elif context == "uptrend":
                add_pattern(
                    "Hanging Man",
                    BiasDirection.BEARISH,
                    58.0 + min(18.0, lower_to_body * 3.5),
                    [i],
                    f"Long lower wick ({lower_to_body:.2f}x body) appeared at upswing highs; signals potential selling pressure if confirmed.",
                    ["Bearish candle close below hanging man low"],
                    [f"Strong close above high ({c.high:.5g})"],
                )
            add_pattern(
                "Bullish Pin Bar",
                BiasDirection.BULLISH,
                64.0 + min(24.0, m.lower_wick_ratio * 28.0),
                [i],
                f"Bullish rejection pin bar with {m.lower_wick_ratio * 100:.1f}% lower wick and close near upper third.",
                ["Break above pin bar high", "Hold above 50% wick level"],
                [f"Close below pin bar tail ({c.low:.5g})"],
            )

        if (
            upper_to_body >= cfg.pin_bar_min_wick_to_body
            and m.lower_wick_ratio <= cfg.pin_bar_max_opposite_wick_ratio
            and m.body_ratio > cfg.doji_max_body_ratio
        ):
            if context == "uptrend":
                add_pattern(
                    "Shooting Star",
                    BiasDirection.BEARISH,
                    67.0 + min(22.0, upper_to_body * 4.5),
                    [i],
                    f"Upper wick is {upper_to_body:.2f}x body after an upswing, indicating supply rejection at {c.high:.5g}.",
                    ["Bearish close below shooting star low"],
                    [f"Close above shooting star high ({c.high:.5g})"],
                )
            elif context == "downtrend":
                add_pattern(
                    "Inverted Hammer",
                    BiasDirection.BULLISH,
                    57.0 + min(18.0, upper_to_body * 3.5),
                    [i],
                    f"Long upper probe ({upper_to_body:.2f}x body) after a downswing; requires bullish follow-through.",
                    ["Next candle closes above inverted hammer body/high"],
                    [f"Close below low ({c.low:.5g})"],
                )
            add_pattern(
                "Bearish Pin Bar",
                BiasDirection.BEARISH,
                64.0 + min(24.0, m.upper_wick_ratio * 28.0),
                [i],
                f"Bearish rejection pin bar with {m.upper_wick_ratio * 100:.1f}% upper wick rejecting higher prices.",
                ["Break below pin bar low"],
                [f"Close above pin bar wick high ({c.high:.5g})"],
            )

        # 7, 8, 9. Doji, Dragonfly Doji, Gravestone Doji
        if m.body_ratio <= cfg.doji_max_body_ratio:
            if m.lower_wick_ratio >= 0.6 and m.upper_wick_ratio <= 0.15:
                add_pattern(
                    "Dragonfly Doji",
                    BiasDirection.BULLISH if context == "downtrend" else BiasDirection.NEUTRAL,
                    62.0 + m.lower_wick_ratio * 20.0,
                    [i],
                    f"Open and close clustered near high ({m.body_ratio*100:.1f}% body) with long lower rejection wick.",
                    ["Bullish follow-through close above high"],
                    [f"Close below dragonfly low ({c.low:.5g})"],
                )
            elif m.upper_wick_ratio >= 0.6 and m.lower_wick_ratio <= 0.15:
                add_pattern(
                    "Gravestone Doji",
                    BiasDirection.BEARISH if context == "uptrend" else BiasDirection.NEUTRAL,
                    62.0 + m.upper_wick_ratio * 20.0,
                    [i],
                    f"Open and close clustered near low ({m.body_ratio*100:.1f}% body) with long upper rejection wick.",
                    ["Bearish follow-through close below low"],
                    [f"Close above gravestone high ({c.high:.5g})"],
                )
            else:
                add_pattern(
                    "Doji",
                    BiasDirection.NEUTRAL,
                    50.0 + min(20.0, rel_size * 10.0),
                    [i],
                    f"Indecision candle with tiny body ({m.body_ratio*100:.1f}% of range); equilibrium between buyers and sellers.",
                    ["Wait for directional breakout candle close beyond Doji range"],
                    ["Continued choppy range inside Doji high/low"],
                )

        # 10 & 11. Morning Star / Evening Star (3-candle)
        m2 = metrics[i - 2]
        mid_first = (m2.open + m2.close) / 2.0
        if (
            m2.is_bearish
            and m2.body_ratio >= 0.45
            and prev_m.body_ratio <= 0.35
            and m.is_bullish
            and m.body_ratio >= 0.45
            and m.close >= mid_first
        ):
            add_pattern(
                "Morning Star",
                BiasDirection.BULLISH,
                78.0 + min(15.0, rel_size * 6.0),
                [i - 2, i - 1, i],
                "Three-candle bullish reversal: strong bearish leg, small indecision middle bar, and bullish close past first bar midpoint.",
                ["Hold above middle candle low", "Continuation above 3rd candle high"],
                [f"Close below pattern low ({min(candles[i-2].low, prev_c.low, c.low):.5g})"],
            )
        elif (
            m2.is_bullish
            and m2.body_ratio >= 0.45
            and prev_m.body_ratio <= 0.35
            and m.is_bearish
            and m.body_ratio >= 0.45
            and m.close <= mid_first
        ):
            add_pattern(
                "Evening Star",
                BiasDirection.BEARISH,
                78.0 + min(15.0, rel_size * 6.0),
                [i - 2, i - 1, i],
                "Three-candle bearish reversal: strong bullish leg, small pause candle, and bearish close past first bar midpoint.",
                ["Hold below middle candle high", "Continuation below 3rd candle low"],
                [f"Close above pattern high ({max(candles[i-2].high, prev_c.high, c.high):.5g})"],
            )

        # 12 & 13. Three White Soldiers / Three Black Crows
        if (
            m2.is_bullish and prev_m.is_bullish and m.is_bullish
            and m2.body_ratio >= 0.5 and prev_m.body_ratio >= 0.5 and m.body_ratio >= 0.5
            and m.close > prev_m.close > m2.close
        ):
            add_pattern(
                "Three White Soldiers",
                BiasDirection.BULLISH,
                80.0,
                [i - 2, i - 1, i],
                "Three consecutive strong bullish candles with progressively higher closes.",
                ["Wait for shallow pullback rather than chasing extended move"],
                [f"Break below first soldier low ({candles[i-2].low:.5g})"],
            )
        elif (
            m2.is_bearish and prev_m.is_bearish and m.is_bearish
            and m2.body_ratio >= 0.5 and prev_m.body_ratio >= 0.5 and m.body_ratio >= 0.5
            and m.close < prev_m.close < m2.close
        ):
            add_pattern(
                "Three Black Crows",
                BiasDirection.BEARISH,
                80.0,
                [i - 2, i - 1, i],
                "Three consecutive strong bearish candles with progressively lower closes.",
                ["Wait for corrective retest before entry if oversold"],
                [f"Break above first crow high ({candles[i-2].high:.5g})"],
            )

        # 14 & 15. Inside Bar / Outside Bar
        if c.high <= prev_c.high and c.low >= prev_c.low:
            add_pattern(
                "Inside Bar",
                BiasDirection.NEUTRAL,
                56.0,
                [i - 1, i],
                f"Compression bar fully contained inside prior mother bar ({prev_c.low:.5g}–{prev_c.high:.5g}).",
                ["Trade confirmed breakout close above mother high or below mother low"],
                ["False breakout followed by immediate re-entry into mother range"],
            )
        elif c.high > prev_c.high and c.low < prev_c.low:
            cls = BiasDirection.BULLISH if m.is_bullish else (BiasDirection.BEARISH if m.is_bearish else BiasDirection.NEUTRAL)
            add_pattern(
                "Outside Bar",
                cls,
                64.0 + min(15.0, m.body_ratio * 15.0),
                [i - 1, i],
                f"Range expansion bar sweeping both sides of prior candle ({prev_c.low:.5g}–{prev_c.high:.5g}) and closing {cls.value}.",
                ["Follow-through in close direction"],
                ["Reversal back past opposite extreme"],
            )

        # 18. Strong Momentum Candle
        if m.body_ratio >= cfg.momentum_min_body_ratio and rel_size >= cfg.momentum_min_atr_multiple:
            cls = BiasDirection.BULLISH if m.is_bullish else BiasDirection.BEARISH
            add_pattern(
                f"Strong {'Bullish' if m.is_bullish else 'Bearish'} Momentum Candle",
                cls,
                70.0 + min(20.0, rel_size * 7.0),
                [i],
                f"High-displacement candle with {m.body_ratio*100:.1f}% body ratio and {rel_size:.2f}x ATR range.",
                ["Retest of candle 50% equilibrium or breakout continuation"],
                ["Full retracement closing beyond momentum candle origin"],
            )

        # 19. Long Wick Rejection (if not already a hammer/shooting star)
        if m.lower_wick_ratio >= cfg.long_wick_min_ratio and lower_to_body < cfg.pin_bar_min_wick_to_body:
            add_pattern(
                "Long Lower Wick Rejection",
                BiasDirection.BULLISH,
                60.0 + m.lower_wick_ratio * 20.0,
                [i],
                f"Notable lower wick rejection ({m.lower_wick_ratio*100:.1f}% of range) defending lows.",
                ["Follow-through bullish close"],
                [f"Close below wick low ({c.low:.5g})"],
            )
        elif m.upper_wick_ratio >= cfg.long_wick_min_ratio and upper_to_body < cfg.pin_bar_min_wick_to_body:
            add_pattern(
                "Long Upper Wick Rejection",
                BiasDirection.BEARISH,
                60.0 + m.upper_wick_ratio * 20.0,
                [i],
                f"Notable upper wick rejection ({m.upper_wick_ratio*100:.1f}% of range) rejecting highs.",
                ["Follow-through bearish close"],
                [f"Close above wick high ({c.high:.5g})"],
            )

        # 20 & 21. Consecutive Bullish / Bearish Candles
        n = cfg.consecutive_count
        if i >= n - 1:
            window = metrics[i - n + 1 : i + 1]
            if all(w.is_bullish for w in window):
                add_pattern(
                    f"Consecutive Bullish Candles ({n})",
                    BiasDirection.BULLISH,
                    60.0 + n * 4.0,
                    list(range(i - n + 1, i + 1)),
                    f"{n} consecutive bullish closes showing sustained short-term buying pressure.",
                    ["Pullback holds higher low"],
                    ["Bearish engulfing or break below sequence midpoint"],
                )
            elif all(w.is_bearish for w in window):
                add_pattern(
                    f"Consecutive Bearish Candles ({n})",
                    BiasDirection.BEARISH,
                    60.0 + n * 4.0,
                    list(range(i - n + 1, i + 1)),
                    f"{n} consecutive bearish closes showing sustained short-term selling pressure.",
                    ["Bounce fails to reclaim lower high"],
                    ["Bullish engulfing or break above sequence midpoint"],
                )

    # Sort with most recent bar first, then strength
    detected.sort(key=lambda p: (max(p.candle_indices), p.strength_score), reverse=True)
    return detected
