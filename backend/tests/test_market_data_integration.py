"""Tests for real market-data providers, TTL caching, error handling, and connection testing."""

from datetime import datetime, timedelta, timezone
import httpx
import pytest
from fastapi.testclient import TestClient
from app.core.config import get_settings
from app.data.manager import MarketDataManager
from app.data.providers.binance_public import BinancePublicProvider
from app.data.providers.twelvedata import TwelveDataProvider, resolve_twelvedata_symbol
from app.database.connection import db_store
from app.main import app
from app.models.market import DataConnectionStatus, Timeframe


class _MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "https://api.twelvedata.com/time_series"),
                response=httpx.Response(self.status_code),
            )


def test_symbol_mapping():
    assert resolve_twelvedata_symbol("XAUUSD") == "XAU/USD"
    assert resolve_twelvedata_symbol("EURUSD") == "EUR/USD"
    assert resolve_twelvedata_symbol("GBPUSD") == "GBP/USD"
    assert resolve_twelvedata_symbol("BTCUSD") == "BTC/USD"
    assert resolve_twelvedata_symbol("OANDA:XAUUSD") == "XAU/USD"


@pytest.mark.asyncio
async def test_twelvedata_live_xauusd_missing_volume_and_error_cases(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "twelvedata_api_key", "test-key-123")
    provider = TwelveDataProvider()

    now = datetime.now(timezone.utc)
    sample_values = [
        {
            "datetime": (now - timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S"),
            "open": str(2680.0 + i * 0.2),
            "high": str(2681.5 + i * 0.2),
            "low": str(2679.5 + i * 0.2),
            "close": str(2680.8 + i * 0.2),
            # Intentionally omit volume as TwelveData does for spot XAU/USD
        }
        for i in range(40)
    ]

    class _ClientSuccess:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            assert params["symbol"] == "XAU/USD"
            assert params["interval"] == "1h"
            return _MockResponse(200, {"status": "ok", "values": sample_values})

    monkeypatch.setattr(httpx, "AsyncClient", _ClientSuccess)
    res = await provider.fetch_candles("XAUUSD", Timeframe.H1, limit=40)
    assert res.connection_status == DataConnectionStatus.LIVE
    assert len(res.raw_candles) == 40
    # Missing volume must stay None (never invented)
    assert res.raw_candles[0]["volume"] is None
    assert Timeframe.M3 in res.unavailable_timeframes

    conn_ok = await provider.test_connection("XAUUSD", Timeframe.H1)
    assert conn_ok.connected is True
    assert conn_ok.status == "CONNECTED"
    assert conn_ok.sample_price is not None

    # Unsupported 3m timeframe
    res_3m = await provider.fetch_candles("XAUUSD", Timeframe.M3)
    assert res_3m.connection_status == DataConnectionStatus.DATA_UNAVAILABLE
    assert "3m" in res_3m.error_message

    # Invalid API key (401)
    class _ClientInvalidKey(_ClientSuccess):
        async def get(self, url, params=None):
            return _MockResponse(401, {"status": "error", "code": 401, "message": "Invalid API key"})

    monkeypatch.setattr(httpx, "AsyncClient", _ClientInvalidKey)
    conn_bad = await provider.test_connection("XAUUSD", Timeframe.H1)
    assert conn_bad.connected is False
    assert conn_bad.status == "INVALID_API_KEY"

    # Rate limit (429)
    class _ClientRateLimit(_ClientSuccess):
        async def get(self, url, params=None):
            return _MockResponse(429, {"status": "error", "code": 429, "message": "Rate limit"})

    monkeypatch.setattr(httpx, "AsyncClient", _ClientRateLimit)
    conn_rl = await provider.test_connection("XAUUSD", Timeframe.H1)
    assert conn_rl.connected is False
    assert conn_rl.status == "RATE_LIMITED"

    # Network timeout
    class _ClientTimeout(_ClientSuccess):
        async def get(self, url, params=None):
            raise httpx.TimeoutException("Timed out")

    monkeypatch.setattr(httpx, "AsyncClient", _ClientTimeout)
    res_to = await provider.fetch_candles("XAUUSD", Timeframe.H1)
    assert res_to.connection_status == DataConnectionStatus.DATA_UNAVAILABLE
    assert "timed out" in res_to.error_message.lower()


@pytest.mark.asyncio
async def test_market_data_manager_ttl_cache_and_force_refresh(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "twelvedata_api_key", "test-key-cache")
    monkeypatch.setattr(settings, "market_data_cache_ttl_seconds", 60)

    mgr = MarketDataManager()
    calls = {"count": 0}
    now = datetime.now(timezone.utc)

    async def _fake_fetch(symbol, timeframe, limit=300):
        calls["count"] += 1
        from app.data.base import ProviderFetchResult

        return ProviderFetchResult(
            provider_name="twelvedata",
            connection_status=DataConnectionStatus.LIVE,
            raw_candles=[
                {
                    "timestamp": (now - timedelta(hours=i)).isoformat(),
                    "open": 2680.0,
                    "high": 2682.0,
                    "low": 2679.0,
                    "close": 2681.0,
                    "volume": None,
                }
                for i in range(35)
            ],
        )

    monkeypatch.setattr(mgr.providers["twelvedata"], "fetch_candles", _fake_fetch)

    first = await mgr.get_market_data("XAUUSD", Timeframe.H1, provider_override="twelvedata")
    assert first.cache_hit is False
    assert calls["count"] == 1

    second = await mgr.get_market_data("XAUUSD", Timeframe.H1, provider_override="twelvedata")
    assert second.cache_hit is True
    assert calls["count"] == 1

    refreshed = await mgr.get_market_data(
        "XAUUSD", Timeframe.H1, provider_override="twelvedata", force_refresh=True
    )
    assert refreshed.cache_hit is False
    assert calls["count"] == 2


def test_provider_connection_endpoint_and_stale_analysis_refusal(monkeypatch):
    db_store.reset()
    monkeypatch.setattr(get_settings(), "twelvedata_api_key", "")

    from app.core.config import Settings
    prod_cfg = Settings(
        app_env="production",
        frontend_url="https://my-app.vercel.app/",
        cors_origins="*,https://custom.example.com/",
    )
    assert prod_cfg.cors_origin_list == [
        "https://my-app.vercel.app",
        "https://custom.example.com",
    ]

    with TestClient(app) as client:
        test_res = client.post(
            "/api/market/providers/test",
            json={"provider": "twelvedata", "symbol": "XAUUSD", "timeframe": "1h"},
        )
        assert test_res.status_code == 200
        body = test_res.json()
        assert body["connected"] is False
        assert body["status"] == "API_KEY_MISSING"

        # Without live data and allow_demo=False, analysis must refuse rather than issuing fake BUY/SELL
        ana = client.post(
            "/api/analysis/run",
            json={"symbol": "XAUUSD", "timeframe": "1h", "allow_demo": False},
        )
        assert ana.status_code == 422

        # Verify CORS allows Vercel frontend origins cleanly
        cors_resp = client.options(
            "/api/health",
            headers={
                "Origin": "https://ai-trading-analyzer-ui.vercel.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert cors_resp.status_code == 200
        assert cors_resp.headers.get("access-control-allow-origin") == "https://ai-trading-analyzer-ui.vercel.app"


@pytest.mark.asyncio
async def test_binance_451_geo_fallback_to_kraken(monkeypatch):
    provider = BinancePublicProvider()

    class _ClientGeo451:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            if "binance" in url:
                return _MockResponse(451, {"msg": "Restricted location"})
            return _MockResponse(
                200,
                {
                    "error": [],
                    "result": {
                        "XXBTZUSD": [
                            [1700000000 + i * 3600, "95000", "95500", "94800", "95200", "95100", "12.5", 100]
                            for i in range(5)
                        ],
                        "last": 1700018000,
                    },
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", _ClientGeo451)
    res = await provider.fetch_candles("BTCUSD", Timeframe.H1, limit=5)
    assert res.connection_status == DataConnectionStatus.LIVE
    assert "kraken_public" in res.provider_name
    assert len(res.raw_candles) == 5
