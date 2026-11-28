"""Application configuration management using environment variables."""

import os
from functools import lru_cache
from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Trading Analyzer"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    log_level: str = "INFO"
    frontend_url: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_origin_regex: str = r"^https://[a-zA-Z0-9-]+\.vercel\.app$"

    # Market Data Providers
    default_data_provider: str = "auto"
    twelvedata_api_key: str = ""
    alphavantage_api_key: str = ""
    finnhub_api_key: str = ""
    stale_data_threshold_seconds: int = Field(default=900, ge=30)
    market_data_cache_ttl_seconds: int = Field(default=30, ge=0, le=3600)

    # TradingView Webhook
    tradingview_webhook_secret: str = "change-me-to-a-strong-random-secret"
    webhook_dedup_window_seconds: int = Field(default=300, ge=5)

    # AI Explanation Provider
    ai_provider: str = "none"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # News / Session
    news_provider: str = "none"
    news_filter_enabled: bool = False
    news_blackout_minutes_before: int = 30
    news_blackout_minutes_after: int = 15

    @property
    def cors_origin_list(self) -> List[str]:
        origins: List[str] = []
        if self.frontend_url.strip():
            origins.append(self.frontend_url.strip().rstrip("/"))
        for origin in self.cors_origins.split(","):
            cleaned = origin.strip().rstrip("/")
            if not cleaned:
                continue
            # Avoid wildcard '*' in production environments
            if self.app_env.lower() == "production" and cleaned == "*":
                continue
            if cleaned not in origins:
                origins.append(cleaned)
        if not origins and self.app_env.lower() != "production":
            origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
        return origins

    def safe_public_status(self) -> dict:
        """Return non-sensitive configuration status for frontend display."""
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "default_data_provider": self.default_data_provider,
            "providers_configured": {
                "twelvedata": bool(self.twelvedata_api_key.strip()),
                "alphavantage": bool(self.alphavantage_api_key.strip()),
                "finnhub": bool(self.finnhub_api_key.strip()),
                "binance_public": True,
                "webhook_cache": True,
            },
            "ai_provider": self.ai_provider,
            "ai_key_configured": self._is_ai_configured(),
            "webhook_secret_configured": (
                bool(self.tradingview_webhook_secret.strip())
                and self.tradingview_webhook_secret != "change-me-to-a-strong-random-secret"
            ),
            "news_provider": self.news_provider,
            "news_configured": bool(self.finnhub_api_key.strip()) and self.news_provider != "none",
            "stale_data_threshold_seconds": self.stale_data_threshold_seconds,
            "market_data_cache_ttl_seconds": self.market_data_cache_ttl_seconds,
        }

    def _is_ai_configured(self) -> bool:
        provider = self.ai_provider.lower().strip()
        if provider == "openai":
            return bool(self.openai_api_key.strip())
        if provider == "gemini":
            return bool(self.gemini_api_key.strip())
        if provider == "anthropic":
            return bool(self.anthropic_api_key.strip())
        if provider == "ollama":
            return bool(self.ollama_base_url.strip())
        return False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
