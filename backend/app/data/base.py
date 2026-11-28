"""Abstract market data provider interface and standardized result contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.models.market import DataConnectionStatus, ProviderCapability, Timeframe


@dataclass
class ProviderFetchResult:
    provider_name: str
    connection_status: DataConnectionStatus
    raw_candles: List[Dict[str, Any]] = field(default_factory=list)
    is_demo: bool = False
    error_message: str = ""
    unavailable_timeframes: List[Timeframe] = field(default_factory=list)


@dataclass
class ProviderConnectionTestResult:
    provider_name: str
    connected: bool
    status: str  # CONNECTED, API_KEY_MISSING, INVALID_API_KEY, RATE_LIMITED, UNSUPPORTED, ERROR
    message: str
    tested_symbol: str
    tested_timeframe: str
    latency_ms: Optional[float] = None
    sample_price: Optional[float] = None
    sample_timestamp: Optional[str] = None
    requires_api_key: bool = True
    subscription_notes: str = ""


class MarketDataProvider(ABC):
    """Base contract for all market data provider adapters."""

    name: str = "base"

    @abstractmethod
    def capabilities(self) -> ProviderCapability:
        """Return provider configuration state and supported symbols/timeframes."""

    @abstractmethod
    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 300
    ) -> ProviderFetchResult:
        """Fetch raw OHLCV candle dicts for validation."""

    async def test_connection(
        self, symbol: str = "XAUUSD", timeframe: Timeframe = Timeframe.H1
    ) -> ProviderConnectionTestResult:
        """Actively test provider connectivity/credentials without fabricating data."""
        res = await self.fetch_candles(symbol, timeframe, limit=5)
        ok = len(res.raw_candles) > 0 and res.connection_status != DataConnectionStatus.DATA_UNAVAILABLE
        return ProviderConnectionTestResult(
            provider_name=self.name,
            connected=ok,
            status="CONNECTED" if ok else "ERROR",
            message="Connection verified." if ok else (res.error_message or "No data returned."),
            tested_symbol=symbol,
            tested_timeframe=timeframe.value,
            sample_price=float(res.raw_candles[-1]["close"]) if res.raw_candles else None,
            sample_timestamp=str(res.raw_candles[-1]["timestamp"]) if res.raw_candles else None,
        )
