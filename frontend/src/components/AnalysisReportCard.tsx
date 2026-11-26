import React, { useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Layers,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  XCircle,
} from 'lucide-react'
import type { TradeAnalysisReport } from '../types/trading'
import { PositionSizeCalculator } from './PositionSizeCalculator'

interface Props {
  report: TradeAnalysisReport
  decimals?: number
  onSendToPaper?: (report: TradeAnalysisReport) => void
  paperSubmitting?: boolean
}

export const AnalysisReportCard: React.FC<Props> = ({
  report,
  decimals = 5,
  onSendToPaper,
  paperSubmitting,
}) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'explanations' | 'levels' | 'mtf'>('overview')

  const isBuy = report.final_decision === 'BUY SETUP'
  const isSell = report.final_decision === 'SELL SETUP'
  const isWait = report.final_decision === 'WAIT'

  const decisionBadge = isBuy
    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40'
    : isSell
    ? 'bg-rose-500/15 text-rose-400 border-rose-500/40'
    : isWait
    ? 'bg-amber-500/15 text-amber-400 border-amber-500/40'
    : 'bg-slate-500/15 text-slate-300 border-slate-500/40'

  const DecisionIcon = isBuy
    ? TrendingUp
    : isSell
    ? TrendingDown
    : isWait
    ? Clock
    : XCircle

  const fmt = (v?: number | null) => (v !== null && v !== undefined ? v.toFixed(decimals) : 'N/A')

  return (
    <div
      className={`rounded-xl border border-terminal-border bg-terminal-panel p-5 space-y-5 ${
        isBuy || isSell ? 'signal-card-glow' : ''
      }`}
    >
      {/* Top Decision Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-terminal-border pb-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-bold tracking-wide ${decisionBadge}`}>
              <DecisionIcon className="w-4 h-4" />
              {report.final_decision}
            </span>
            <span className="text-xs px-2 py-0.5 rounded bg-terminal-elevated border border-terminal-border font-mono">
              {report.symbol} · {report.timeframe}
            </span>
            <span className="text-xs px-2 py-0.5 rounded bg-terminal-elevated border border-terminal-border">
              {report.connection_status} ({report.provider})
            </span>
            {report.is_demo && (
              <span className="text-xs px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 font-semibold">
                DEMO HISTORICAL DATA
              </span>
            )}
          </div>
          <p className="text-sm text-terminal-text font-medium pt-1">{report.decision_reason}</p>
        </div>

        <div className="flex items-center gap-4 shrink-0">
          <div className="text-right">
            <div className="text-[11px] uppercase tracking-wider text-terminal-muted">Setup Score</div>
            <div className="text-2xl font-bold tabular-nums">
              {report.setup_score.total_score}
              <span className="text-sm font-normal text-terminal-muted">/100</span>
            </div>
            <div className="text-xs text-sky-400 font-medium">{report.setup_score.grade_label}</div>
          </div>

          {(isBuy || isSell) && report.trade_levels.is_valid && onSendToPaper && (
            <button
              onClick={() => onSendToPaper(report)}
              disabled={paperSubmitting}
              className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-semibold transition"
            >
              {paperSubmitting ? 'Submitting...' : 'Paper Trade Setup'}
            </button>
          )}
        </div>
      </div>

      {/* Risk Warnings */}
      {report.risk_warnings.length > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 flex items-start gap-2.5 text-xs text-amber-300">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            {report.risk_warnings.map((w, i) => (
              <div key={i}>{w}</div>
            ))}
          </div>
        </div>
      )}

      {/* Sub-navigation tabs */}
      <div className="flex flex-wrap gap-2 border-b border-terminal-border pb-2">
        {[
          { id: 'overview', label: 'Score & Evidence' },
          { id: 'explanations', label: 'AI Explanations (8 Sections)' },
          { id: 'levels', label: 'Trade Plan & Position Sizing' },
          { id: 'mtf', label: 'Multi-Timeframe & Liquidity' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id as typeof activeTab)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
              activeTab === t.id
                ? 'bg-sky-500/15 text-sky-400 border border-sky-500/30'
                : 'text-terminal-muted hover:text-terminal-text hover:bg-terminal-elevated'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab 1: Score & Separated Facts vs Interpretations */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-terminal-muted">
              Transparent Setup Score Breakdown
            </h4>
            <div className="space-y-2.5">
              {report.setup_score.breakdown.map((item) => {
                const pct = item.max_score > 0 ? (item.score / item.max_score) * 100 : 0
                return (
                  <div key={item.category} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium">{item.category}</span>
                      <span className="font-mono tabular-nums">
                        {item.score}/{item.max_score}
                      </span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-terminal-elevated overflow-hidden">
                      <div
                        className="h-full rounded-full bg-sky-500 transition-all"
                        style={{ width: `${Math.min(100, pct)}%` }}
                      />
                    </div>
                    <p className="text-[11px] text-terminal-muted">{item.reason}</p>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="space-y-4">
            {/* Probability Model Separation */}
            <div className="rounded-lg border border-terminal-border bg-terminal-elevated/60 p-3.5 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-terminal-muted">
                  ML Probability Model
                </span>
                <span
                  className={`text-[11px] px-2 py-0.5 rounded font-semibold ${
                    report.probability.model_validated
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : 'bg-amber-500/15 text-amber-400'
                  }`}
                >
                  {report.probability.status_label}
                </span>
              </div>
              {report.probability.model_validated &&
              report.probability.estimated_win_probability !== null &&
              report.probability.estimated_win_probability !== undefined ? (
                <div className="text-lg font-bold tabular-nums">
                  {(report.probability.estimated_win_probability * 100).toFixed(1)}% estimated TP1-before-SL probability
                </div>
              ) : (
                <p className="text-xs text-terminal-muted">
                  Setup score ({report.setup_score.total_score}/100) is NOT a win probability. Train & validate the ML model in the Probability Lab on historical data first.
                </p>
              )}
            </div>

            {/* Market Facts vs Calculated Findings */}
            <div className="rounded-lg border border-terminal-border bg-terminal-elevated/40 p-3.5 space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-terminal-muted">
                Facts From Market Data
              </h4>
              <ul className="text-xs space-y-1 text-terminal-text">
                {report.facts_summary.map((f, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-sky-400 shrink-0 mt-0.5" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-lg border border-terminal-border bg-terminal-elevated/40 p-3.5 space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-terminal-muted">
                Calculated Technical Findings
              </h4>
              <ul className="text-xs space-y-1 text-terminal-text">
                {report.calculated_findings.map((f, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <Layers className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Detected Patterns */}
            <div className="rounded-lg border border-terminal-border bg-terminal-elevated/40 p-3.5 space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-terminal-muted">
                Detected Candlestick Patterns ({report.patterns.length})
              </h4>
              {report.patterns.length === 0 ? (
                <p className="text-xs text-terminal-muted">No notable candlestick patterns in recent bars.</p>
              ) : (
                <div className="space-y-2">
                  {report.patterns.slice(0, 4).map((p, i) => (
                    <div key={i} className="text-xs border-l-2 border-sky-500/50 pl-2.5">
                      <div className="flex justify-between font-medium">
                        <span>{p.name}</span>
                        <span className="font-mono text-terminal-muted">
                          {p.classification.toUpperCase()} · {p.strength_score}/100
                        </span>
                      </div>
                      <p className="text-[11px] text-terminal-muted mt-0.5">{p.explanation}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Structured 8-Section AI Explanation */}
      {activeTab === 'explanations' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-terminal-muted">
            <span>Explanation Mode: <strong className="text-terminal-text">{report.explanation.engine_mode}</strong></span>
            <span>Grounded strictly on computed OHLCV metrics</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {[
              { title: 'A. Pattern Explanation', body: report.explanation.pattern_explanation },
              { title: 'B. Market Structure', body: report.explanation.market_structure_explanation },
              { title: 'C. Liquidity Analysis', body: report.explanation.liquidity_explanation },
              { title: 'D. Indicator Alignment', body: report.explanation.indicator_explanation },
              { title: 'E. Multi-Timeframe Context', body: report.explanation.multi_timeframe_explanation },
              { title: 'F. Trade Rationale', body: report.explanation.trade_rationale },
              { title: 'G. Setup Invalidation', body: report.explanation.invalidation },
              { title: 'H. Risk Assessment', body: report.explanation.risk_assessment },
            ].map((sec) => (
              <div key={sec.title} className="rounded-lg border border-terminal-border bg-terminal-elevated/50 p-3.5 space-y-1.5">
                <h5 className="text-xs font-semibold text-sky-400">{sec.title}</h5>
                <p className="text-xs leading-relaxed text-terminal-text">{sec.body}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 3: Trade Plan & Position Size Calculator */}
      {activeTab === 'levels' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-terminal-muted">
              Potential Trade Plan
            </h4>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-lg border border-terminal-border bg-terminal-elevated/50">
                <div className="text-terminal-muted">Entry Price / Zone</div>
                <div className="text-base font-bold font-mono tabular-nums mt-0.5">
                  {fmt(report.trade_levels.entry_price)}
                </div>
                <div className="text-[11px] text-terminal-muted font-mono">
                  {fmt(report.trade_levels.entry_zone_low)} – {fmt(report.trade_levels.entry_zone_high)}
                </div>
              </div>
              <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-500/5">
                <div className="text-rose-400">Stop Loss</div>
                <div className="text-base font-bold font-mono tabular-nums mt-0.5 text-rose-400">
                  {fmt(report.trade_levels.stop_loss)}
                </div>
                <div className="text-[11px] text-terminal-muted mt-0.5">
                  {report.trade_levels.stop_loss_explanation || 'N/A'}
                </div>
              </div>
            </div>

            <div className="space-y-2 text-xs">
              {[
                { label: 'TP1', price: report.trade_levels.take_profit_1, rr: report.trade_levels.risk_reward_tp1, exp: report.trade_levels.tp1_explanation },
                { label: 'TP2', price: report.trade_levels.take_profit_2, rr: report.trade_levels.risk_reward_tp2, exp: report.trade_levels.tp2_explanation },
                { label: 'TP3', price: report.trade_levels.take_profit_3, rr: report.trade_levels.risk_reward_tp3, exp: report.trade_levels.tp3_explanation },
              ].map((tp) => (
                <div key={tp.label} className="p-2.5 rounded-lg border border-terminal-border bg-terminal-elevated/40 flex items-start justify-between gap-3">
                  <div>
                    <span className="font-semibold text-emerald-400">{tp.label}: </span>
                    <span className="font-mono font-bold tabular-nums">{fmt(tp.price)}</span>
                    <p className="text-[11px] text-terminal-muted mt-0.5">{tp.exp || 'Not calculated'}</p>
                  </div>
                  <span className="font-mono text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 shrink-0">
                    {tp.rr ? `${tp.rr}:1 R:R` : '—'}
                  </span>
                </div>
              ))}
            </div>

            {report.trade_levels.rejection_reasons.length > 0 && (
              <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-500/10 text-xs text-rose-300 space-y-1">
                <div className="font-semibold flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4" /> Level Validation Rejections
                </div>
                {report.trade_levels.rejection_reasons.map((r, i) => (
                  <div key={i}>• {r}</div>
                ))}
              </div>
            )}
          </div>

          <PositionSizeCalculator
            symbol={report.symbol}
            defaultEntry={report.trade_levels.entry_price || report.current_price}
            defaultStopLoss={report.trade_levels.stop_loss || undefined}
          />
        </div>
      )}

      {/* Tab 4: Multi-Timeframe & Liquidity */}
      {activeTab === 'mtf' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 text-xs">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="font-semibold uppercase tracking-wider text-terminal-muted">
                Multi-Timeframe Alignment ({report.multi_timeframe.alignment_score}/100)
              </h4>
              {report.multi_timeframe.has_conflict && (
                <span className="px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 font-semibold">
                  CONFLICT
                </span>
              )}
            </div>
            <div className="space-y-2">
              {report.multi_timeframe.timeframes.map((tf) => (
                <div key={tf.timeframe} className="p-3 rounded-lg border border-terminal-border bg-terminal-elevated/40">
                  <div className="flex justify-between font-medium">
                    <span>
                      {tf.timeframe.toUpperCase()} ({tf.role.replace('_', ' ')})
                    </span>
                    <span className={tf.available ? 'text-sky-400' : 'text-rose-400'}>
                      {tf.available ? tf.trend.toUpperCase() : 'UNAVAILABLE'}
                    </span>
                  </div>
                  <p className="text-[11px] text-terminal-muted mt-1">{tf.notes}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-3">
            <h4 className="font-semibold uppercase tracking-wider text-terminal-muted">
              Liquidity Zones, Sweeps & FVGs
            </h4>
            <p className="text-terminal-muted">{report.liquidity.summary}</p>
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {report.liquidity.sweep_events.map((s, i) => (
                <div key={`sw-${i}`} className="p-2.5 rounded border border-amber-500/30 bg-amber-500/10">
                  <div className="font-semibold text-amber-300">
                    Sweep ({s.direction}) · [{s.certainty}]
                  </div>
                  <p className="text-[11px] text-terminal-text mt-0.5">{s.explanation}</p>
                </div>
              ))}
              {report.liquidity.liquidity_zones.map((z, i) => (
                <div key={`lz-${i}`} className="p-2.5 rounded border border-terminal-border bg-terminal-elevated/40">
                  <div className="flex justify-between font-medium">
                    <span>{z.zone_type.replace('_', ' ').toUpperCase()}</span>
                    <span className="text-[11px] text-terminal-muted">{z.certainty}</span>
                  </div>
                  <p className="text-[11px] text-terminal-muted mt-0.5">{z.explanation}</p>
                </div>
              ))}
              {report.liquidity.fair_value_gaps.map((f, i) => (
                <div key={`fvg-${i}`} className="p-2.5 rounded border border-purple-500/30 bg-purple-500/5">
                  <div className="font-medium text-purple-300">
                    FVG ({f.direction}) · {f.filled ? 'Filled' : 'Unfilled'}
                  </div>
                  <p className="text-[11px] text-terminal-muted mt-0.5">{f.explanation}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
