import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, Filter } from 'lucide-react'
import { api } from '../services/api'

export const JournalPage: React.FC = () => {
  const [symbol, setSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('')
  const [decision, setDecision] = useState('')
  const [outcome, setOutcome] = useState('')
  const [pattern, setPattern] = useState('')

  const journalQ = useQuery({
    queryKey: ['journal', symbol, timeframe, decision, outcome, pattern],
    queryFn: () => api.listJournal({ symbol, timeframe, decision, outcome, pattern }),
  })

  const handleOutcomeChange = async (id: string, nextOutcome: string) => {
    await api.updateJournal(id, { outcome: nextOutcome })
    journalQ.refetch()
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-sky-400" />
          <div>
            <h2 className="text-base font-bold">Automatic Trade Analysis Journal</h2>
            <p className="text-xs text-terminal-muted">
              Every analysis—including rejected setups and WAIT decisions—is audited here.
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
            value={decision}
            onChange={(e) => setDecision(e.target.value)}
            className="px-2.5 py-1.5 rounded bg-terminal-elevated border border-terminal-border"
          >
            <option value="">All Decisions</option>
            <option value="BUY SETUP">BUY SETUP</option>
            <option value="SELL SETUP">SELL SETUP</option>
            <option value="WAIT">WAIT</option>
            <option value="NO VALID SETUP">NO VALID SETUP</option>
          </select>
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            className="px-2.5 py-1.5 rounded bg-terminal-elevated border border-terminal-border"
          >
            <option value="">All Outcomes</option>
            <option value="pending">Pending</option>
            <option value="win">Win</option>
            <option value="loss">Loss</option>
            <option value="breakeven">Breakeven</option>
            <option value="rejected">Rejected</option>
          </select>
          <input
            placeholder="Pattern filter"
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            className="px-2.5 py-1.5 rounded bg-terminal-elevated border border-terminal-border w-32"
          />
        </div>
      </div>

      <div className="rounded-xl border border-terminal-border bg-terminal-panel overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead className="bg-terminal-elevated text-terminal-muted border-b border-terminal-border">
            <tr>
              <th className="p-3">Time (UTC)</th>
              <th className="p-3">Market</th>
              <th className="p-3">Decision</th>
              <th className="p-3">Score</th>
              <th className="p-3">Patterns</th>
              <th className="p-3">Entry / SL / TP1</th>
              <th className="p-3">R:R</th>
              <th className="p-3">Outcome</th>
              <th className="p-3">Rationale</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-terminal-border">
            {(journalQ.data || []).length === 0 ? (
              <tr>
                <td colSpan={9} className="p-8 text-center text-terminal-muted">
                  No journal entries found. Run an analysis on the Dashboard to record entries.
                </td>
              </tr>
            ) : (
              journalQ.data?.map((row) => (
                <tr key={row.id} className="hover:bg-terminal-elevated/40">
                  <td className="p-3 font-mono whitespace-nowrap">
                    {new Date(row.created_at).toISOString().slice(0, 16).replace('T', ' ')}
                  </td>
                  <td className="p-3 font-semibold">
                    {row.symbol} <span className="text-terminal-muted font-normal">({row.timeframe})</span>
                    {row.is_demo && (
                      <span className="ml-1.5 px-1 py-0.5 rounded bg-amber-500/15 text-amber-400 text-[10px]">
                        DEMO
                      </span>
                    )}
                  </td>
                  <td className="p-3 font-bold whitespace-nowrap">{row.decision}</td>
                  <td className="p-3 font-mono">{row.setup_score}/100</td>
                  <td className="p-3 max-w-[160px] truncate">{row.patterns.join(', ') || 'None'}</td>
                  <td className="p-3 font-mono whitespace-nowrap">
                    {row.entry_price ?? '—'} / {row.stop_loss ?? '—'} / {row.take_profit_1 ?? '—'}
                  </td>
                  <td className="p-3 font-mono">{row.risk_reward ? `${row.risk_reward}:1` : '—'}</td>
                  <td className="p-3">
                    <select
                      value={row.outcome}
                      onChange={(e) => handleOutcomeChange(row.id, e.target.value)}
                      className="px-2 py-1 rounded bg-terminal-elevated border border-terminal-border text-[11px]"
                    >
                      <option value="pending">pending</option>
                      <option value="win">win</option>
                      <option value="loss">loss</option>
                      <option value="breakeven">breakeven</option>
                      <option value="rejected">rejected</option>
                    </select>
                  </td>
                  <td className="p-3 max-w-xs text-terminal-muted">{row.decision_reason}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
