"""Market session schedule and optional Economic News Calendar adapter."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import httpx
from app.core.config import get_settings
from app.data.manager import compute_market_session


async def get_sessions_and_news(symbol: str = "XAUUSD") -> Dict[str, Any]:
    """Return active UTC market sessions and real economic calendar events if configured."""
    now = datetime.now(timezone.utc)
    session_name, session_status = compute_market_session(now)
    hour = now.hour

    sessions = [
        {"name": "Sydney", "utc_hours": "21:00 - 06:00", "active": hour >= 21 or hour < 6},
        {"name": "Tokyo", "utc_hours": "00:00 - 09:00", "active": 0 <= hour < 9},
        {"name": "London", "utc_hours": "07:00 - 16:00", "active": 7 <= hour < 16},
        {"name": "New York", "utc_hours": "12:00 - 21:00", "active": 12 <= hour < 21},
    ]

    settings = get_settings()
    if settings.news_provider.lower() != "finnhub" or not settings.finnhub_api_key.strip():
        return {
            "current_session": session_name,
            "session_status": session_status,
            "utc_time": now.isoformat(),
            "sessions": sessions,
            "news_status": "UNAVAILABLE",
            "news_message": (
                "Economic news calendar unavailable: configure FINNHUB_API_KEY and NEWS_PROVIDER=finnhub in .env. "
                "No economic events are fabricated."
            ),
            "events": [],
            "blackout_active": False,
            "blackout_reason": "",
        }

    # Fetch real Finnhub economic calendar if configured
    try:
        date_from = now.strftime("%Y-%m-%d")
        date_to = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://finnhub.io/api/v1/calendar/economic",
                params={"from": date_from, "to": date_to, "token": settings.finnhub_api_key.strip()},
            )
        resp.raise_for_status()
        raw_events = resp.json().get("economicCalendar", [])
        events = [
            {
                "event": ev.get("event"),
                "country": ev.get("country"),
                "currency": ev.get("unit") or ev.get("country"),
                "impact": ev.get("impact"),
                "time": ev.get("time"),
                "estimate": ev.get("estimate"),
                "previous": ev.get("prev"),
            }
            for ev in raw_events[:25]
        ]
        blackout, reason = _check_blackout(events, symbol, now, settings)
        return {
            "current_session": session_name,
            "session_status": session_status,
            "utc_time": now.isoformat(),
            "sessions": sessions,
            "news_status": "CONNECTED (Finnhub)",
            "news_message": f"Loaded {len(events)} scheduled economic events.",
            "events": events,
            "blackout_active": blackout,
            "blackout_reason": reason,
        }
    except Exception as exc:
        return {
            "current_session": session_name,
            "session_status": session_status,
            "utc_time": now.isoformat(),
            "sessions": sessions,
            "news_status": "ERROR",
            "news_message": f"Failed to fetch Finnhub calendar: {exc}",
            "events": [],
            "blackout_active": False,
            "blackout_reason": "",
        }


def _check_blackout(
    events: List[Dict[str, Any]], symbol: str, now: datetime, settings: Any
) -> Tuple[bool, str]:
    if not settings.news_filter_enabled:
        return False, ""
    relevant_countries = set()
    if "USD" in symbol:
        relevant_countries.add("US")
    if "EUR" in symbol:
        relevant_countries.add("EU")
    if "GBP" in symbol:
        relevant_countries.add("GB")

    for ev in events:
        if str(ev.get("impact", "")).lower() != "high":
            continue
        if relevant_countries and ev.get("country") not in relevant_countries:
            continue
        ts_str = ev.get("time")
        if not ts_str:
            continue
        try:
            ev_dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            if ev_dt.tzinfo is None:
                ev_dt = ev_dt.replace(tzinfo=timezone.utc)
            delta_min = (ev_dt - now).total_seconds() / 60.0
            if -settings.news_blackout_minutes_after <= delta_min <= settings.news_blackout_minutes_before:
                return True, f"High-impact event '{ev.get('event')}' ({ev.get('country')}) at {ev_dt.isoformat()}"
        except Exception:
            continue
    return False, ""
