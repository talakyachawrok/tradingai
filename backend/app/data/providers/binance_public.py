"""Binance public REST market data adapter (supports BTCUSD via BTCUSDT without API key)."""

import time
from typing import Dict
import httpx
from app.core.instruments import instrument_registry, normalize_symbol
from app.core.logging_config import logger
from app.data.base import MarketDataProvider, ProviderConnectionTestResult, ProviderFetchResult
from app.models.market import DataConnectionStatus, ProviderCapability, Timeframe


BINANCE_INTERVALS: Dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M3: "3m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
}


class BinancePublicProvider(MarketDataProvider):
    """Public Binance Spot API adapter for crypto pairs (e.g. BTCUSD -> BTCUSDT)."""

    name = "binance_public"
    BASE_URL = "https://api.binance.com/api/v3/klines"

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            name=self.name,
            configured=True,
            supports_live=True,
            supports_historical=True,
            supported_timeframes=list(BINANCE_INTERVALS.keys()),
            supported_symbols=["BTCUSD"],
            notes="Public REST klines for BTCUSD (BTCUSDT) across all 8 timeframes. No API key required.",
        )

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 300
    ) -> ProviderFetchResult:
        norm = normalize_symbol(symbol)
        spec = instrument_registry.get(norm)
        mapped = spec.provider_symbols.get(self.name) if spec else None
        if not mapped:
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message=f"{norm} is not supported by Binance Public provider (crypto only).",
            )

        interval = BINANCE_INTERVALS.get(timeframe)
        if not interval:
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message=f"Timeframe {timeframe.value} is not supported.",
            )

        try:
            logger.info("Fetching Binance public klines symbol=%s interval=%s limit=%s", mapped, interval, limit)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={"symbol": mapped, "interval": interval, "limit": min(limit, 1000)},
                )
            if resp.status_code == 429:
                logger.warning("Binance HTTP 429 rate limit exceeded")
                return ProviderFetchResult(
                    provider_name=self.name,
                    connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                    error_message="Binance API rate limit reached (HTTP 429).",
                )
            if resp.status_code == 400:
                return ProviderFetchResult(
                    provider_name=self.name,
                    connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                    error_message=f"Binance rejected symbol or interval ({mapped}, {interval}).",
                )
            resp.raise_for_status()
            rows = resp.json()
            candles = [
                {
                    "timestamp": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
                for row in rows
            ]
            logger.info("Binance fetched %d candles for %s (%s)", len(candles), mapped, interval)
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.LIVE,
                raw_candles=candles,
            )
        except httpx.TimeoutException:
            logger.error("Binance API timeout for %s (%s)", mapped, interval)
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message="Binance public API timed out.",
            )
        except Exception as exc:
            logger.error("Binance API error: %s", exc)
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message=f"Binance public API unreachable: {exc}",
            )

    async def test_connection(
        self, symbol: str = "BTCUSD", timeframe: Timeframe = Timeframe.H1
    ) -> ProviderConnectionTestResult:
        test_sym = "BTCUSD" if normalize_symbol(symbol) != "BTCUSD" else symbol
        t0 = time.perf_counter()
        res = await self.fetch_candles(test_sym, timeframe, limit=2)
        latency = round((time.perf_counter() - t0) * 1000.0, 1)
        if res.raw_candles:
            latest = res.raw_candles[-1]
            return ProviderConnectionTestResult(
                provider_name=self.name,
                connected=True,
                status="CONNECTED",
                message="Connected to Binance Public Spot API (BTCUSDT).",
                tested_symbol=test_sym,
                tested_timeframe=timeframe.value,
                latency_ms=latency,
                sample_price=float(latest["close"]),
                sample_timestamp=str(latest["timestamp"]),
                requires_api_key=False,
                subscription_notes="Free public endpoint for BTCUSD only (no API key needed).",
            )
        return ProviderConnectionTestResult(
            provider_name=self.name,
            connected=False,
            status="ERROR",
            message=res.error_message or "Binance public API unreachable.",
            tested_symbol=test_sym,
            tested_timeframe=timeframe.value,
            latency_ms=latency,
            requires_api_key=False,
            subscription_notes="Check internet connectivity or firewall access to api.binance.com.",
        )
