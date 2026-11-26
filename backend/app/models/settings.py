"""Configurable analysis, indicator, pattern, scoring, and risk settings models."""

from typing import Dict, List
from pydantic import BaseModel, Field
from app.models.market import Timeframe


class IndicatorSettings(BaseModel):
    ema_fast: int = Field(default=20, ge=2, le=200)
    ema_medium: int = Field(default=50, ge=5, le=300)
    ema_slow: int = Field(default=200, ge=20, le=500)
    rsi_period: int = Field(default=14, ge=2, le=50)
    rsi_overbought: float = Field(default=70.0, ge=50, le=95)
    rsi_oversold: float = Field(default=30.0, ge=5, le=50)
    atr_period: int = Field(default=14, ge=2, le=50)
    macd_fast: int = Field(default=12, ge=2, le=50)
    macd_slow: int = Field(default=26, ge=5, le=100)
    macd_signal: int = Field(default=9, ge=2, le=50)
    volume_sma_period: int = Field(default=20, ge=5, le=100)


class PatternSettings(BaseModel):
    doji_max_body_ratio: float = Field(default=0.12, ge=0.01, le=0.35)
    pin_bar_min_wick_to_body: float = Field(default=2.0, ge=1.2, le=6.0)
    pin_bar_max_opposite_wick_ratio: float = Field(default=0.25, ge=0.05, le=0.5)
    momentum_min_body_ratio: float = Field(default=0.65, ge=0.4, le=0.95)
    momentum_min_atr_multiple: float = Field(default=1.2, ge=0.5, le=4.0)
    long_wick_min_ratio: float = Field(default=0.55, ge=0.3, le=0.9)
    consecutive_count: int = Field(default=3, ge=2, le=6)


class StructureSettings(BaseModel):
    swing_left_bars: int = Field(default=3, ge=2, le=10)
    swing_right_bars: int = Field(default=3, ge=2, le=10)
    min_swing_atr_distance: float = Field(default=0.35, ge=0.0, le=3.0)
    equal_level_tolerance_atr: float = Field(default=0.25, ge=0.05, le=1.5)
    sr_cluster_tolerance_atr: float = Field(default=0.4, ge=0.05, le=2.0)


class ScoringWeights(BaseModel):
    trend_alignment: float = Field(default=18.0, ge=0, le=50)
    market_structure: float = Field(default=18.0, ge=0, le=50)
    candlestick_pattern: float = Field(default=14.0, ge=0, le=50)
    liquidity: float = Field(default=12.0, ge=0, le=50)
    support_resistance: float = Field(default=10.0, ge=0, le=50)
    indicator_confirmation: float = Field(default=12.0, ge=0, le=50)
    multi_timeframe_alignment: float = Field(default=10.0, ge=0, le=50)
    volatility_suitability: float = Field(default=3.0, ge=0, le=20)
    risk_reward_quality: float = Field(default=3.0, ge=0, le=20)

    def normalized_weights(self) -> Dict[str, float]:
        raw = self.model_dump()
        total = sum(raw.values())
        if total <= 0:
            return {k: 100.0 / len(raw) for k in raw}
        return {k: (v / total) * 100.0 for k, v in raw.items()}


class ScoringThresholds(BaseModel):
    avoid_max: float = Field(default=49.9, ge=0, le=100)
    weak_max: float = Field(default=64.9, ge=0, le=100)
    wait_max: float = Field(default=74.9, ge=0, le=100)
    qualified_max: float = Field(default=84.9, ge=0, le=100)


class RiskSettings(BaseModel):
    max_risk_per_trade_pct: float = Field(default=1.0, ge=0.1, le=10.0)
    max_daily_loss_pct: float = Field(default=3.0, ge=0.5, le=25.0)
    max_daily_trades: int = Field(default=5, ge=1, le=50)
    max_consecutive_losses: int = Field(default=3, ge=1, le=20)
    min_risk_reward: float = Field(default=1.5, ge=0.5, le=10.0)
    max_open_paper_trades: int = Field(default=3, ge=1, le=25)
    min_setup_score: float = Field(default=75.0, ge=0, le=100)
    require_candle_close_confirmation: bool = True
    require_htf_alignment: bool = True
    atr_sl_buffer_multiple: float = Field(default=0.35, ge=0.0, le=3.0)
    min_atr_pct: float = Field(default=0.01, ge=0.0, le=5.0)
    max_atr_pct: float = Field(default=6.0, ge=0.1, le=25.0)


class TimeframeSettings(BaseModel):
    primary_timeframe: Timeframe = Timeframe.H1
    confirmation_timeframes: List[Timeframe] = Field(
        default_factory=lambda: [Timeframe.H4, Timeframe.M15]
    )


class AppUserSettings(BaseModel):
    theme: str = "dark"
    data_provider: str = "auto"
    indicators: IndicatorSettings = Field(default_factory=IndicatorSettings)
    patterns: PatternSettings = Field(default_factory=PatternSettings)
    structure: StructureSettings = Field(default_factory=StructureSettings)
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    scoring_thresholds: ScoringThresholds = Field(default_factory=ScoringThresholds)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    timeframes: TimeframeSettings = Field(default_factory=TimeframeSettings)
    news_filter_enabled: bool = False
    notifications_enabled: bool = True
