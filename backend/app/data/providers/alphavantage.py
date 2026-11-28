"""AlphaVantage market data provider adapter."""

import time
from typing import Dict
import httpx
from app.core.config import get_settings
from app.core.instruments import instrument_registry, normalize_symbol
from app.core.logging_config import logger
from app.data.base import MarketDataProvider, ProviderConnectionTestResult, ProviderFetchResult
from app.models.market import DataConnectionStatus, ProviderCapability, Timeframe


AV_INTRADAY_INTERVALS: Dict[Timeframe, str] = {
    Timeframe.M1: "1min",
    Timeframe.M5: "5min",
    Timeframe.M15: "15min",
    Timeframe.M30: "30min",
    Timeframe.H1: "60min",
}


class AlphaVantageProvider(MarketDataProvider):
    """REST adapter for AlphaVantage FX/Daily API (requires ALPHAVANTAGE_API_KEY)."""

    name = "alphavantage"
    BASE_URL = "https://www.alphavantage.co/query"

    def capabilities(self) -> ProviderCapability:
        settings = get_settings()
        supported = [
            inst.symbol
            for inst in instrument_registry.list_instruments()
            if "alphavantage" in inst.supported_providers or "alphavantage" in inst.provider_symbols
        ]
        return ProviderCapability(
            name=self.name,
            configured=bool(settings.alphavantage_api_key.strip()),
            supports_live=False,
            supports_historical=True,
            supported_timeframes=[
                Timeframe.M1,
                Timeframe.M5,
                Timeframe.M15,
                Timeframe.M30,
                Timeframe.H1,
                Timeframe.D1,
            ],
            supported_symbols=supported,
            notes="Requires ALPHAVANTAGE_API_KEY. Supports Forex & USD Crypto. 3m and 4h timeframes are unavailable natively.",
        )

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 300
    ) -> ProviderFetchResult:
        settings = get_settings()
        api_key = settings.alphavantage_api_key.strip()
        unavailable = [Timeframe.M3, Timeframe.H4]
        if not api_key:
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message="ALPHAVANTAGE_API_KEY is not configured.",
                unavailable_timeframes=unavailable,
            )

        norm = normalize_symbol(symbol)
        spec = instrument_registry.get(norm)
        base = spec.base_currency if spec else norm[:3]
        quote = spec.quote_currency if spec else norm[3:]

        if timeframe in AV_INTRADAY_INTERVALS:
            params = {
                "function": "FX_INTRADAY",
                "from_symbol": base,
                "to_symbol": quote,
                "interval": AV_INTRADAY_INTERVALS[timeframe],
                "outputsize": "full" if limit > 100 else "compact",
                "apikey": api_key,
            }
            series_prefix = f"Time Series FX ({AV_INTRADAY_INTERVALS[timeframe]})"
        elif timeframe == Timeframe.D1:
            params = {
                "function": "FX_DAILY",
                "from_symbol": base,
                "to_symbol": quote,
                "outputsize": "full" if limit > 100 else "compact",
                "apikey": api_key,
            }
            series_prefix = "Time Series FX (Daily)"
        else:
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message=f"AlphaVantage does not support {timeframe.value}.",
                unavailable_timeframes=unavailable,
            )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.BASE_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
            if "Note" in payload or "Information" in payload:
                msg = payload.get("Note") or payload.get("Information") or "Rate limited"
                return ProviderFetchResult(
                    provider_name=self.name,
                    connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                    error_message=f"AlphaVantage limit/notice: {msg}",
                    unavailable_timeframes=unavailable,
                )
            if "Error Message" in payload:
                return ProviderFetchResult(
                    provider_name=self.name,
                    connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                    error_message=payload["Error Message"],
                    unavailable_timeframes=unavailable,
                )
            series = payload.get(series_prefix, {})
            candles = [
                {
                    "timestamp": ts,
                    "open": float(vals["1. open"]),
                    "high": float(vals["2. high"]),
                    "low": float(vals["3. low"]),
                    "close": float(vals["4. close"]),
                    "volume": None,
                }
                for ts, vals in series.items()
            ][:limit]
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DELAYED,
                raw_candles=candles,
                unavailable_timeframes=unavailable,
            )
        except Exception as exc:
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message=f"AlphaVantage request failed: {exc}",
                unavailable_timeframes=unavailable,
            )

    async def test_connection(
        self, symbol: str = "EURUSD", timeframe: Timeframe = Timeframe.D1
    ) -> ProviderConnectionTestResult:
        settings = get_settings()
        if not settings.alphavantage_api_key.strip():
            return ProviderConnectionTestResult(
                provider_name=self.name,
                connected=False,
                status="API_KEY_MISSING",
                message="ALPHAVANTAGE_API_KEY is not configured in .env.",
                tested_symbol=symbol,
                tested_timeframe=timeframe.value,
                requires_api_key=True,
                subscription_notes="Free tier provides 25 requests/day and Daily FX; FX_INTRADAY requires a Premium AlphaVantage key.",
            )
        t0 = time.perf_counter()
        res = await self.fetch_candles(symbol, timeframe, limit=5)
        latency = round((time.perf_counter() - t0) * 1000.0, 1)
        if res.raw_candles:
            latest = res.raw_candles[0]
            return ProviderConnectionTestResult(
                provider_name=self.name,
                connected=True,
                status="CONNECTED",
                message=f"Connected to AlphaVantage ({symbol} {timeframe.value}).",
                tested_symbol=symbol,
                tested_timeframe=timeframe.value,
                latency_ms=latency,
                sample_price=float(latest["close"]),
                sample_timestamp=str(latest["timestamp"]),
                requires_api_key=True,
                subscription_notes="Note: Free tier restricts FX_INTRADAY; TwelveData is recommended for live intraday XAUUSD.",
            )
        return ProviderConnectionTestResult(
            provider_name=self.name,
            connected=False,
            status="RATE_LIMITED" if "limit" in res.error_message.lower() else "ERROR",
            message=res.error_message,
            tested_symbol=symbol,
            tested_timeframe=timeframe.value,
            latency_ms=latency,
            requires_api_key=True,
            subscription_notes="Free tier restricts FX_INTRADAY; upgrade or use TwelveData for intraday XAUUSD.",
        )
