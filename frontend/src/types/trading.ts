export type Timeframe = '1m' | '3m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d'

export type DataConnectionStatus =
  | 'LIVE'
  | 'DELAYED'
  | 'DEMO_MODE'
  | 'WEBHOOK_CACHE'
  | 'DATA_UNAVAILABLE'

export type DecisionType = 'BUY SETUP' | 'SELL SETUP' | 'WAIT' | 'NO VALID SETUP'

export type SignalStatus =
  | 'SCANNING'
  | 'SETUP FORMING'
  | 'WAIT FOR CONFIRMATION'
  | 'BUY SIGNAL'
  | 'SELL SIGNAL'
  | 'SIGNAL EXPIRED'
  | 'TARGET HIT'
  | 'STOP LOSS HIT'
  | 'NO TRADE'
  | 'DATA UNAVAILABLE'

export interface InstrumentSpec {
  symbol: string
  display_name: string
  asset_class: string
  base_currency: string
  quote_currency: string
  decimals: number
  pip_size?: number | null
  contract_size?: number | null
  tick_size?: number | null
  tick_value_per_lot?: number | null
  min_lot: number
  lot_step: number
  typical_spread?: number | null
  provider_symbols?: Record<string, string>
  supported_providers?: string[]
  specs_complete: boolean
  is_custom: boolean
}

export type MarketCategory =
  | 'all'
  | 'favorites'
  | 'forex'
  | 'crypto'
  | 'commodities'
  | 'indices'
  | 'stocks'

export interface ChartOverlaySettings {
  showEma20: boolean
  showEma50: boolean
  showEma200: boolean
  showLevels: boolean
  showTradeLines: boolean
}

export interface ProviderCapability {
  name: string
  configured: boolean
  supports_live: boolean
  supports_historical: boolean
  supported_timeframes: Timeframe[]
  supported_symbols: string[]
  notes: string
}

export interface OHLCVCandle {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume?: number | null
}

export interface DataIntegrityReport {
  raw_count: number
  valid_count: number
  duplicates_removed: number
  invalid_candles_dropped: number
  time_gaps_detected: number
  is_stale: boolean
  stale_seconds?: number | null
  has_volume: boolean
  warnings: string[]
}

export interface MarketOverview {
  symbol: string
  display_name: string
  timeframe: Timeframe
  current_price?: number | null
  price_change?: number | null
  price_change_pct?: number | null
  market_session: string
  session_status: string
  data_source: string
  connection_status: DataConnectionStatus
  last_data_update?: string | null
  market_status: string
  volatility_condition: string
  is_demo: boolean
  status_message: string
}

export interface IndicatorSnapshot {
  ema_20?: number | null
  ema_50?: number | null
  ema_200?: number | null
  rsi_14?: number | null
  atr_14?: number | null
  atr_pct?: number | null
  macd_line?: number | null
  macd_signal?: number | null
  macd_histogram?: number | null
  volume_current?: number | null
  volume_sma_20?: number | null
  volume_ratio?: number | null
  ema_alignment: string
  rsi_condition: string
  volatility_condition: string
  macd_condition: string
  volume_condition: string
  conflicts: string[]
}

export interface IndicatorChartOverlay {
  timestamps: string[]
  ema_20: Array<number | null>
  ema_50: Array<number | null>
  ema_200: Array<number | null>
  rsi_14: Array<number | null>
  atr_14: Array<number | null>
}

export interface MarketDataResponse {
  overview: MarketOverview
  candles: OHLCVCandle[]
  integrity: DataIntegrityReport
  unavailable_timeframes: Timeframe[]
  indicators?: IndicatorSnapshot
  overlays?: IndicatorChartOverlay
  cache_hit?: boolean
}

export interface ProviderConnectionTestResult {
  provider_name: string
  connected: boolean
  status: string
  message: string
  tested_symbol: string
  tested_timeframe: string
  latency_ms?: number | null
  sample_price?: number | null
  sample_timestamp?: string | null
  requires_api_key: boolean
  subscription_notes: string
}

export interface CandlestickPattern {
  name: string
  classification: 'bullish' | 'bearish' | 'neutral' | 'unclear'
  strength_score: number
  candle_indices: number[]
  timestamps: string[]
  explanation: string
  confirmation_conditions: string[]
  invalidation_conditions: string[]
  metrics: Record<string, number>
}

export interface SwingPoint {
  index: number
  timestamp: string
  price: number
  kind: 'swing_high' | 'swing_low'
  label: string
}

export interface StructureEvent {
  event_type: 'BOS' | 'CHoCH'
  direction: 'bullish' | 'bearish'
  index: number
  timestamp: string
  break_price: number
  reference_swing_price: number
  reference_swing_timestamp: string
  explanation: string
}

export interface MarketStructureResult {
  bias: 'bullish' | 'bearish' | 'neutral' | 'unclear'
  regime: string
  swing_points: SwingPoint[]
  structure_events: StructureEvent[]
  recent_bos?: StructureEvent | null
  recent_choch?: StructureEvent | null
  explanation: string
}

export interface SupportResistanceLevel {
  level_type: 'support' | 'resistance'
  price: number
  zone_low: number
  zone_high: number
  touches: number
  strength: number
  last_touched: string
  certainty: string
  explanation: string
}

export interface LiquidityZone {
  zone_type: string
  bias: string
  price_low: number
  price_high: number
  reference_timestamps: string[]
  certainty: string
  explanation: string
}

export interface LiquiditySweepEvent {
  direction: string
  swept_level: number
  sweep_extreme: number
  close_price: number
  timestamp: string
  index: number
  certainty: string
  explanation: string
}

export interface FairValueGap {
  direction: string
  gap_low: number
  gap_high: number
  created_at: string
  index: number
  filled: boolean
  explanation: string
}

export interface LiquidityAnalysisResult {
  support_resistance: SupportResistanceLevel[]
  liquidity_zones: LiquidityZone[]
  sweep_events: LiquiditySweepEvent[]
  fair_value_gaps: FairValueGap[]
  breakout_status: string
  pullback_retest_status: string
  summary: string
}

export interface MultiTimeframeEntry {
  timeframe: Timeframe
  role: string
  available: boolean
  trend: string
  structure: string
  ema_alignment: string
  rsi_14?: number | null
  key_support?: number | null
  key_resistance?: number | null
  notes: string
}

export interface MultiTimeframeResult {
  primary_timeframe: Timeframe
  alignment_score: number
  overall_bias: string
  has_conflict: boolean
  conflict_reasons: string[]
  unavailable_timeframes: Timeframe[]
  timeframes: MultiTimeframeEntry[]
  summary: string
}

export interface ScoreBreakdownItem {
  category: string
  score: number
  max_score: number
  reason: string
}

export interface SetupScoreResult {
  total_score: number
  max_score: number
  grade_label: string
  breakdown: ScoreBreakdownItem[]
  direction_candidate: string
}

export interface TradeLevels {
  direction?: string | null
  entry_price?: number | null
  entry_zone_low?: number | null
  entry_zone_high?: number | null
  entry_condition: string
  requires_confirmation: boolean
  stop_loss?: number | null
  stop_loss_explanation: string
  take_profit_1?: number | null
  tp1_explanation: string
  take_profit_2?: number | null
  tp2_explanation: string
  take_profit_3?: number | null
  tp3_explanation: string
  risk_reward_tp1?: number | null
  risk_reward_tp2?: number | null
  risk_reward_tp3?: number | null
  is_valid: boolean
  rejection_reasons: string[]
}

export interface ProbabilityEstimate {
  model_validated: boolean
  is_experimental?: boolean
  model_available?: boolean
  status_label: string
  model_name?: string | null
  estimated_win_probability?: number | null
  raw_probability?: number | null
  calibration_method?: string | null
  definition: string
  explanation?: string
  trained_on?: string | null
  validation_metrics: Record<string, unknown>
}

export interface TradeExplanation {
  engine_mode: string
  pattern_explanation: string
  market_structure_explanation: string
  liquidity_explanation: string
  indicator_explanation: string
  multi_timeframe_explanation: string
  trade_rationale: string
  invalidation: string
  risk_assessment: string
}

export interface BeginnerExplanation {
  headline: string
  why_bullets: string[]
  what_it_means: string
  confirmations_met: string[]
  confirmations_missing: string[]
  no_trade_category?: string | null
}

export interface PatternStory {
  detected: boolean
  pattern_name: string
  direction: string
  candles_involved: string[]
  what_happened: string
  why_considered: string
  confirmation_found: string
  what_makes_it_fail: string
}

export interface SimpleTradePlan {
  direction: string
  entry_display: string
  stop_loss_display: string
  tp1_display: string
  tp2_display: string
  tp3_display: string
  risk_reward_display: string
  why_stop_loss_here: string
  why_targets_selected: string
}

export interface SignalTrackingState {
  entry_reached: boolean
  entry_reached_at?: string | null
  tp1_reached: boolean
  tp1_reached_at?: string | null
  tp2_reached: boolean
  tp2_reached_at?: string | null
  tp3_reached: boolean
  tp3_reached_at?: string | null
  sl_reached: boolean
  sl_reached_at?: string | null
  invalidated: boolean
  expired: boolean
  ambiguous_intrabar: boolean
  last_checked_at?: string | null
  last_checked_price?: number | null
  tracking_note: string
}

export interface TradeSignalRecord {
  signal_id: string
  dedup_key: string
  analysis_id: string
  created_at: string
  candle_timestamp: string
  expires_at: string
  symbol: string
  timeframe: Timeframe
  provider: string
  connection_status: DataConnectionStatus
  is_demo: boolean
  direction: 'BUY' | 'SELL' | 'WAIT' | 'NONE'
  status: SignalStatus
  entry_price?: number | null
  entry_zone_low?: number | null
  entry_zone_high?: number | null
  stop_loss?: number | null
  take_profit_1?: number | null
  take_profit_2?: number | null
  take_profit_3?: number | null
  risk_reward?: number | null
  setup_score: number
  probability_estimate?: number | null
  probability_status: string
  invalidation_condition: string
  short_reason: string
  beginner_explanation: BeginnerExplanation
  pattern_story: PatternStory
  simple_trade_plan: SimpleTradePlan
  tracking: SignalTrackingState
  notified: boolean
}

export interface TradeAnalysisReport {
  analysis_id: string
  signal_id?: string | null
  signal_status: SignalStatus
  signal_expires_at?: string | null
  created_at: string
  strategy_version: string
  symbol: string
  provider: string
  connection_status: DataConnectionStatus
  is_demo: boolean
  timeframe: Timeframe
  current_price: number
  data_timestamp: string
  market_session: string
  market_trend: string
  market_structure: MarketStructureResult
  patterns: CandlestickPattern[]
  liquidity: LiquidityAnalysisResult
  indicators: IndicatorSnapshot
  overlays: IndicatorChartOverlay
  multi_timeframe: MultiTimeframeResult
  setup_score: SetupScoreResult
  trade_levels: TradeLevels
  probability: ProbabilityEstimate
  explanation: TradeExplanation
  beginner_explanation?: BeginnerExplanation | null
  pattern_story?: PatternStory | null
  simple_trade_plan?: SimpleTradePlan | null
  final_decision: DecisionType
  decision_reason: string
  risk_warnings: string[]
  facts_summary: string[]
  calculated_findings: string[]
}

export interface JournalEntry {
  id: string
  created_at: string
  symbol: string
  timeframe: Timeframe
  provider: string
  connection_status: DataConnectionStatus
  is_demo: boolean
  data_timestamp: string
  current_price: number
  patterns: string[]
  market_trend: string
  setup_score: number
  decision: DecisionType
  decision_reason: string
  entry_price?: number | null
  stop_loss?: number | null
  take_profit_1?: number | null
  take_profit_2?: number | null
  take_profit_3?: number | null
  risk_reward?: number | null
  probability_estimate?: number | null
  probability_status: string
  strategy_version: string
  outcome: string
  notes: string
  ai_explanation_summary: string
}

export interface BacktestResult {
  backtest_id: string
  created_at: string
  symbol: string
  timeframe: Timeframe
  data_source: string
  is_demo: boolean
  candles_evaluated: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate_pct: number
  profit_factor?: number | null
  average_rr: number
  net_return_amount: number
  net_return_pct: number
  max_drawdown_pct: number
  average_win: number
  average_loss: number
  expectancy_r: number
  expectancy_amount: number
  final_balance: number
  equity_curve: Array<{ timestamp: string; balance: number; drawdown_pct: number }>
  by_pattern: Array<{ key: string; trades: number; wins: number; losses: number; win_rate_pct: number; net_pnl: number; avg_r: number }>
  by_regime: Array<{ key: string; trades: number; wins: number; losses: number; win_rate_pct: number; net_pnl: number; avg_r: number }>
  by_timeframe: Array<{ key: string; trades: number; wins: number; losses: number; win_rate_pct: number; net_pnl: number; avg_r: number }>
  by_instrument: Array<{ key: string; trades: number; wins: number; losses: number; win_rate_pct: number; net_pnl: number; avg_r: number }>
  trades: Array<{
    trade_number: number
    direction: string
    entry_time: string
    exit_time: string
    entry_price: number
    stop_loss: number
    take_profit: number
    exit_price: number
    exit_reason: string
    pattern: string
    regime: string
    setup_score: number
    risk_reward_planned: number
    r_multiple: number
    pnl_amount: number
    pnl_pct: number
    balance_after: number
    intrabar_conflict_assumed_sl: boolean
  }>
  overfitting_warnings: string[]
  methodology_notes: string[]
}

export interface PaperTradePosition {
  trade_id: string
  symbol: string
  direction: string
  status: 'OPEN' | 'CLOSED_TP' | 'CLOSED_SL' | 'CLOSED_MANUAL'
  opened_at: string
  closed_at?: string | null
  entry_price: number
  current_price: number
  stop_loss: number
  take_profit: number
  exit_price?: number | null
  quantity_units: number
  lots?: number | null
  risk_amount: number
  risk_percentage: number
  unrealized_pnl: number
  realized_pnl: number
  r_multiple?: number | null
  is_simulated_notice: string
  is_demo_data: boolean
  notes: string
}

export interface PaperAccountSummary {
  initial_balance: number
  balance: number
  equity: number
  unrealized_pnl: number
  realized_pnl: number
  daily_realized_pnl: number
  daily_loss_pct: number
  daily_trades_count: number
  consecutive_losses: number
  open_positions_count: number
  total_closed_trades: number
  winning_trades: number
  losing_trades: number
  win_rate_pct: number
  risk_limit_breached: boolean
  risk_limit_reasons: string[]
  simulation_disclaimer: string
}

export interface NotificationItem {
  id: string
  created_at: string
  category: string
  severity: 'info' | 'success' | 'warning' | 'error'
  title: string
  message: string
  read: boolean
}

export interface WebhookLogRecord {
  alert_id: string
  received_at: string
  dedup_hash: string
  symbol: string
  timeframe: string
  event: string
  status: string
  message: string
  analysis_id?: string | null
}
