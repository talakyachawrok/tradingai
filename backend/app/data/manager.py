"""Market data manager orchestrating providers, sessions, CSV imports, and integrity checks."""

import csv
import io
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from app.core.config import get_settings
from app.core.instruments import instrument_registry, normalize_symbol
from app.core.logging_config import logger
from app.data.base import MarketDataProvider, ProviderConnectionTestResult, ProviderFetchResult
from app.data.providers.alphavantage import AlphaVantageProvider
from app.data.providers.binance_public import BinancePublicProvider
from app.data.providers.demo_historical import DemoHistoricalProvider
from app.data.providers.twelvedata import TwelveDataProvider
from app.data.providers.webhook_cache import webhook_cache_provider
from app.data.validator import validate_and_clean_candles
from app.models.market import (
    DataConnectionStatus,
    DataIntegrityReport,
    MarketDataResponse,
    MarketOverview,
    OHLCVCandle,
    ProviderCapability,
    Timeframe,
)


def compute_market_session(now: Optional[datetime] = None) -> Tuple[str, str]:
    """Return active FX/Global market session and status in UTC."""
    dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    weekday = dt.weekday()  # 0=Mon .. 6=Sun
    hour = dt.hour

    if weekday == 5 or (weekday == 6 and hour < 21):
        return "Weekend (FX Closed / Crypto 24/7)", "FX Closed"

    active: List[str] = []
    if hour >= 21 or hour < 6:
        active.append("Sydney")
    if 0 <= hour < 9:
        active.append("Tokyo")
    if 7 <= hour < 16:
        active.append("London")
    if 12 <= hour < 21:
        active.append("New York")

    if "London" in active and "New York" in active:
        return "London / New York Overlap", "High Liquidity Session"
    if active:
        return " + ".join(active), "Active Session"
    return "Off-Peak Transition", "Low Liquidity"


def classify_volatility(candles: List[OHLCVCandle]) -> str:
    """Compute recent ATR% volatility condition directly from OHLC candles."""
    if len(candles) < 15:
        return "Insufficient Data"
    trs: List[float] = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev_c = candles[i - 1].close
        tr = max(c.high - c.low, abs(c.high - prev_c), abs(c.low - prev_c))
        trs.append(tr)
    recent_atr = sum(trs[-14:]) / 14.0
    baseline_atr = sum(trs[-50:]) / min(len(trs), 50)
    atr_pct = (recent_atr / candles[-1].close) * 100.0 if candles[-1].close else 0.0
    ratio = recent_atr / baseline_atr if baseline_atr > 0 else 1.0
    if ratio >= 1.45 or atr_pct >= 2.5:
        return f"Elevated ({atr_pct:.2f}% ATR)"
    if ratio <= 0.65:
        return f"Compressed ({atr_pct:.2f}% ATR)"
    return f"Normal ({atr_pct:.2f}% ATR)"


class MarketDataManager:
    """Coordinates market data providers without fabricating live data."""

    def __init__(self) -> None:
        self.providers: Dict[str, MarketDataProvider] = {
            "twelvedata": TwelveDataProvider(),
            "alphavantage": AlphaVantageProvider(),
            "binance_public": BinancePublicProvider(),
            "webhook_cache": webhook_cache_provider,
            "demo_historical": DemoHistoricalProvider(),
        }
        self._cache: Dict[Tuple[str, Timeframe, str, bool, int], Tuple[float, MarketDataResponse]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def list_provider_capabilities(self) -> List[ProviderCapability]:
        return [p.capabilities() for p in self.providers.values()]

    async def test_provider_connection(
        self, provider_name: str, symbol: str = "XAUUSD", timeframe: Timeframe = Timeframe.H1
    ) -> ProviderConnectionTestResult:
        name = provider_name.lower().strip()
        if name not in self.providers:
            return ProviderConnectionTestResult(
                provider_name=name,
                connected=False,
                status="UNSUPPORTED",
                message=f"Unknown provider '{provider_name}'. Available: {', '.join(self.providers.keys())}.",
                tested_symbol=symbol,
                tested_timeframe=timeframe.value,
            )
        logger.info("Testing connection for provider=%s symbol=%s timeframe=%s", name, symbol, timeframe.value)
        return await self.providers[name].test_connection(symbol=symbol, timeframe=timeframe)

    def ingest_csv(self, symbol: str, timeframe: Timeframe, csv_text: str) -> int:
        """Parse user-uploaded OHLCV CSV into webhook_cache provider."""
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = []
        for row in reader:
            normalized_row = {k.strip().lower(): v for k, v in row.items() if k}
            ts = (
                normalized_row.get("timestamp")
                or normalized_row.get("time")
                or normalized_row.get("date")
                or normalized_row.get("datetime")
            )
            if not ts:
                continue
            rows.append(
                {
                    "timestamp": ts,
                    "open": float(normalized_row["open"]),
                    "high": float(normalized_row["high"]),
                    "low": float(normalized_row["low"]),
                    "close": float(normalized_row["close"]),
                    "volume": float(normalized_row["volume"])
                    if normalized_row.get("volume") not in (None, "")
                    else None,
                }
            )
        n_loaded = webhook_cache_provider.push_candles(symbol, timeframe, rows, replace=True)
        self.clear_cache()
        return n_loaded

    async def get_market_data(
        self,
        symbol: str,
        timeframe: Timeframe,
        provider_override: Optional[str] = None,
        limit: int = 300,
        allow_demo: bool = False,
        force_refresh: bool = False,
    ) -> MarketDataResponse:
        settings = get_settings()
        norm = normalize_symbol(symbol)
        spec = instrument_registry.get(norm)
        display_name = spec.display_name if spec else norm

        preferred = provider_override
        if not preferred:
            try:
                from app.database.repositories import repo
                user_cfg = await repo.get_settings()
                preferred = user_cfg.data_provider
            except Exception:
                preferred = None
        preferred = (preferred or settings.default_data_provider or "auto").lower().strip()

        cache_key = (norm, timeframe, preferred, allow_demo, limit)
        ttl = settings.market_data_cache_ttl_seconds
        if timeframe in (Timeframe.M1, Timeframe.M3):
            ttl = min(ttl, 15)
        if not force_refresh and ttl > 0 and cache_key in self._cache:
            cached_ts, cached_resp = self._cache[cache_key]
            if (time.monotonic() - cached_ts) < ttl:
                logger.info("Market data cache HIT symbol=%s tf=%s provider=%s", norm, timeframe.value, preferred)
                return cached_resp.model_copy(update={"cache_hit": True})

        fetch_result = await self._resolve_fetch(
            norm, timeframe, preferred, limit=limit, allow_demo=allow_demo
        )

        candles, integrity = validate_and_clean_candles(
            fetch_result.raw_candles,
            timeframe=timeframe,
            stale_threshold_seconds=settings.stale_data_threshold_seconds,
            check_staleness=not fetch_result.is_demo,
        )

        status = fetch_result.connection_status
        status_message = fetch_result.error_message
        if fetch_result.is_demo:
            status = DataConnectionStatus.DEMO_MODE
            status_message = (
                "DEMO MODE: Displaying static historical sample dataset (not live market data)."
            )
        elif not candles:
            status = DataConnectionStatus.DATA_UNAVAILABLE
            if not status_message:
                status_message = (
                    f"No live market data available for {norm} ({timeframe.value}). "
                    "Configure API keys, send TradingView webhook candles, upload CSV, or switch to Demo Historical Mode."
                )
            logger.warning("Data unavailable for %s (%s): %s", norm, timeframe.value, status_message)
        elif integrity.is_stale and status == DataConnectionStatus.LIVE:
            status = DataConnectionStatus.DELAYED
            status_message = "Market data is stale/delayed beyond configured freshness threshold."
            logger.warning("Stale market data for %s (%s): %ss old", norm, timeframe.value, integrity.stale_seconds)

        session_name, session_status = compute_market_session()
        current_price = candles[-1].close if candles else None
        prev_close = candles[-2].close if len(candles) >= 2 else None
        price_change = (current_price - prev_close) if (current_price and prev_close) else None
        price_change_pct = (
            (price_change / prev_close) * 100.0 if (price_change is not None and prev_close) else None
        )

        market_status = "Unavailable"
        if status == DataConnectionStatus.LIVE:
            market_status = "Live Feed Active"
        elif status == DataConnectionStatus.DELAYED:
            market_status = "Delayed / Stale"
        elif status == DataConnectionStatus.WEBHOOK_CACHE:
            market_status = "Webhook / CSV Dataset"
        elif status == DataConnectionStatus.DEMO_MODE:
            market_status = "Demo Historical Mode"

        overview = MarketOverview(
            symbol=norm,
            display_name=display_name,
            timeframe=timeframe,
            current_price=current_price,
            price_change=price_change,
            price_change_pct=price_change_pct,
            market_session=session_name,
            session_status=session_status,
            data_source=fetch_result.provider_name,
            connection_status=status,
            last_data_update=candles[-1].timestamp if candles else None,
            market_status=market_status,
            volatility_condition=classify_volatility(candles) if candles else "Unavailable",
            is_demo=fetch_result.is_demo,
            status_message=status_message,
        )

        response = MarketDataResponse(
            overview=overview,
            candles=candles,
            integrity=integrity,
            unavailable_timeframes=fetch_result.unavailable_timeframes,
            cache_hit=False,
        )
        if ttl > 0 and candles:
            self._cache[cache_key] = (time.monotonic(), response)
        return response

    async def _resolve_fetch(
        self,
        symbol: str,
        timeframe: Timeframe,
        preferred: str,
        limit: int,
        allow_demo: bool,
    ) -> ProviderFetchResult:
        if preferred != "auto" and preferred in self.providers:
            if preferred == "demo_historical" and not allow_demo:
                pass
            else:
                return await self.providers[preferred].fetch_candles(symbol, timeframe, limit)

        # Auto selection order: webhook_cache (if populated) -> configured live providers -> binance_public (crypto) -> demo (only if explicitly allowed)
        errors: List[str] = []
        unavailable_tfs: List[Timeframe] = []

        if webhook_cache_provider.has_data(symbol, timeframe):
            res = await webhook_cache_provider.fetch_candles(symbol, timeframe, limit)
            if len(res.raw_candles) >= 30:
                return res

        for name in ("twelvedata", "alphavantage", "binance_public"):
            provider = self.providers[name]
            caps = provider.capabilities()
            if not caps.configured:
                continue
            if symbol not in caps.supported_symbols and name == "binance_public":
                continue
            res = await provider.fetch_candles(symbol, timeframe, limit)
            unavailable_tfs = list(set(unavailable_tfs + res.unavailable_timeframes))
            if res.raw_candles:
                return res
            if res.error_message:
                errors.append(f"{name}: {res.error_message}")

        if allow_demo:
            return await self.providers["demo_historical"].fetch_candles(symbol, timeframe, limit)

        return ProviderFetchResult(
            provider_name="none",
            connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
            raw_candles=[],
            is_demo=False,
            error_message=" | ".join(errors)
            if errors
            else f"No live provider configured or reachable for {symbol}.",
            unavailable_timeframes=unavailable_tfs,
        )


market_data_manager = MarketDataManager()
