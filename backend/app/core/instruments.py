"""Configurable instrument catalog, categories, contract specs, and provider symbol mapping."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class InstrumentSpec(BaseModel):
    """Trading instrument metadata, provider mappings, and contract specifications."""

    symbol: str
    display_name: str
    asset_class: str  # forex, crypto, commodities, indices, stocks
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
    supported_providers: List[str] = Field(default_factory=list)
    specs_complete: bool = True
    is_custom: bool = False


def _fx(
    symbol: str,
    name: str,
    pip_size: float = 0.0001,
    decimals: int = 5,
    tick_size: float = 0.00001,
    tick_value_per_lot: Optional[float] = None,
) -> InstrumentSpec:
    base, quote = symbol[:3], symbol[3:]
    is_usd_quote = quote == "USD"
    # Exact USD pip/tick value only known without FX conversion when quote == USD
    tv = tick_value_per_lot if tick_value_per_lot is not None else (1.0 if is_usd_quote else None)
    return InstrumentSpec(
        symbol=symbol,
        display_name=name,
        asset_class="forex",
        base_currency=base,
        quote_currency=quote,
        decimals=decimals,
        pip_size=pip_size,
        contract_size=100000.0,
        tick_size=tick_size,
        tick_value_per_lot=tv,
        min_lot=0.01,
        lot_step=0.01,
        provider_symbols={
            "twelvedata": f"{base}/{quote}",
            "alphavantage": f"{base}/{quote}",
            "tradingview": f"FX:{symbol}",
        },
        supported_providers=["twelvedata", "alphavantage", "webhook_cache", "demo_historical"],
        specs_complete=tv is not None,
    )


def _crypto(
    symbol: str,
    name: str,
    binance_symbol: str,
    td_symbol: str,
    decimals: int = 2,
    pip_size: float = 1.0,
    tick_size: float = 0.01,
    kraken_symbol: Optional[str] = None,
) -> InstrumentSpec:
    quote = "USDT" if symbol.endswith("USDT") else "USD"
    base = symbol[: -len(quote)]
    providers: Dict[str, str] = {
        "twelvedata": td_symbol,
        "binance_public": binance_symbol,
        "tradingview": f"BINANCE:{binance_symbol}" if quote == "USDT" else f"BITSTAMP:{symbol}",
    }
    if kraken_symbol:
        providers["kraken_public"] = kraken_symbol
    if quote == "USD":
        providers["alphavantage"] = f"{base}/USD"

    return InstrumentSpec(
        symbol=symbol,
        display_name=name,
        asset_class="crypto",
        base_currency=base,
        quote_currency=quote,
        decimals=decimals,
        pip_size=pip_size,
        contract_size=1.0,
        tick_size=tick_size,
        tick_value_per_lot=tick_size,
        min_lot=0.001 if base in ("BTC", "ETH") else 1.0,
        lot_step=0.001 if base in ("BTC", "ETH") else 1.0,
        provider_symbols=providers,
        supported_providers=(
            ["twelvedata", "binance_public", "alphavantage", "webhook_cache", "demo_historical"]
            if quote == "USD"
            else ["twelvedata", "binance_public", "webhook_cache", "demo_historical"]
        ),
        specs_complete=True,
    )


def _commodity(
    symbol: str,
    name: str,
    base: str,
    td_symbol: str,
    decimals: int,
    pip_size: float,
    contract_size: Optional[float] = None,
    tick_size: Optional[float] = None,
    tick_value_per_lot: Optional[float] = None,
    tv_symbol: Optional[str] = None,
) -> InstrumentSpec:
    has_specs = contract_size is not None and tick_size is not None and tick_value_per_lot is not None
    return InstrumentSpec(
        symbol=symbol,
        display_name=name,
        asset_class="commodities",
        base_currency=base,
        quote_currency="USD",
        decimals=decimals,
        pip_size=pip_size,
        contract_size=contract_size,
        tick_size=tick_size,
        tick_value_per_lot=tick_value_per_lot,
        min_lot=0.01,
        lot_step=0.01,
        provider_symbols={
            "twelvedata": td_symbol,
            "tradingview": tv_symbol or f"OANDA:{symbol}",
        },
        supported_providers=["twelvedata", "webhook_cache", "demo_historical"],
        specs_complete=has_specs,
    )


def _index(symbol: str, name: str, td_symbol: str, tv_symbol: str, quote: str = "USD") -> InstrumentSpec:
    return InstrumentSpec(
        symbol=symbol,
        display_name=name,
        asset_class="indices",
        base_currency=symbol,
        quote_currency=quote,
        decimals=2,
        pip_size=1.0,
        min_lot=0.01,
        lot_step=0.01,
        provider_symbols={
            "twelvedata": td_symbol,
            "tradingview": tv_symbol,
        },
        supported_providers=["twelvedata", "webhook_cache", "demo_historical"],
        specs_complete=False,
    )


def _stock(symbol: str, name: str) -> InstrumentSpec:
    return InstrumentSpec(
        symbol=symbol,
        display_name=name,
        asset_class="stocks",
        base_currency=symbol,
        quote_currency="USD",
        decimals=2,
        pip_size=0.01,
        contract_size=1.0,
        tick_size=0.01,
        tick_value_per_lot=0.01,
        min_lot=1.0,
        lot_step=1.0,
        provider_symbols={
            "twelvedata": symbol,
            "tradingview": f"NASDAQ:{symbol}",
        },
        supported_providers=["twelvedata", "webhook_cache", "demo_historical"],
        specs_complete=True,
    )


_CATALOG: List[InstrumentSpec] = [
    # --- FOREX (27 Major, Minor & Exotic Pairs) ---
    _fx("EURUSD", "Euro / US Dollar"),
    _fx("GBPUSD", "British Pound / US Dollar"),
    _fx("USDJPY", "US Dollar / Japanese Yen", pip_size=0.01, decimals=3, tick_size=0.001),
    _fx("USDCHF", "US Dollar / Swiss Franc"),
    _fx("USDCAD", "US Dollar / Canadian Dollar"),
    _fx("AUDUSD", "Australian Dollar / US Dollar"),
    _fx("NZDUSD", "New Zealand Dollar / US Dollar"),
    _fx("EURJPY", "Euro / Japanese Yen", pip_size=0.01, decimals=3, tick_size=0.001),
    _fx("GBPJPY", "British Pound / Japanese Yen", pip_size=0.01, decimals=3, tick_size=0.001),
    _fx("EURGBP", "Euro / British Pound"),
    _fx("AUDJPY", "Australian Dollar / Japanese Yen", pip_size=0.01, decimals=3, tick_size=0.001),
    _fx("EURAUD", "Euro / Australian Dollar"),
    _fx("GBPAUD", "British Pound / Australian Dollar"),
    _fx("AUDNZD", "Australian Dollar / New Zealand Dollar"),
    _fx("EURCHF", "Euro / Swiss Franc"),
    _fx("GBPCHF", "British Pound / Swiss Franc"),
    _fx("CADJPY", "Canadian Dollar / Japanese Yen", pip_size=0.01, decimals=3, tick_size=0.001),
    _fx("NZDJPY", "New Zealand Dollar / Japanese Yen", pip_size=0.01, decimals=3, tick_size=0.001),
    _fx("CHFJPY", "Swiss Franc / Japanese Yen", pip_size=0.01, decimals=3, tick_size=0.001),
    _fx("EURNZD", "Euro / New Zealand Dollar"),
    _fx("GBPNZD", "British Pound / New Zealand Dollar"),
    _fx("AUDCAD", "Australian Dollar / Canadian Dollar"),
    _fx("NZDCAD", "New Zealand Dollar / Canadian Dollar"),
    _fx("CADCHF", "Canadian Dollar / Swiss Franc"),
    _fx("USDZAR", "US Dollar / South African Rand", pip_size=0.0001, decimals=4, tick_size=0.0001),
    _fx("USDMXN", "US Dollar / Mexican Peso", pip_size=0.0001, decimals=4, tick_size=0.0001),
    _fx("USDTRY", "US Dollar / Turkish Lira", pip_size=0.0001, decimals=4, tick_size=0.0001),

    # --- CRYPTO (Major Spot & Exchange-Specific USDT Pairs) ---
    _crypto("BTCUSD", "Bitcoin / US Dollar", "BTCUSDT", "BTC/USD", decimals=2, pip_size=1.0, tick_size=0.01, kraken_symbol="XBTUSD"),
    _crypto("ETHUSD", "Ethereum / US Dollar", "ETHUSDT", "ETH/USD", decimals=2, pip_size=0.1, tick_size=0.01, kraken_symbol="ETHUSD"),
    _crypto("BNBUSD", "BNB / US Dollar", "BNBUSDT", "BNB/USD", decimals=2, pip_size=0.1, tick_size=0.01),
    _crypto("SOLUSD", "Solana / US Dollar", "SOLUSDT", "SOL/USD", decimals=2, pip_size=0.01, tick_size=0.01, kraken_symbol="SOLUSD"),
    _crypto("XRPUSD", "XRP / US Dollar", "XRPUSDT", "XRP/USD", decimals=4, pip_size=0.0001, tick_size=0.0001, kraken_symbol="XRPUSD"),
    _crypto("ADAUSD", "Cardano / US Dollar", "ADAUSDT", "ADA/USD", decimals=4, pip_size=0.0001, tick_size=0.0001, kraken_symbol="ADAUSD"),
    _crypto("DOGEUSD", "Dogecoin / US Dollar", "DOGEUSDT", "DOGE/USD", decimals=5, pip_size=0.0001, tick_size=0.00001, kraken_symbol="DOGEUSD"),
    _crypto("AVAXUSD", "Avalanche / US Dollar", "AVAXUSDT", "AVAX/USD", decimals=2, pip_size=0.01, tick_size=0.01, kraken_symbol="AVAXUSD"),
    _crypto("LINKUSD", "Chainlink / US Dollar", "LINKUSDT", "LINK/USD", decimals=3, pip_size=0.01, tick_size=0.001, kraken_symbol="LINKUSD"),
    _crypto("DOTUSD", "Polkadot / US Dollar", "DOTUSDT", "DOT/USD", decimals=3, pip_size=0.01, tick_size=0.001, kraken_symbol="DOTUSD"),
    _crypto("LTCUSD", "Litecoin / US Dollar", "LTCUSDT", "LTC/USD", decimals=2, pip_size=0.01, tick_size=0.01, kraken_symbol="LTCUSD"),
    _crypto("BCHUSD", "Bitcoin Cash / US Dollar", "BCHUSDT", "BCH/USD", decimals=2, pip_size=0.1, tick_size=0.01, kraken_symbol="BCHUSD"),
    _crypto("TRXUSD", "TRON / US Dollar", "TRXUSDT", "TRX/USD", decimals=5, pip_size=0.0001, tick_size=0.00001, kraken_symbol="TRXUSD"),
    _crypto("TONUSD", "Toncoin / US Dollar", "TONUSDT", "TON/USD", decimals=3, pip_size=0.01, tick_size=0.001, kraken_symbol="TONUSD"),
    _crypto("BTCUSDT", "Bitcoin / Tether (Spot)", "BTCUSDT", "BTC/USD", decimals=2, pip_size=1.0, tick_size=0.01, kraken_symbol="XBTUSD"),
    _crypto("ETHUSDT", "Ethereum / Tether (Spot)", "ETHUSDT", "ETH/USD", decimals=2, pip_size=0.1, tick_size=0.01, kraken_symbol="ETHUSD"),

    # --- COMMODITIES ---
    _commodity("XAUUSD", "Gold / US Dollar", "XAU", "XAU/USD", decimals=2, pip_size=0.10, contract_size=100.0, tick_size=0.01, tick_value_per_lot=1.0, tv_symbol="OANDA:XAUUSD"),
    _commodity("XAGUSD", "Silver / US Dollar", "XAG", "XAG/USD", decimals=3, pip_size=0.01, contract_size=5000.0, tick_size=0.001, tick_value_per_lot=5.0, tv_symbol="OANDA:XAGUSD"),
    _commodity("WTI", "WTI Crude Oil / US Dollar", "WTI", "WTI/USD", decimals=2, pip_size=0.01, tv_symbol="TVC:USOIL"),
    _commodity("BRENT", "Brent Crude Oil / US Dollar", "BRENT", "XBR/USD", decimals=2, pip_size=0.01, tv_symbol="TVC:UKOIL"),
    _commodity("NATGAS", "Natural Gas / US Dollar", "NG", "NG/USD", decimals=3, pip_size=0.001, tv_symbol="NYMEX:NG1!"),

    # --- INDICES ---
    _index("US500", "S&P 500 Index", "SPX", "SP:SPX"),
    _index("NAS100", "Nasdaq 100 Index", "NDX", "NASDAQ:NDX"),
    _index("US30", "Dow Jones 30 Index", "DJI", "DJ:DJI"),
    _index("GER40", "DAX 40 Germany Index", "GDAXI", "XETR:DAX", quote="EUR"),
    _index("UK100", "FTSE 100 UK Index", "FTSE", "FTSE:UKX", quote="GBP"),
    _index("JP225", "Nikkei 225 Japan Index", "N225", "TVC:NI225", quote="JPY"),
    _index("AUS200", "ASX 200 Australia Index", "AXJO", "ASX:XJO", quote="AUD"),

    # --- US STOCKS ---
    _stock("AAPL", "Apple Inc."),
    _stock("MSFT", "Microsoft Corporation"),
    _stock("NVDA", "NVIDIA Corporation"),
    _stock("AMZN", "Amazon.com Inc."),
    _stock("META", "Meta Platforms Inc."),
    _stock("GOOGL", "Alphabet Inc. (Class A)"),
    _stock("TSLA", "Tesla Inc."),
    _stock("AMD", "Advanced Micro Devices Inc."),
    _stock("NFLX", "Netflix Inc."),
    _stock("JPM", "JPMorgan Chase & Co."),
    _stock("AVGO", "Broadcom Inc."),
    _stock("PLTR", "Palantir Technologies Inc."),
]

DEFAULT_INSTRUMENTS: Dict[str, InstrumentSpec] = {item.symbol: item for item in _CATALOG}

# Preserve expected provider symbols for XAUUSD / EURUSD / GBPUSD / BTCUSD
DEFAULT_INSTRUMENTS["XAUUSD"].typical_spread = 0.25
DEFAULT_INSTRUMENTS["EURUSD"].typical_spread = 0.00012
DEFAULT_INSTRUMENTS["GBPUSD"].typical_spread = 0.00015
DEFAULT_INSTRUMENTS["BTCUSD"].typical_spread = 15.0


class InstrumentRegistry:
    """In-memory registry for built-in categorized and custom user instruments."""

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
        supported = spec.supported_providers or [
            "twelvedata",
            "webhook_cache",
            "demo_historical",
        ]
        updated = spec.model_copy(
            update={
                "symbol": normalized,
                "specs_complete": has_all_sizing,
                "supported_providers": supported,
            }
        )
        self._instruments[normalized] = updated
        return updated

    def remove_custom(self, symbol: str) -> bool:
        normalized = normalize_symbol(symbol)
        if normalized in DEFAULT_INSTRUMENTS:
            return False
        return self._instruments.pop(normalized, None) is not None


def normalize_symbol(symbol: str) -> str:
    """Normalize ticker strings like 'OANDA:XAUUSD', 'XAU/USD', 'btcusd'."""
    cleaned = symbol.strip().upper()
    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[1]
    cleaned = cleaned.replace("/", "").replace("-", "")
    aliases = {
        "SPX500": "US500",
        "SP500": "US500",
        "US100": "NAS100",
        "USOIL": "WTI",
        "UKOIL": "BRENT",
    }
    return aliases.get(cleaned, cleaned)


instrument_registry = InstrumentRegistry()
