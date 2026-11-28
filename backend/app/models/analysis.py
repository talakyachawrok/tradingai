"""Analysis, pattern, structure, liquidity, scoring, risk, and report models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.market import DataConnectionStatus, Timeframe


class BiasDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    UNCLEAR = "unclear"


class DecisionType(str, Enum):
    BUY_SETUP = "BUY SETUP"
    SELL_SETUP = "SELL SETUP"
    WAIT = "WAIT"
    NO_VALID_SETUP = "NO VALID SETUP"


class SignalStatus(str, Enum):
    SCANNING = "SCANNING"
    SETUP_FORMING = "SETUP FORMING"
    WAIT_FOR_CONFIRMATION = "WAIT FOR CONFIRMATION"
    BUY_SIGNAL = "BUY SIGNAL"
    SELL_SIGNAL = "SELL SIGNAL"
    SIGNAL_EXPIRED = "SIGNAL EXPIRED"
    TARGET_HIT = "TARGET HIT"
    STOP_LOSS_HIT = "STOP LOSS HIT"
    NO_TRADE = "NO TRADE"
    DATA_UNAVAILABLE = "DATA UNAVAILABLE"


class CertaintyLevel(str, Enum):
    DETECTED_EVENT = "detected_event"
    POSSIBLE_INTERPRETATION = "possible_interpretation"
    CONFIRMED_RULE = "confirmed_rule"


class CandlestickPattern(BaseModel):
    name: str
    classification: BiasDirection
    strength_score: float = Field(ge=0, le=100)
    candle_indices: List[int]
    timestamps: List[datetime]
    explanation: str
    confirmation_conditions: List[str]
    invalidation_conditions: List[str]
    metrics: Dict[str, float] = Field(default_factory=dict)


class SwingPoint(BaseModel):
    index: int
    timestamp: datetime
    price: float
    kind: str  # "swing_high" or "swing_low"
    label: str  # HH, HL, LH, LL, SH, SL


class StructureEvent(BaseModel):
    event_type: str  # BOS, CHoCH
    direction: BiasDirection
    index: int
    timestamp: datetime
    break_price: float
    reference_swing_price: float
    reference_swing_timestamp: datetime
    explanation: str


class MarketStructureResult(BaseModel):
    bias: BiasDirection
    regime: str  # trending_bullish, trending_bearish, range_bound, consolidation, unclear
    swing_points: List[SwingPoint] = Field(default_factory=list)
    structure_events: List[StructureEvent] = Field(default_factory=list)
    recent_bos: Optional[StructureEvent] = None
    recent_choch: Optional[StructureEvent] = None
    explanation: str


class SupportResistanceLevel(BaseModel):
    level_type: str  # support, resistance
    price: float
    zone_low: float
    zone_high: float
    touches: int
    strength: float = Field(ge=0, le=100)
    last_touched: datetime
    certainty: CertaintyLevel = CertaintyLevel.CONFIRMED_RULE
    explanation: str


class LiquidityZone(BaseModel):
    zone_type: str  # equal_highs, equal_lows, supply_zone, demand_zone, rejection_zone
    bias: BiasDirection
    price_low: float
    price_high: float
    reference_timestamps: List[datetime]
    certainty: CertaintyLevel
    explanation: str


class LiquiditySweepEvent(BaseModel):
    direction: BiasDirection  # bullish_sweep (swept lows & reclaimed), bearish_sweep (swept highs & rejected)
    swept_level: float
    sweep_extreme: float
    close_price: float
    timestamp: datetime
    index: int
    certainty: CertaintyLevel
    explanation: str


class FairValueGap(BaseModel):
    direction: BiasDirection
    gap_low: float
    gap_high: float
    created_at: datetime
    index: int
    filled: bool = False
    explanation: str


class LiquidityAnalysisResult(BaseModel):
    support_resistance: List[SupportResistanceLevel] = Field(default_factory=list)
    liquidity_zones: List[LiquidityZone] = Field(default_factory=list)
    sweep_events: List[LiquiditySweepEvent] = Field(default_factory=list)
    fair_value_gaps: List[FairValueGap] = Field(default_factory=list)
    breakout_status: str = "none"  # none, bullish_breakout, bearish_breakout, failed_bullish_breakout, failed_bearish_breakout
    pullback_retest_status: str = "none"
    summary: str


class IndicatorSnapshot(BaseModel):
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    rsi_14: Optional[float] = None
    atr_14: Optional[float] = None
    atr_pct: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    volume_current: Optional[float] = None
    volume_sma_20: Optional[float] = None
    volume_ratio: Optional[float] = None
    ema_alignment: str = "unavailable"
    rsi_condition: str = "unavailable"
    volatility_condition: str = "unavailable"
    macd_condition: str = "unavailable"
    volume_condition: str = "unavailable"
    conflicts: List[str] = Field(default_factory=list)


class IndicatorChartOverlay(BaseModel):
    timestamps: List[datetime] = Field(default_factory=list)
    ema_20: List[Optional[float]] = Field(default_factory=list)
    ema_50: List[Optional[float]] = Field(default_factory=list)
    ema_200: List[Optional[float]] = Field(default_factory=list)
    rsi_14: List[Optional[float]] = Field(default_factory=list)
    atr_14: List[Optional[float]] = Field(default_factory=list)


class MultiTimeframeEntry(BaseModel):
    timeframe: Timeframe
    role: str  # higher_timeframe, primary_timeframe, lower_timeframe
    available: bool
    trend: BiasDirection = BiasDirection.UNCLEAR
    structure: BiasDirection = BiasDirection.UNCLEAR
    ema_alignment: str = "unavailable"
    rsi_14: Optional[float] = None
    key_support: Optional[float] = None
    key_resistance: Optional[float] = None
    notes: str = ""


class MultiTimeframeResult(BaseModel):
    primary_timeframe: Timeframe
    alignment_score: float = Field(ge=0, le=100)
    overall_bias: BiasDirection
    has_conflict: bool
    conflict_reasons: List[str] = Field(default_factory=list)
    unavailable_timeframes: List[Timeframe] = Field(default_factory=list)
    timeframes: List[MultiTimeframeEntry] = Field(default_factory=list)
    summary: str


class ScoreBreakdownItem(BaseModel):
    category: str
    score: float
    max_score: float
    reason: str


class SetupScoreResult(BaseModel):
    total_score: float = Field(ge=0, le=100)
    max_score: float = 100.0
    grade_label: str  # Avoid, Weak setup, Wait for confirmation, Qualified setup, Strongly qualified setup
    breakdown: List[ScoreBreakdownItem] = Field(default_factory=list)
    direction_candidate: BiasDirection


class TradeLevels(BaseModel):
    direction: Optional[BiasDirection] = None
    entry_price: Optional[float] = None
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    entry_condition: str = ""
    requires_confirmation: bool = True
    stop_loss: Optional[float] = None
    stop_loss_explanation: str = ""
    take_profit_1: Optional[float] = None
    tp1_explanation: str = ""
    take_profit_2: Optional[float] = None
    tp2_explanation: str = ""
    take_profit_3: Optional[float] = None
    tp3_explanation: str = ""
    risk_reward_tp1: Optional[float] = None
    risk_reward_tp2: Optional[float] = None
    risk_reward_tp3: Optional[float] = None
    is_valid: bool = False
    rejection_reasons: List[str] = Field(default_factory=list)


class PositionSizeRequest(BaseModel):
    symbol: str
    account_balance: float = Field(gt=0)
    risk_percentage: float = Field(gt=0, le=100)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)


class PositionSizeResult(BaseModel):
    symbol: str
    specs_available: bool
    risk_amount: float
    stop_distance: float
    recommended_lots: Optional[float] = None
    recommended_units: Optional[float] = None
    pip_or_tick_risk: Optional[float] = None
    warning: Optional[str] = None
    details: str


class ProbabilityEstimate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_validated: bool = False
    is_experimental: bool = True
    model_available: bool = False
    status_label: str = "PROBABILITY MODEL NOT YET VALIDATED"
    model_name: Optional[str] = None
    estimated_win_probability: Optional[float] = Field(default=None, ge=0, le=1)
    raw_probability: Optional[float] = Field(default=None, ge=0, le=1)
    calibration_method: Optional[str] = None
    definition: str = (
        "Estimated calibrated probability that TP1 is reached before Stop Loss within "
        "the configured lookahead horizon under historical setup rules. This is a "
        "statistical estimate, not a guarantee of future trade performance."
    )
    explanation: str = ""
    trained_on: Optional[str] = None
    validation_metrics: Dict[str, Any] = Field(default_factory=dict)


class TradeExplanation(BaseModel):
    engine_mode: str  # RULE_BASED_EXPLANATION or LLM_ASSISTED_EXPLANATION
    pattern_explanation: str
    market_structure_explanation: str
    liquidity_explanation: str
    indicator_explanation: str
    multi_timeframe_explanation: str
    trade_rationale: str
    invalidation: str
    risk_assessment: str


class BeginnerExplanation(BaseModel):
    headline: str
    why_bullets: List[str] = Field(default_factory=list)
    what_it_means: str
    confirmations_met: List[str] = Field(default_factory=list)
    confirmations_missing: List[str] = Field(default_factory=list)
    no_trade_category: Optional[str] = None  # NO TRADE, WAIT, LOW QUALITY SETUP, DATA UNAVAILABLE


class PatternStory(BaseModel):
    detected: bool = False
    pattern_name: str = "No decisive candle pattern"
    direction: str = "neutral"
    candles_involved: List[str] = Field(default_factory=list)
    what_happened: str = ""
    why_considered: str = ""
    confirmation_found: str = ""
    what_makes_it_fail: str = ""


class SimpleTradePlan(BaseModel):
    direction: str = "NONE"
    entry_display: str = "N/A"
    stop_loss_display: str = "N/A"
    tp1_display: str = "N/A"
    tp2_display: str = "N/A"
    tp3_display: str = "N/A"
    risk_reward_display: str = "N/A"
    why_stop_loss_here: str = ""
    why_targets_selected: str = ""


class SignalTrackingState(BaseModel):
    entry_reached: bool = False
    entry_reached_at: Optional[datetime] = None
    tp1_reached: bool = False
    tp1_reached_at: Optional[datetime] = None
    tp2_reached: bool = False
    tp2_reached_at: Optional[datetime] = None
    tp3_reached: bool = False
    tp3_reached_at: Optional[datetime] = None
    sl_reached: bool = False
    sl_reached_at: Optional[datetime] = None
    invalidated: bool = False
    expired: bool = False
    ambiguous_intrabar: bool = False
    last_checked_at: Optional[datetime] = None
    last_checked_price: Optional[float] = None
    tracking_note: str = "Awaiting market price tracking."


class TradeSignalRecord(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    signal_id: str
    dedup_key: str
    analysis_id: str
    created_at: datetime
    candle_timestamp: datetime
    expires_at: datetime
    symbol: str
    timeframe: Timeframe
    provider: str
    connection_status: DataConnectionStatus
    is_demo: bool = False
    direction: str  # BUY, SELL, WAIT, NONE
    status: SignalStatus
    entry_price: Optional[float] = None
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = None
    setup_score: float = 0.0
    probability_estimate: Optional[float] = None
    probability_status: str = "PROBABILITY MODEL NOT YET VALIDATED"
    invalidation_condition: str = ""
    short_reason: str = ""
    beginner_explanation: BeginnerExplanation
    pattern_story: PatternStory
    simple_trade_plan: SimpleTradePlan
    tracking: SignalTrackingState = Field(default_factory=SignalTrackingState)
    notified: bool = False


class TradeAnalysisReport(BaseModel):
    analysis_id: str
    signal_id: Optional[str] = None
    signal_status: SignalStatus = SignalStatus.NO_TRADE
    signal_expires_at: Optional[datetime] = None
    created_at: datetime
    strategy_version: str = "1.0.0"
    symbol: str
    provider: str
    connection_status: DataConnectionStatus
    is_demo: bool = False
    timeframe: Timeframe
    current_price: float
    data_timestamp: datetime
    market_session: str
    market_trend: BiasDirection
    market_structure: MarketStructureResult
    patterns: List[CandlestickPattern] = Field(default_factory=list)
    liquidity: LiquidityAnalysisResult
    indicators: IndicatorSnapshot
    overlays: IndicatorChartOverlay
    multi_timeframe: MultiTimeframeResult
    setup_score: SetupScoreResult
    trade_levels: TradeLevels
    probability: ProbabilityEstimate
    explanation: TradeExplanation
    beginner_explanation: Optional[BeginnerExplanation] = None
    pattern_story: Optional[PatternStory] = None
    simple_trade_plan: Optional[SimpleTradePlan] = None
    final_decision: DecisionType
    decision_reason: str
    risk_warnings: List[str] = Field(default_factory=list)
    facts_summary: List[str] = Field(default_factory=list)
    calculated_findings: List[str] = Field(default_factory=list)
