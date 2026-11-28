"""OHLCV market data validation and integrity auditing."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from app.models.market import (
    TIMEFRAME_SECONDS,
    DataIntegrityReport,
    OHLCVCandle,
    Timeframe,
)


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse ISO strings, epoch seconds, or epoch milliseconds into UTC datetime."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        if ts <= 0:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return parse_timestamp(int(raw))
        normalized = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None


def validate_and_clean_candles(
    raw_candles: List[Dict[str, Any]],
    timeframe: Timeframe,
    stale_threshold_seconds: int = 900,
    reference_now: Optional[datetime] = None,
    check_staleness: bool = True,
) -> Tuple[List[OHLCVCandle], DataIntegrityReport]:
    """
    Validate OHLC bounds, drop corrupted candles, deduplicate timestamps,
    sort ascending, detect time gaps, and evaluate data freshness.
    """
    raw_count = len(raw_candles)
    invalid_dropped = 0
    dedup_map: Dict[datetime, OHLCVCandle] = {}
    duplicates_removed = 0
    warnings: List[str] = []

    for item in raw_candles:
        ts = parse_timestamp(item.get("timestamp") or item.get("datetime") or item.get("time"))
        if ts is None:
            invalid_dropped += 1
            continue
        try:
            candle = OHLCVCandle(
                timestamp=ts,
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item["volume"]) if item.get("volume") is not None else None,
            )
        except Exception:
            invalid_dropped += 1
            continue

        if ts in dedup_map:
            duplicates_removed += 1
        dedup_map[ts] = candle

    sorted_candles = [dedup_map[k] for k in sorted(dedup_map.keys())]
    expected_step = TIMEFRAME_SECONDS[timeframe]
    gap_timestamps: List[datetime] = []

    for i in range(1, len(sorted_candles)):
        delta = (sorted_candles[i].timestamp - sorted_candles[i - 1].timestamp).total_seconds()
        # Allow minor market-close weekend gaps on daily/4h, flag gaps > 1.5x interval on intraday
        multiplier = 1.5 if expected_step <= 3600 else 4.0
        if delta > expected_step * multiplier:
            gap_timestamps.append(sorted_candles[i].timestamp)

    is_stale = False
    stale_seconds: Optional[float] = None
    if sorted_candles and check_staleness:
        now = reference_now or datetime.now(timezone.utc)
        stale_seconds = max(0.0, (now - sorted_candles[-1].timestamp).total_seconds())
        effective_threshold = max(stale_threshold_seconds, expected_step * 2)
        if stale_seconds > effective_threshold:
            is_stale = True
            warnings.append(
                f"Latest candle is {int(stale_seconds)}s old (threshold: {effective_threshold}s)."
            )

    if invalid_dropped > 0:
        warnings.append(f"Dropped {invalid_dropped} malformed or invalid OHLC candles.")
    if duplicates_removed > 0:
        warnings.append(f"Removed {duplicates_removed} duplicate timestamp candles.")
    if gap_timestamps:
        warnings.append(f"Detected {len(gap_timestamps)} time gap(s) in candle sequence.")

    has_volume = any(c.volume is not None and c.volume > 0 for c in sorted_candles)

    report = DataIntegrityReport(
        raw_count=raw_count,
        valid_count=len(sorted_candles),
        duplicates_removed=duplicates_removed,
        invalid_candles_dropped=invalid_dropped,
        time_gaps_detected=len(gap_timestamps),
        gap_timestamps=gap_timestamps[:20],
        is_stale=is_stale,
        stale_seconds=round(stale_seconds, 1) if stale_seconds is not None else None,
        has_volume=has_volume,
        warnings=warnings,
    )
    return sorted_candles, report
