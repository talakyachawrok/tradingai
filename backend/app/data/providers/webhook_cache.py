"""Webhook and CSV-uploaded candle cache provider."""

from collections import defaultdict
from typing import Any, Dict, List, Tuple
from app.core.instruments import instrument_registry, normalize_symbol
from app.data.base import MarketDataProvider, ProviderConnectionTestResult, ProviderFetchResult
from app.models.market import DataConnectionStatus, ProviderCapability, Timeframe


class WebhookCacheProvider(MarketDataProvider):
    """Stores OHLCV candles pushed by TradingView webhooks or uploaded CSV datasets."""

    name = "webhook_cache"

    def __init__(self) -> None:
        self._store: Dict[Tuple[str, Timeframe], List[Dict[str, Any]]] = defaultdict(list)

    def push_candles(
        self, symbol: str, timeframe: Timeframe, candles: List[Dict[str, Any]], replace: bool = False
    ) -> int:
        key = (normalize_symbol(symbol), timeframe)
        if replace:
            self._store[key] = list(candles)
        else:
            self._store[key].extend(candles)
            if len(self._store[key]) > 2000:
                self._store[key] = self._store[key][-2000:]
        return len(self._store[key])

    def has_data(self, symbol: str, timeframe: Timeframe) -> bool:
        return len(self._store.get((normalize_symbol(symbol), timeframe), [])) > 0

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            name=self.name,
            configured=True,
            supports_live=False,
            supports_historical=True,
            supported_timeframes=list(Timeframe),
            supported_symbols=[i.symbol for i in instrument_registry.list_instruments()],
            notes="Populated from TradingView webhook payloads or user-uploaded OHLCV CSV files.",
        )

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 300
    ) -> ProviderFetchResult:
        key = (normalize_symbol(symbol), timeframe)
        rows = self._store.get(key, [])
        if not rows:
            return ProviderFetchResult(
                provider_name=self.name,
                connection_status=DataConnectionStatus.DATA_UNAVAILABLE,
                error_message=f"No cached webhook or uploaded CSV candles for {key[0]} ({timeframe.value}).",
            )
        return ProviderFetchResult(
            provider_name=self.name,
            connection_status=DataConnectionStatus.WEBHOOK_CACHE,
            raw_candles=rows[-limit:],
        )

    async def test_connection(
        self, symbol: str = "XAUUSD", timeframe: Timeframe = Timeframe.H1
    ) -> ProviderConnectionTestResult:
        key = (normalize_symbol(symbol), timeframe)
        rows = self._store.get(key, [])
        total_series = sum(1 for v in self._store.values() if v)
        if rows:
            return ProviderConnectionTestResult(
                provider_name=self.name,
                connected=True,
                status="CONNECTED",
                message=f"Found {len(rows)} cached candles for {key[0]} ({timeframe.value}).",
                tested_symbol=key[0],
                tested_timeframe=timeframe.value,
                sample_price=float(rows[-1]["close"]),
                sample_timestamp=str(rows[-1]["timestamp"]),
                requires_api_key=False,
                subscription_notes="Populated via TradingView webhooks or uploaded OHLC CSV files.",
            )
        return ProviderConnectionTestResult(
            provider_name=self.name,
            connected=total_series > 0,
            status="CONNECTED" if total_series > 0 else "EMPTY_CACHE",
            message=(
                f"{total_series} series cached, none for {key[0]} ({timeframe.value})."
                if total_series > 0
                else "No webhook or CSV candles uploaded yet."
            ),
            tested_symbol=key[0],
            tested_timeframe=timeframe.value,
            requires_api_key=False,
            subscription_notes="Upload an OHLC CSV on the Market Analyzer page or send TradingView webhook alerts.",
        )


webhook_cache_provider = WebhookCacheProvider()
