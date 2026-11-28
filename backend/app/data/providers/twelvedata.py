"""TwelveData market data provider adapter (XAUUSD, EURUSD, GBPUSD, BTCUSD)."""

import time
from typing import Dict
import httpx
from app.core.config import get_settings
from app.core.instruments import instrument_registry, normalize_symbol
from app.core.logging_config import logger
from app.data.base import MarketDataProvider, ProviderConnectionTestResult, ProviderFetchResult
from app.models.market import DataConnectionStatus, ProviderCapability, Timeframe


TWELVEDATA_INTERVALS: Dict[Timeframe, str] = {
    Timeframe.M1: "1min",
    Timeframe.M5: "5min",
    Timeframe.M15: "15min",
    Timeframe.M30: "30min",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1day",
}


def resolve_twelvedata_symbol(symbol: str) -> str:
    norm = normalize_symbol(symbol)
    spec = instrument_registry.get(norm)
    if spec and spec.provider_symbols.get("twelvedata"):
        return spec.provider_symbols["twelvedata"]
    # Standard 6-char FX/metal/crypto ticker -> BASE/QUOTE
    if len(norm) == 6 and norm.isalpha():
        return f"{norm[:3]}/{norm[3:]}"
    return norm


class TwelveDataProvider(MarketDataProvider):
    """REST adapter for TwelveData API (requires TWELVEDATA_API_KEY in .env)."""

    name = "twelvedata"
    BASE_URL = "https://api.twelvedata.com/time_series"

    def capabilities(self) -> ProviderCapability:
        settings = get_settings()
        supported = [
            inst.symbol
            for inst in instrument_registry.list_instruments()
            if "twelvedata" in inst.supported_providers or "twelvedata" in inst.provider_symbols
        ]
        return ProviderCapability(
            name=self.name,
            configured=bool(settings.twelvedata_api_key.strip()),
            supports_live=True,
            supports_historical=True,
            supported_timeframes=list(TWELVEDATA_INTERVALS.keys()),
            supported_symbols=supported,
            notes=(
                "Primary multi-asset provider (Forex, Crypto, Commodities, Indices, US Stocks). "
                "Requires TWELVEDATA_API_KEY in .env (free Basic plan includes 8 credits/min, 800/day). "
                "3m timeframe is not natively supported by TwelveData."
            ),
        )

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 300
    ) -> ProviderFetchResult:
        settings = get_settings()
        api_key = settings.twelvedata_api_key.strip()
        unavailable = [Timeframe.M3]
        if not api_key:
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message="TWELVEDATA_API_KEY is not configured in .env.",
                unavailable_timeframes=unavailable,
            )

        interval = TWELVEDATA_INTERVALS.get(timeframe)
        if not interval:
            logger.warning("TwelveData does not support timeframe %s", timeframe.value)
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message=f"TwelveData does not natively support the {timeframe.value} timeframe.",
                unavailable_timeframes=unavailable,
            )

        mapped = resolve_twelvedata_symbol(symbol)
        try:
            logger.info("Fetching TwelveData time_series symbol=%s interval=%s limit=%s", mapped, interval, limit)
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "symbol": mapped,
                        "interval": interval,
                        "outputsize": min(limit, 5000),
                        "apikey": api_key,
                        "timezone": "UTC",
                    },
                )

            if resp.status_code == 401:
                logger.error("TwelveData HTTP 401 Invalid API key")
                return ProviderFetchResult(
                    provider_name=self.name,
                    connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                    error_message="Invalid TWELVEDATA_API_KEY (HTTP 401).",
                    unavailable_timeframes=unavailable,
                )
            if resp.status_code == 429:
                logger.warning("TwelveData HTTP 429 rate limit exceeded")
                return ProviderFetchResult(
                    provider_name=self.name,
                    connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                    error_message="TwelveData rate limit exceeded (HTTP 429). Wait 60s or upgrade plan.",
                    unavailable_timeframes=unavailable,
                )

            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") == "error":
                code = payload.get("code")
                msg = str(payload.get("message", "Unknown TwelveData error"))
                logger.error("TwelveData API error code=%s msg=%s", code, msg)
                if code == 401 or "apikey" in msg.lower():
                    msg = f"Invalid TWELVEDATA_API_KEY: {msg}"
                elif code == 429 or "limit" in msg.lower():
                    msg = f"TwelveData rate limit reached: {msg}"
                return ProviderFetchResult(
                    provider_name=self.name,
                    connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                    error_message=msg,
                    unavailable_timeframes=unavailable,
                )

            values = payload.get("values") or []
            if not values:
                logger.warning("TwelveData returned empty values for %s (%s)", mapped, interval)
                return ProviderFetchResult(
                    provider_name=self.name,
                    connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                    error_message=f"TwelveData returned no candles for {mapped} ({interval}).",
                    unavailable_timeframes=unavailable,
                )

            candles = [
                {
                    "timestamp": item["datetime"],
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    # Preserve None when FX/Metal provider omits volume (never invent volume)
                    "volume": float(item["volume"])
                    if item.get("volume") not in (None, "", "null")
                    else None,
                }
                for item in values
            ]
            logger.info("TwelveData fetched %d candles for %s (%s)", len(candles), mapped, interval)
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.LIVE,
                raw_candles=candles,
                unavailable_timeframes=unavailable,
            )
        except httpx.TimeoutException:
            logger.error("TwelveData request timeout for %s (%s)", mapped, interval)
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message="TwelveData API request timed out.",
                unavailable_timeframes=unavailable,
            )
        except httpx.RequestError as exc:
            logger.error("TwelveData network error: %s", exc)
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message=f"Network error reaching TwelveData: {exc}",
                unavailable_timeframes=unavailable,
            )
        except Exception as exc:
            logger.exception("Unexpected TwelveData error")
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message=f"TwelveData request failed: {exc}",
                unavailable_timeframes=unavailable,
            )

    async def test_connection(
        self, symbol: str = "XAUUSD", timeframe: Timeframe = Timeframe.H1
    ) -> ProviderConnectionTestResult:
        settings = get_settings()
        api_key = settings.twelvedata_api_key.strip()
        test_tf = timeframe if timeframe in TWELVEDATA_INTERVALS else Timeframe.H1
        if not api_key:
            return ProviderConnectionTestResult(
                provider_name=self.name,
                connected=False,
                status="API_KEY_MISSING",
                message="TWELVEDATA_API_KEY is not set in .env.",
                tested_symbol=symbol,
                tested_timeframe=test_tf.value,
                requires_api_key=True,
                subscription_notes="Sign up at twelvedata.com (Free Basic plan includes XAU/USD, EUR/USD, GBP/USD, BTC/USD; 8 credits/min, 800/day).",
            )

        t0 = time.perf_counter()
        res = await self.fetch_candles(symbol, test_tf, limit=3)
        latency = round((time.perf_counter() - t0) * 1000.0, 1)
        if res.raw_candles:
            latest = res.raw_candles[0]  # TwelveData returns newest bar first before validator sorts
            return ProviderConnectionTestResult(
                provider_name=self.name,
                connected=True,
                status="CONNECTED",
                message=f"Connected to TwelveData ({resolve_twelvedata_symbol(symbol)} {test_tf.value}).",
                tested_symbol=symbol,
                tested_timeframe=test_tf.value,
                latency_ms=latency,
                sample_price=float(latest["close"]),
                sample_timestamp=str(latest["timestamp"]),
                requires_api_key=True,
                subscription_notes="Free Basic tier supports 8 calls/min & 800 calls/day; 3m timeframe unsupported.",
            )

        err_low = res.error_message.lower()
        status = (
            "INVALID_API_KEY"
            if "invalid" in err_low or "401" in err_low
            else ("RATE_LIMITED" if "rate limit" in err_low or "429" in err_low else "ERROR")
        )
        return ProviderConnectionTestResult(
            provider_name=self.name,
            connected=False,
            status=status,
            message=res.error_message,
            tested_symbol=symbol,
            tested_timeframe=test_tf.value,
            latency_ms=latency,
            requires_api_key=True,
            subscription_notes="Check TWELVEDATA_API_KEY in .env and ensure your plan covers the requested symbol.",
        )
