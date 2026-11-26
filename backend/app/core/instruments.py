"""Configurable instrument specifications and symbol registry."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class InstrumentSpec(BaseModel):
    """Trading instrument metadata and contract specifications."""

    symbol: str
    display_name: str
    asset_class: str  # forex, metals, crypto, indices, equities
    base_currency: str
    quote_currency: str
    decimals: int = Field(ge=0, le=8)
    pip_size: Optional[float] = Field(default=None, gt=0)
    contract_size: Optional[float] = Field(default=None, gt=0)
    tick_size: Optional[float] = Field(default=None, gt=0)
    tick_value_per_lot: Optional[float] = Field(default=None, gt=0)
    min_lot: float = Field(default=0.01, gt=0)
    lot_step: float = Field(default=0.01, gt=0)
    typical_spread: Optional[float] = Field(default=None, ge=0)
    provider_symbols: Dict[str, str] = Field(default_factory=dict)
    specs_complete: bool = True
    is_custom: bool = False


DEFAULT_INSTRUMENTS: Dict[str, InstrumentSpec] = {
    "XAUUSD": InstrumentSpec(
        symbol="XAUUSD",
        display_name="Gold / US Dollar",
        asset_class="metals",
        base_currency="XAU",
        quote_currency="USD",
        decimals=2,
        pip_size=0.10,
        contract_size=100.0,  # 1 standard lot = 100 troy oz
        tick_size=0.01,
        tick_value_per_lot=1.0,  # $1.00 per 0.01 move per 1.00 lot
        min_lot=0.01,
        lot_step=0.01,
        typical_spread=0.25,
        provider_symbols={
            "twelvedata": "XAU/USD",
            "alphavantage": "XAU/USD",
            "tradingview": "OANDA:XAUUSD",
        },
        specs_complete=True,
    ),
    "EURUSD": InstrumentSpec(
        symbol="EURUSD",
        display_name="Euro / US Dollar",
        asset_class="forex",
        base_currency="EUR",
        quote_currency="USD",
        decimals=5,
        pip_size=0.0001,
        contract_size=100000.0,
        tick_size=0.00001,
        tick_value_per_lot=1.0,  # $1.00 per 0.00001 move per 1.00 lot ($10/pip)
        min_lot=0.01,
        lot_step=0.01,
        typical_spread=0.00012,
        provider_symbols={
            "twelvedata": "EUR/USD",
            "alphavantage": "EUR/USD",
            "tradingview": "FX:EURUSD",
        },
        specs_complete=True,
    ),
    "GBPUSD": InstrumentSpec(
        symbol="GBPUSD",
        display_name="British Pound / US Dollar",
        asset_class="forex",
        base_currency="GBP",
        quote_currency="USD",
        decimals=5,
        pip_size=0.0001,
        contract_size=100000.0,
        tick_size=0.00001,
        tick_value_per_lot=1.0,
        min_lot=0.01,
        lot_step=0.01,
        typical_spread=0.00015,
        provider_symbols={
            "twelvedata": "GBP/USD",
            "alphavantage": "GBP/USD",
            "tradingview": "FX:GBPUSD",
        },
        specs_complete=True,
    ),
    "BTCUSD": InstrumentSpec(
        symbol="BTCUSD",
        display_name="Bitcoin / US Dollar",
        asset_class="crypto",
        base_currency="BTC",
        quote_currency="USD",
        decimals=2,
        pip_size=1.0,
        contract_size=1.0,  # 1 lot / unit = 1 BTC
        tick_size=0.01,
        tick_value_per_lot=0.01,
        min_lot=0.001,
        lot_step=0.001,
        typical_spread=15.0,
        provider_symbols={
            "twelvedata": "BTC/USD",
            "alphavantage": "BTC/USD",
            "binance_public": "BTCUSDT",
            "tradingview": "BITSTAMP:BTCUSD",
        },
        specs_complete=True,
    ),
}


class InstrumentRegistry:
    """In-memory + persisted registry for default and user-configured instruments."""

    def __init__(self) -> None:
        self._instruments: Dict[str, InstrumentSpec] = {
            k: v.model_copy(deep=True) for k, v in DEFAULT_INSTRUMENTS.items()
        }

    def list_instruments(self) -> List[InstrumentSpec]:
        return list(self._instruments.values())

    def get(self, symbol: str) -> Optional[InstrumentSpec]:
        normalized = normalize_symbol(symbol)
        return self._instruments.get(normalized)

    def add_or_update(self, spec: InstrumentSpec) -> InstrumentSpec:
        normalized = normalize_symbol(spec.symbol)
        has_all_sizing = (
            spec.contract_size is not None
            and spec.tick_size is not None
            and spec.tick_value_per_lot is not None
        )
        updated = spec.model_copy(
            update={"symbol": normalized, "specs_complete": has_all_sizing}
        )
        self._instruments[normalized] = updated
        return updated

    def remove_custom(self, symbol: str) -> bool:
        normalized = normalize_symbol(symbol)
        if normalized in DEFAULT_INSTRUMENTS:
            return False
        return self._instruments.pop(normalized, None) is not None


def normalize_symbol(symbol: str) -> str:
    """Normalize ticker strings like 'OANDA:XAUUSD', 'XAU/USD', 'btcusdt'."""
    cleaned = symbol.strip().upper()
    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[1]
    cleaned = cleaned.replace("/", "").replace("-", "")
    if cleaned == "BTCUSDT":
        cleaned = "BTCUSD"
    return cleaned


instrument_registry = InstrumentRegistry()
