"""Trade journal, backtesting, paper trading, webhook, and notification models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.analysis import DecisionType
from app.models.market import DataConnectionStatus, Timeframe


class JournalEntry(BaseModel):
    id: str
    created_at: datetime
    symbol: str
    timeframe: Timeframe
    provider: str
    connection_status: DataConnectionStatus
    is_demo: bool = False
    data_timestamp: datetime
    current_price: float
    patterns: List[str] = Field(default_factory=list)
    market_trend: str
    setup_score: float
    decision: DecisionType
    decision_reason: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = None
    probability_estimate: Optional[float] = None
    probability_status: str = "PROBABILITY MODEL NOT YET VALIDATED"
    strategy_version: str = "1.0.0"
    outcome: str = "pending"  # pending, win, loss, breakeven, rejected, expired
    notes: str = ""
    ai_explanation_summary: str = ""
    snapshot: Dict[str, Any] = Field(default_factory=dict)


class BacktestRequest(BaseModel):
    symbol: str
    timeframe: Timeframe = Timeframe.H1
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    initial_balance: float = Field(default=10000.0, gt=0)
    risk_per_trade_pct: float = Field(default=1.0, gt=0, le=10)
    min_setup_score: float = Field(default=65.0, ge=0, le=100)
    min_risk_reward: float = Field(default=1.5, ge=0.5, le=10)
    sl_methodology: str = "structure_atr"  # structure_atr, atr_only
    tp_methodology: str = "rr_and_structure"  # rr_and_structure, fixed_rr
    fixed_tp_rr: float = Field(default=2.0, ge=1.0, le=10.0)
    spread_bps: float = Field(default=1.5, ge=0, le=100)
    slippage_bps: float = Field(default=1.0, ge=0, le=100)
    commission_bps: float = Field(default=0.5, ge=0, le=100)
    use_demo_if_unavailable: bool = False


class BacktestTradeRecord(BaseModel):
    trade_number: int
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    exit_reason: str  # stop_loss, take_profit, end_of_data
    pattern: str
    regime: str
    setup_score: float
    risk_reward_planned: float
    r_multiple: float
    pnl_amount: float
    pnl_pct: float
    balance_after: float
    intrabar_conflict_assumed_sl: bool = False


class BacktestBreakdownItem(BaseModel):
    key: str
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    net_pnl: float
    avg_r: float


class BacktestResult(BaseModel):
    backtest_id: str
    created_at: datetime
    symbol: str
    timeframe: Timeframe
    data_source: str
    is_demo: bool
    candles_evaluated: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: Optional[float] = None
    average_rr: float
    net_return_amount: float
    net_return_pct: float
    max_drawdown_pct: float
    average_win: float
    average_loss: float
    expectancy_r: float
    expectancy_amount: float
    final_balance: float
    equity_curve: List[Dict[str, Any]] = Field(default_factory=list)
    by_pattern: List[BacktestBreakdownItem] = Field(default_factory=list)
    by_regime: List[BacktestBreakdownItem] = Field(default_factory=list)
    by_timeframe: List[BacktestBreakdownItem] = Field(default_factory=list)
    by_instrument: List[BacktestBreakdownItem] = Field(default_factory=list)
    trades: List[BacktestTradeRecord] = Field(default_factory=list)
    overfitting_warnings: List[str] = Field(default_factory=list)
    methodology_notes: List[str] = Field(default_factory=list)


class PaperTradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED_TP = "CLOSED_TP"
    CLOSED_SL = "CLOSED_SL"
    CLOSED_MANUAL = "CLOSED_MANUAL"


class PaperTradeOrderRequest(BaseModel):
    symbol: str
    direction: str  # BUY or SELL
    entry_price: Optional[float] = Field(default=None, gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    risk_percentage: float = Field(default=1.0, gt=0, le=10)
    analysis_id: Optional[str] = None
    setup_score: Optional[float] = None
    notes: str = ""
    is_demo_data: bool = False


class PaperTradePosition(BaseModel):
    trade_id: str
    symbol: str
    direction: str
    status: PaperTradeStatus
    opened_at: datetime
    closed_at: Optional[datetime] = None
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    exit_price: Optional[float] = None
    quantity_units: float
    lots: Optional[float] = None
    risk_amount: float
    risk_percentage: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    r_multiple: Optional[float] = None
    analysis_id: Optional[str] = None
    setup_score: Optional[float] = None
    is_simulated_notice: str = "PAPER TRADING ONLY — NO REAL MONEY"
    is_demo_data: bool = False
    notes: str = ""


class PaperAccountSummary(BaseModel):
    initial_balance: float
    balance: float
    equity: float
    unrealized_pnl: float
    realized_pnl: float
    daily_realized_pnl: float
    daily_loss_pct: float
    daily_trades_count: int
    consecutive_losses: int
    open_positions_count: int
    total_closed_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    risk_limit_breached: bool
    risk_limit_reasons: List[str] = Field(default_factory=list)
    simulation_disclaimer: str = "SIMULATED PAPER TRADING ACCOUNT — NOT REAL MONEY"


class TradingViewAlertPayload(BaseModel):
    symbol: str
    timeframe: str = "1h"
    price: Optional[float] = None
    close: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None
    timestamp: Optional[str] = None
    exchange: Optional[str] = None
    source: str = "TradingView"
    event: str = "analysis_trigger"
    pattern: Optional[str] = None
    indicators: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    secret: Optional[str] = None


class WebhookLogRecord(BaseModel):
    alert_id: str
    received_at: datetime
    dedup_hash: str
    symbol: str
    timeframe: str
    event: str
    status: str  # queued, processed, duplicate_ignored, rejected_invalid, rejected_auth
    message: str
    analysis_id: Optional[str] = None


class NotificationItem(BaseModel):
    id: str
    created_at: datetime
    category: str  # webhook, pattern, setup, risk, paper_trading, data_status
    severity: str  # info, success, warning, error
    title: str
    message: str
    read: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
