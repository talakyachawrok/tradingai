"""Market data, OHLCV, timeframe, and data integrity Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class Timeframe(str, Enum):
    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


TIMEFRAME_SECONDS: Dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M3: 180,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
}


class DataConnectionStatus(str, Enum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    DEMO_MODE = "DEMO_MODE"
    WEBHOOK_CACHE = "WEBHOOK_CACHE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class OHLCVCandle(BaseModel):
    """Single validated OHLCV candlestick."""

    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_ohlc_bounds(self) -> "OHLCVCandle":
        if self.high < max(self.open, self.close):
            raise ValueError("Candle high must be >= max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError("Candle low must be <= min(open, close)")
        if self.high < self.low:
            raise ValueError("Candle high must be >= low")
        return self


class DataIntegrityReport(BaseModel):
    """Audit report from OHLCV data validation."""

    raw_count: int
    valid_count: int
    duplicates_removed: int = 0
    invalid_candles_dropped: int = 0
    time_gaps_detected: int = 0
    gap_timestamps: List[datetime] = Field(default_factory=list)
    is_stale: bool = False
    stale_seconds: Optional[float] = None
    has_volume: bool = False
    warnings: List[str] = Field(default_factory=list)


class ProviderCapability(BaseModel):
    """Describes what a market data provider supports."""

    name: str
    configured: bool
    supports_live: bool
    supports_historical: bool
    supported_timeframes: List[Timeframe]
    supported_symbols: List[str]
    notes: str = ""


class MarketOverview(BaseModel):
    """Market overview header displayed on the main dashboard."""

    symbol: str
    display_name: str
    timeframe: Timeframe
    current_price: Optional[float] = None
    price_change: Optional[float] = None
    price_change_pct: Optional[float] = None
    market_session: str
    session_status: str
    data_source: str
    connection_status: DataConnectionStatus
    last_data_update: Optional[datetime] = None
    market_status: str
    volatility_condition: str
    is_demo: bool = False
    status_message: str = ""


class MarketDataResponse(BaseModel):
    """Full response returned by the market data endpoint."""

    overview: MarketOverview
    candles: List[OHLCVCandle] = Field(default_factory=list)
    integrity: DataIntegrityReport
    unavailable_timeframes: List[Timeframe] = Field(default_factory=list)
    cache_hit: bool = False
