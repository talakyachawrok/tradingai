import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BellRing, Filter, RefreshCw } from 'lucide-react'
import { api } from '../services/api'
import type { SignalStatus } from '../types/trading'

interface Props {
  allowDemo: boolean
}

const STATUS_BADGES: Record<SignalStatus, string> = {
  'BUY SIGNAL': 'bg-emerald-600 text-white',
  'SELL SIGNAL': 'bg-rose-600 text-white',
  'WAIT FOR CONFIRMATION': 'bg-amber-500 text-slate-950',
  'SETUP FORMING': 'bg-amber-500/20 text-amber-300 border border-amber-500/40',
  'TARGET HIT': 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40',
  'STOP LOSS HIT': 'bg-rose-500/20 text-rose-300 border border-rose-500/40',
  'SIGNAL EXPIRED': 'bg-slate-600/40 text-slate-300',
  'NO TRADE': 'bg-slate-700/60 text-slate-300',
  'DATA UNAVAILABLE': 'bg-rose-900/50 text-rose-300',
  SCANNING: 'bg-sky-600 text-white',
}

export const SignalHistoryPage: React.FC<Props> = ({ allowDemo }) => {
  const [symbol, setSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('')
  const [direction, setDirection] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [trackingBusy, setTrackingBusy] = useState(false)

  const signalsQ = useQuery({
    queryKey: ['signals', symbol, timeframe, direction, dateFrom],
    queryFn: () =>
      api.listSignals({
        symbol,
        timeframe,
        direction,
        date_from: dateFrom ? `${dateFrom}T00:00:00Z` : '',
      }),
    refetchInterval: 20000,
  })

  const handleTrackSync = async () => {
    setTrackingBusy(true)
    try {
      await api.trackSignals(allowDemo)
      await signalsQ.refetch()
    } finally {
      setTrackingBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <BellRing className="w-5 h-5 text-sky-400" />
          <div>
            <h2 className="text-base font-bold">TRADE SIGNAL HISTORY</h2>
            <p className="text-xs text-terminal-muted">
              Non-repainting history of every AI trade signal, entry/SL/TP tracking against market candles, and beginner explanations.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Filter className="w-4 h-4 text-terminal-muted" />
          <input
            placeholder="Symbol (e.g. XAUUSD)"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="px-2.5 py-1.5 rounded bg-terminal-elevated border border-terminal-border w-32"
          />
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="px-2.5 py-1.5 rounded bg-terminal-elevated border border-terminal-border"
          >
            <option value="">All Timeframes</option>
            {['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d'].map((tf) => (
              <option key={tf} value={tf}>{tf}</option>
            ))}
          </select>
          <select
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
            className="px-2.5 py-1.5 rounded bg-terminal-elevated border border-terminal-border"
          >
            <option value="">All Directions</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
            <option value="WAIT">WAIT</option>
            <option value="NONE">NO TRADE</option>
          </select>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="px-2.5 py-1.5 rounded bg-terminal-elevated border border-terminal-border"
          />
          <button
            onClick={handleTrackSync}
            disabled={trackingBusy}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${trackingBusy ? 'animate-spin' : ''}`} />
            Track Against Market
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-terminal-border bg-terminal-panel overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead className="bg-terminal-elevated text-terminal-muted border-b border-terminal-border">
            <tr>
              <th className="p-3">Signal Time (UTC)</th>
              <th className="p-3">Symbol / TF</th>
              <th className="p-3">Direction</th>
              <th className="p-3">Status</th>
              <th className="p-3">Entry / SL / TP1</th>
              <th className="p-3">Score</th>
              <th className="p-3">Live Tracking Milestones</th>
              <th className="p-3">Simple Explanation</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-terminal-border">
            {(signalsQ.data || []).length === 0 ? (
              <tr>
                <td colSpan={8} className="p-8 text-center text-terminal-muted">
                  No signals stored yet. Run an analysis on the Market Analyzer page to generate and track signals.
                </td>
              </tr>
            ) : (
              signalsQ.data?.map((sig) => (
                <tr key={sig.signal_id} className="hover:bg-terminal-elevated/40 align-top">
                  <td className="p-3 font-mono whitespace-nowrap">
                    {new Date(sig.created_at).toISOString().slice(0, 16).replace('T', ' ')}
                  </td>
                  <td className="p-3 font-semibold whitespace-nowrap">
                    {sig.symbol} <span className="text-terminal-muted">({sig.timeframe})</span>
                    {sig.is_demo && (
                      <span className="ml-1 px-1 py-0.5 rounded bg-amber-500/15 text-amber-400 text-[10px]">
                        DEMO
                      </span>
                    )}
                  </td>
                  <td
                    className={`p-3 font-extrabold ${
                      sig.direction === 'BUY'
                        ? 'text-emerald-400'
                        : sig.direction === 'SELL'
                        ? 'text-rose-400'
                        : 'text-amber-400'
                    }`}
                  >
                    {sig.direction}
                  </td>
                  <td className="p-3 whitespace-nowrap">
                    <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${STATUS_BADGES[sig.status]}`}>
                      {sig.status}
                    </span>
                  </td>
                  <td className="p-3 font-mono whitespace-nowrap">
                    {sig.entry_price ?? '—'} / {sig.stop_loss ?? '—'} / {sig.take_profit_1 ?? '—'}
                  </td>
                  <td className="p-3 font-mono">
                    <div>{sig.setup_score}/100</div>
                    {sig.probability_estimate != null && (
                      <div className="text-[10px] text-sky-400">
                        ML: {(sig.probability_estimate * 100).toFixed(1)}%
                      </div>
                    )}
                  </td>
                  <td className="p-3 space-y-1">
                    <div className="flex flex-wrap gap-1 text-[10px]">
                      {sig.tracking.entry_reached && (
                        <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300">Entry Hit</span>
                      )}
                      {sig.tracking.tp1_reached && (
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300">TP1 Hit</span>
                      )}
                      {sig.tracking.tp2_reached && (
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300">TP2 Hit</span>
                      )}
                      {sig.tracking.tp3_reached && (
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/25 text-emerald-300">TP3 Hit</span>
                      )}
                      {sig.tracking.sl_reached && (
                        <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300">SL Hit</span>
                      )}
                      {sig.tracking.expired && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-500/20 text-slate-300">Expired</span>
                      )}
                    </div>
                    <div className="text-[11px] text-terminal-muted">{sig.tracking.tracking_note}</div>
                  </td>
                  <td className="p-3 max-w-xs text-terminal-muted">
                    <div className="font-semibold text-terminal-text">{sig.beginner_explanation.headline}</div>
                    <div>{sig.beginner_explanation.what_it_means}</div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
