"""Static historical sample dataset provider (explicit DEMO_MODE only, never live)."""

import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from app.core.instruments import instrument_registry, normalize_symbol
from app.data.base import MarketDataProvider, ProviderFetchResult
from app.models.market import TIMEFRAME_SECONDS, DataConnectionStatus, ProviderCapability, Timeframe


# Fixed historical anchor so demo candles never impersonate current live market time.
DEMO_ANCHOR_END = datetime(2026, 2, 15, 16, 0, 0, tzinfo=timezone.utc)

BASE_SPECS: Dict[str, Dict[str, float]] = {
    "XAUUSD": {"base": 2680.0, "step": 2.4, "vol": 1250.0, "decimals": 2},
    "EURUSD": {"base": 1.0450, "step": 0.0008, "vol": 4200.0, "decimals": 5},
    "GBPUSD": {"base": 1.2580, "step": 0.0010, "vol": 3600.0, "decimals": 5},
    "BTCUSD": {"base": 96200.0, "step": 210.0, "vol": 850.0, "decimals": 2},
}


class DemoHistoricalProvider(MarketDataProvider):
    """
    Reproducible offline historical dataset for testing analysis, charting,
    backtesting, and paper trading when live API credentials are absent.
    Always marked is_demo=True and DataConnectionStatus.DEMO_MODE.
    """

    name = "demo_historical"

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            name=self.name,
            configured=True,
            supports_live=False,
            supports_historical=True,
            supported_timeframes=list(Timeframe),
            supported_symbols=[i.symbol for i in instrument_registry.list_instruments()],
            notes="Static historical sample dataset ending 2026-02-15 UTC. Never represents live prices.",
        )

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 300
    ) -> ProviderFetchResult:
        norm = normalize_symbol(symbol)
        inst = instrument_registry.get(norm)
        default_base = (
            1.10 if inst and inst.asset_class == "forex" else (250.0 if inst and inst.asset_class == "stocks" else 100.0)
        )
        default_step = 0.0008 if inst and inst.asset_class == "forex" else (1.5 if default_base > 100 else 0.5)
        spec = BASE_SPECS.get(
            norm,
            {
                "base": default_base,
                "step": default_step,
                "vol": 1000.0,
                "decimals": float(inst.decimals if inst else 2),
            },
        )
        candles = self._build_historical_series(
            symbol=norm,
            timeframe=timeframe,
            count=min(max(limit, 80), 600),
            base_price=spec["base"],
            step_scale=spec["step"],
            base_vol=spec["vol"],
            decimals=int(spec["decimals"]),
        )
        return ProviderFetchResult(
            provider_name=self.name,
            connection_status=DataConnectionStatus.DEMO_MODE,
            raw_candles=candles,
            is_demo=True,
        )

    def _build_historical_series(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
        base_price: float,
        step_scale: float,
        base_vol: float,
        decimals: int,
    ) -> List[Dict]:
        tf_sec = TIMEFRAME_SECONDS[timeframe]
        scale = step_scale * math.sqrt(tf_sec / 3600.0)
        seed_offset = sum(ord(ch) for ch in symbol) % 17
        start_ts = DEMO_ANCHOR_END - timedelta(seconds=tf_sec * count)

        candles: List[Dict] = []
        price = base_price

        for i in range(count):
            ts = start_ts + timedelta(seconds=tf_sec * i)
            # Multi-wave structure: uptrend legs, pullbacks, consolidation, sweep & reversal
            macro = math.sin((i + seed_offset) / 28.0) * 1.15
            meso = math.cos((i + seed_offset) / 9.5) * 0.75
            micro = math.sin((i * 1.7 + seed_offset) / 3.2) * 0.45
            drift = 0.08 if i < count * 0.65 else -0.04
            delta = (macro * 0.35 + meso * 0.45 + micro * 0.3 + drift) * scale

            open_p = price
            close_p = max(open_p * 0.2, open_p + delta)

            # Inject clear structural & candlestick setups near the tail for inspection
            if i == count - 6:
                close_p = open_p - scale * 1.15
            elif i == count - 5:
                # Sweep / hammer rejection candle
                close_p = open_p + scale * 0.35
                wick_down = scale * 2.1
                high_p = max(open_p, close_p) + scale * 0.22
                low_p = min(open_p, close_p) - wick_down
            elif i == count - 2:
                close_p = open_p - scale * 0.65
            elif i == count - 1:
                # Bullish engulfing confirmation candle
                prev_open = candles[-1]["open"]
                prev_close = candles[-1]["close"]
                open_p = prev_close - scale * 0.08
                close_p = prev_open + scale * 0.75

            if i != count - 5:
                upper_w = abs(math.sin(i * 0.91 + seed_offset)) * scale * 0.65 + scale * 0.12
                lower_w = abs(math.cos(i * 1.13 + seed_offset)) * scale * 0.65 + scale * 0.12
                high_p = max(open_p, close_p) + upper_w
                low_p = max(0.00001, min(open_p, close_p) - lower_w)

            vol = round(base_vol * (0.7 + abs(math.sin(i * 0.5)) * 1.1), 2)
            candles.append(
                {
                    "timestamp": ts.isoformat(),
                    "open": round(open_p, decimals),
                    "high": round(high_p, decimals),
                    "low": round(max(0.00001, low_p), decimals),
                    "close": round(close_p, decimals),
                    "volume": vol,
                }
            )
            price = close_p

        return candles
