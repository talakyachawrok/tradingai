"""Public Crypto Spot REST market data adapter (Binance Global -> Binance.US / Kraken fallback for US servers)."""

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

KRAKEN_INTERVALS: Dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
    Timeframe.D1: 1440,
}


class BinancePublicProvider(MarketDataProvider):
    """
    Public Spot REST adapter for crypto pairs (BTCUSD).
    Uses Binance Global (`api.binance.com`), automatically falling back to
    Binance.US (`api.binance.us`) and Kraken (`api.kraken.com`) if the host
    region (such as Render US servers) receives HTTP 451 geo-restrictions.
    """

    name = "binance_public"
    GLOBAL_URL = "https://api.binance.com/api/v3/klines"
    US_URL = "https://api.binance.us/api/v3/klines"
    KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"

    def capabilities(self) -> ProviderCapability:
        supported = [
            inst.symbol
            for inst in instrument_registry.list_instruments()
            if "binance_public" in inst.supported_providers or "binance_public" in inst.provider_symbols
        ]
        return ProviderCapability(
            name=self.name,
            configured=True,
            supports_live=True,
            supports_historical=True,
            supported_timeframes=list(BINANCE_INTERVALS.keys()),
            supported_symbols=supported,
            notes="Public REST klines for major Crypto pairs (auto-falls back to Binance.US / Kraken on HTTP 451 regions). No API key required.",
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

        last_error = ""
        for endpoint_url in (self.GLOBAL_URL, self.US_URL):
            try:
                logger.info("Fetching %s symbol=%s interval=%s limit=%s", endpoint_url, mapped, interval, limit)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        endpoint_url,
                        params={"symbol": mapped, "interval": interval, "limit": min(limit, 1000)},
                    )
                if resp.status_code == 451:
                    last_error = f"{endpoint_url} geo-restricted (HTTP 451)"
                    logger.warning("%s; trying next crypto public fallback", last_error)
                    continue
                if resp.status_code == 429:
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
                logger.info("Fetched %d candles from %s for %s (%s)", len(candles), endpoint_url, mapped, interval)
                return ProviderFetchResult(
                    provider_name=self.name,
                    connection_status=DataConnectionStatus.LIVE,
                    raw_candles=candles,
                )
            except httpx.TimeoutException:
                last_error = f"{endpoint_url} timed out"
                logger.warning(last_error)
            except Exception as exc:
                last_error = f"{endpoint_url} error: {exc}"
                logger.warning(last_error)

        # Fallback to Kraken public OHLC (works globally, including US Render servers)
        kraken_interval = KRAKEN_INTERVALS.get(timeframe)
        kraken_pair = spec.provider_symbols.get("kraken_public") if spec else None
        if kraken_interval is not None and kraken_pair:
            try:
                logger.info("Falling back to Kraken public OHLC for %s (%s) interval=%sm", norm, kraken_pair, kraken_interval)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        self.KRAKEN_URL,
                        params={"pair": kraken_pair, "interval": kraken_interval},
                    )
                resp.raise_for_status()
                payload = resp.json()
                if not payload.get("error"):
                    result = payload.get("result", {})
                    pair_key = next((k for k in result.keys() if k != "last"), None)
                    if pair_key:
                        rows = result[pair_key][-limit:]
                        candles = [
                            {
                                "timestamp": int(row[0]) * 1000,
                                "open": float(row[1]),
                                "high": float(row[2]),
                                "low": float(row[3]),
                                "close": float(row[4]),
                                "volume": float(row[6]),
                            }
                            for row in rows
                        ]
                        logger.info("Kraken fetched %d candles for %s (%s)", len(candles), norm, timeframe.value)
                        return ProviderFetchResult(
                            provider_name="kraken_public (binance fallback)",
                            connection_status=DataConnectionStatus.LIVE,
                            raw_candles=candles,
                        )
            except Exception as exc:
                last_error = f"{last_error} | Kraken fallback error: {exc}"

        return ProviderFetchResult(
            provider_name=self.name,
            connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
            error_message=f"Crypto public API unreachable: {last_error}",
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
                message=f"Connected to {res.provider_name} for {test_sym}.",
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
            message=res.error_message or "Crypto public API unreachable.",
            tested_symbol=test_sym,
            tested_timeframe=timeframe.value,
            latency_ms=latency,
            requires_api_key=False,
            subscription_notes="Check internet connectivity or provider access.",
        )
