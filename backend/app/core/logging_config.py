"""Structured logging setup for backend services (never logs secrets)."""

import logging
from app.core.config import get_settings


def configure_logging() -> logging.Logger:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    return logging.getLogger("ai_trading_analyzer")


logger = configure_logging()
