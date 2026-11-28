import React, { useState } from 'react'
import {
  AlertTriangle,
  CandlestickChart,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  HelpCircle,
  Loader2,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
  XCircle,
} from 'lucide-react'
import type { SignalStatus, TradeAnalysisReport } from '../types/trading'

interface Props {
  report: TradeAnalysisReport | null
  scanning: boolean
  dataUnavailable: boolean
  symbol: string
  timeframe: string
  decimals?: number
  onSendToPaper?: (report: TradeAnalysisReport) => void
  paperSubmitting?: boolean
}

export const AITradeSignalCard: React.FC<Props> = ({
  report,
  scanning,
  dataUnavailable,
  symbol,
  timeframe,
  decimals = 5,
  onSendToPaper,
  paperSubmitting,
}) => {
  const [showAdvanced, setShowAdvanced] = useState(false)

  const status: SignalStatus = scanning
    ? 'SCANNING'
    : !report
    ? dataUnavailable
      ? 'DATA UNAVAILABLE'
      : 'NO TRADE'
    : report.signal_status

  const isBuy = status === 'BUY SIGNAL'
  const isSell = status === 'SELL SIGNAL'
  const isWait = status === 'WAIT FOR CONFIRMATION' || status === 'SETUP FORMING'

  const containerStyle = isBuy
    ? 'border-emerald-500/50 bg-emerald-500/5 signal-card-glow'
    : isSell
    ? 'border-rose-500/50 bg-rose-500/5'
    : isWait
    ? 'border-amber-500/50 bg-amber-500/5'
    : 'border-terminal-border bg-terminal-panel'

  const pillStyle = isBuy
    ? 'bg-emerald-600 text-white'
    : isSell
    ? 'bg-rose-600 text-white'
    : isWait
    ? 'bg-amber-500 text-slate-950'
    : status === 'SCANNING'
    ? 'bg-sky-600 text-white'
    : 'bg-slate-600 text-white'

  const StatusIcon = isBuy
    ? TrendingUp
    : isSell
    ? TrendingDown
    : isWait
    ? Clock
    : status === 'SCANNING'
    ? Loader2
    : XCircle

  const fmt = (v?: number | null) => (v !== null && v !== undefined ? v.toFixed(decimals) : 'N/A')
  const beginner = report?.beginner_explanation
  const story = report?.pattern_story
  const plan = report?.simple_trade_plan

  return (
    <section
      aria-label="AI Trade Signal"
      className={`rounded-2xl border-2 p-5 space-y-5 transition-all ${containerStyle}`}
    >
      {/* Header Row */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-terminal-border/70 pb-4">
        <div className="space-y-1.5">
          <div className="text-[11px] font-bold uppercase tracking-widest text-terminal-muted">
            AI TRADE SIGNAL
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <span className={`inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-extrabold tracking-wide ${pillStyle}`}>
              <StatusIcon className={`w-4 h-4 ${status === 'SCANNING' ? 'animate-spin' : ''}`} />
              {status}
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-terminal-panel border border-terminal-border text-xs font-bold font-mono">
              {report?.symbol || symbol} · {(report?.timeframe || timeframe).toUpperCase()}
            </span>
            {report?.is_demo && (
              <span className="px-2.5 py-1 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs font-semibold">
                DEMO HISTORICAL DATA
              </span>
            )}
            {report?.created_at && (
              <span className="text-xs text-terminal-muted font-mono">
                {new Date(report.created_at).toISOString().slice(0, 16).replace('T', ' ')} UTC
              </span>
            )}
          </div>
          {beginner?.headline && (
            <h2 className="text-lg font-bold tracking-tight pt-1">{beginner.headline}</h2>
          )}
        </div>

        {/* Score & Probability Summary */}
        {report && (
          <div className="flex flex-wrap items-center gap-4 shrink-0">
            <div className="px-3.5 py-2 rounded-xl bg-terminal-panel border border-terminal-border text-right">
              <div className="text-[10px] uppercase tracking-wider text-terminal-muted">Setup Score</div>
              <div className="text-xl font-extrabold tabular-nums">
                {report.setup_score.total_score}
                <span className="text-xs font-normal text-terminal-muted">/100</span>
              </div>
              <div className="text-[11px] text-sky-400 font-medium">{report.setup_score.grade_label}</div>
            </div>

            <div
              className="px-3.5 py-2 rounded-xl bg-terminal-panel border border-terminal-border text-right"
              title={report.probability.explanation || report.probability.definition}
            >
              <div className="text-[10px] uppercase tracking-wider text-terminal-muted">
                ML TP1 Probability
                {report.probability.is_experimental && report.probability.estimated_win_probability != null && (
                  <span className="ml-1 text-amber-400">· EXP</span>
                )}
              </div>
              {report.probability.model_validated &&
              report.probability.estimated_win_probability != null ? (
                <div>
                  <div
                    className={`text-xl font-extrabold tabular-nums ${
                      report.probability.is_experimental ? 'text-amber-400' : 'text-emerald-400'
                    }`}
                  >
                    {(report.probability.estimated_win_probability * 100).toFixed(1)}%
                  </div>
                  <div className="text-[10px] text-terminal-muted max-w-[160px] truncate">
                    {report.probability.calibration_method ? 'Calibrated · Stat. only' : 'Stat. estimate only'}
                  </div>
                </div>
              ) : (
                <div className="text-[11px] font-semibold text-amber-400 max-w-[160px]">
                  {report.probability.status_label || 'ML UNAVAILABLE'}
                </div>
              )}
            </div>

            {(isBuy || isSell) && report.trade_levels.is_valid && onSendToPaper && (
              <button
                onClick={() => onSendToPaper(report)}
                disabled={paperSubmitting}
                className="px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-bold transition shadow-sm"
              >
                {paperSubmitting ? 'Sending...' : 'Send to Paper Trading'}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Scanning or Pre-Analysis Empty State */}
      {scanning ? (
        <div className="py-6 text-center text-sm text-terminal-muted">
          Scanning candlesticks, trend, support/resistance, and chart agreement...
        </div>
      ) : !report ? (
        <div className="rounded-xl border border-terminal-border bg-terminal-elevated/40 p-4 text-xs space-y-1.5">
          <div className="font-bold text-sm">
            {dataUnavailable ? 'DATA UNAVAILABLE' : 'READY TO SCAN MARKET'}
          </div>
          <p className="text-terminal-muted">
            {dataUnavailable
              ? 'The market data is missing or outdated. Connect a provider, upload OHLC CSV, or enable Demo Historical Mode, then click ANALYZE MARKET.'
              : 'Click ANALYZE MARKET above to evaluate whether a qualified BUY or SELL setup exists.'}
          </p>
        </div>
      ) : (
        <>
          {/* Section A & B: Beginner Why + Trade Plan Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* WHY IS THE AI SUGGESTING THIS TRADE? */}
            <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-sky-400">
                <HelpCircle className="w-4 h-4" />
                {isBuy || isSell
                  ? 'WHY IS THE AI SUGGESTING THIS TRADE?'
                  : `WHY IS THE STATUS "${status}"?`}
              </div>

              <ul className="space-y-1.5 text-xs">
                {(beginner?.why_bullets || [report.decision_reason]).map((b, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <CheckCircle2
                      className={`w-3.5 h-3.5 shrink-0 mt-0.5 ${
                        isBuy ? 'text-emerald-400' : isSell ? 'text-rose-400' : 'text-amber-400'
                      }`}
                    />
                    <span>{b}</span>
                  </li>
                ))}
              </ul>

              <div className="rounded-lg bg-terminal-elevated/70 border border-terminal-border p-3 text-xs space-y-1">
                <div className="font-bold text-terminal-text">What does this mean?</div>
                <p className="text-terminal-muted leading-relaxed">
                  {beginner?.what_it_means || report.decision_reason}
                </p>
              </div>

              {(beginner?.confirmations_met?.length || beginner?.confirmations_missing?.length) ? (
                <div className="flex flex-wrap gap-1.5 pt-1 text-[11px]">
                  {beginner?.confirmations_met.map((c, idx) => (
                    <span
                      key={`met-${idx}`}
                      className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-300"
                    >
                      ✓ {c}
                    </span>
                  ))}
                  {beginner?.confirmations_missing.map((c, idx) => (
                    <span
                      key={`miss-${idx}`}
                      className="px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-300"
                    >
                      ⏳ {c}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>

            {/* TRADE PLAN (Easy-to-read Entry, SL, TP1/2/3, R:R) */}
            <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-400">
                  <Target className="w-4 h-4" />
                  TRADE PLAN
                </div>
                {report.signal_expires_at && (
                  <span className="text-[11px] text-terminal-muted font-mono">
                    Expires: {new Date(report.signal_expires_at).toISOString().slice(0, 16).replace('T', ' ')} UTC
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
                <div className="p-2.5 rounded-lg bg-terminal-elevated/60 border border-terminal-border">
                  <div className="text-[10px] text-terminal-muted uppercase">Direction</div>
                  <div
                    className={`text-sm font-extrabold mt-0.5 ${
                      plan?.direction === 'BUY'
                        ? 'text-emerald-400'
                        : plan?.direction === 'SELL'
                        ? 'text-rose-400'
                        : 'text-terminal-muted'
                    }`}
                  >
                    {plan?.direction || 'NONE'}
                  </div>
                </div>
                <div className="p-2.5 rounded-lg bg-terminal-elevated/60 border border-terminal-border sm:col-span-2">
                  <div className="text-[10px] text-terminal-muted uppercase">Entry Price / Zone</div>
                  <div className="text-sm font-bold font-mono tabular-nums mt-0.5">
                    {fmt(report.trade_levels.entry_price)}
                  </div>
                  {report.trade_levels.entry_zone_low != null && (
                    <div className="text-[10px] text-terminal-muted font-mono">
                      Zone: {fmt(report.trade_levels.entry_zone_low)} – {fmt(report.trade_levels.entry_zone_high)}
                    </div>
                  )}
                </div>
                <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30">
                  <div className="text-[10px] text-rose-300 uppercase">Stop Loss (SL)</div>
                  <div className="text-sm font-bold font-mono tabular-nums text-rose-400 mt-0.5">
                    {fmt(report.trade_levels.stop_loss)}
                  </div>
                </div>
                <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
                  <div className="text-[10px] text-emerald-300 uppercase">Take Profit 1</div>
                  <div className="text-sm font-bold font-mono tabular-nums text-emerald-400 mt-0.5">
                    {fmt(report.trade_levels.take_profit_1)}
                  </div>
                </div>
                <div className="p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                  <div className="text-[10px] text-emerald-300 uppercase">TP2 / TP3</div>
                  <div className="text-xs font-bold font-mono tabular-nums text-emerald-300 mt-0.5">
                    {fmt(report.trade_levels.take_profit_2)} / {fmt(report.trade_levels.take_profit_3)}
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs px-3 py-2 rounded-lg bg-terminal-elevated/50 border border-terminal-border">
                <span className="text-terminal-muted">Potential reward compared with risk:</span>
                <span className="font-mono font-bold text-sky-400">
                  {plan?.risk_reward_display || 'N/A'}
                </span>
              </div>

              <div className="space-y-1.5 text-xs">
                <div>
                  <span className="font-semibold text-rose-300">Why is the Stop Loss here? </span>
                  <span className="text-terminal-muted">{plan?.why_stop_loss_here}</span>
                </div>
                <div>
                  <span className="font-semibold text-emerald-300">Why are these targets selected? </span>
                  <span className="text-terminal-muted">{plan?.why_targets_selected}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Section C: Candle Pattern Story + Quick Beginner Friendly Summary Cards */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 text-xs">
            {/* Candle Pattern Explanation */}
            <div className="lg:col-span-2 rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-bold uppercase tracking-wider text-amber-400">
                  <CandlestickChart className="w-4 h-4" />
                  PATTERN: {story?.pattern_name?.toUpperCase() || 'NONE'}
                </div>
                <span className="px-2 py-0.5 rounded bg-terminal-elevated border border-terminal-border text-[11px] uppercase font-semibold">
                  {story?.direction || 'neutral'}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                <div className="space-y-1">
                  <div className="font-semibold text-terminal-text">What happened?</div>
                  <p className="text-terminal-muted leading-relaxed">{story?.what_happened}</p>
                </div>
                <div className="space-y-1">
                  <div className="font-semibold text-terminal-text">Why does the AI consider it?</div>
                  <p className="text-terminal-muted leading-relaxed">{story?.why_considered}</p>
                </div>
              </div>

              <div className="flex flex-wrap gap-3 pt-1 text-[11px] text-terminal-muted border-t border-terminal-border/60">
                <span>
                  <strong className="text-terminal-text">Candles used:</strong>{' '}
                  {story?.candles_involved?.length ? story.candles_involved.join(' -> ') : 'N/A'}
                </span>
                <span>
                  <strong className="text-emerald-300">Confirmation:</strong> {story?.confirmation_found}
                </span>
                <span>
                  <strong className="text-rose-300">What makes it fail:</strong> {story?.what_makes_it_fail}
                </span>
              </div>
            </div>

            {/* Beginner Quick Health Checks */}
            <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-2.5">
              <div className="flex items-center gap-2 font-bold uppercase tracking-wider text-terminal-muted">
                <ShieldCheck className="w-4 h-4 text-sky-400" />
                Simple Market Checks
              </div>
              <div className="space-y-2">
                <div className="p-2 rounded bg-terminal-elevated/50 border border-terminal-border">
                  <div className="text-[11px] text-terminal-muted">Do the different charts agree?</div>
                  <div className="font-semibold mt-0.5">
                    {report.multi_timeframe.has_conflict
                      ? 'No — timeframes disagree (Wait)'
                      : `Yes — aligned (${report.multi_timeframe.alignment_score}/100)`}
                  </div>
                </div>
                <div className="p-2 rounded bg-terminal-elevated/50 border border-terminal-border">
                  <div className="text-[11px] text-terminal-muted">How much is the market moving?</div>
                  <div className="font-semibold mt-0.5">{report.indicators.volatility_condition}</div>
                </div>
                <div className="p-2 rounded bg-terminal-elevated/50 border border-terminal-border">
                  <div className="text-[11px] text-terminal-muted">What would make this trade wrong?</div>
                  <div className="text-[11px] mt-0.5 text-rose-300">
                    {report.trade_levels.stop_loss != null
                      ? `Price moving past Stop Loss (${fmt(report.trade_levels.stop_loss)})`
                      : 'Structure invalidation or conflicting higher timeframe.'}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {report.risk_warnings.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 flex items-start gap-2 text-xs text-amber-300">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                {report.risk_warnings.map((w, i) => (
                  <div key={i}>{w}</div>
                ))}
              </div>
            </div>
          )}

          {/* Expandable Advanced Technical Toggle */}
          <div className="pt-1">
            <button
              onClick={() => setShowAdvanced((v) => !v)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-sky-400 hover:underline"
            >
              {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              {showAdvanced ? 'Hide' : 'Show'} Advanced Technical Breakdown
            </button>
            {showAdvanced && (
              <div className="mt-3 p-3 rounded-xl border border-terminal-border bg-terminal-panel text-xs text-terminal-muted">
                Full quantitative metrics, score weights, liquidity zones, and position sizing are available in the detailed report panel below.
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}
