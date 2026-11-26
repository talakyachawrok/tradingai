import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, RotateCcw, ShieldAlert, Wallet } from 'lucide-react'
import { api } from '../services/api'

interface Props {
  allowDemo: boolean
}

export const PaperTradingPage: React.FC<Props> = ({ allowDemo }) => {
  const [symbol, setSymbol] = useState('XAUUSD')
  const [direction, setDirection] = useState('BUY')
  const [entryPrice, setEntryPrice] = useState('')
  const [stopLoss, setStopLoss] = useState('')
  const [takeProfit, setTakeProfit] = useState('')
  const [riskPct, setRiskPct] = useState('1.0')
  const [error, setError] = useState<string | null>(null)

  const accountQ = useQuery({ queryKey: ['paper-account'], queryFn: api.getPaperAccount })
  const positionsQ = useQuery({ queryKey: ['paper-positions'], queryFn: api.getPaperPositions })

  const handleOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      await api.openPaperOrder({
        symbol,
        direction,
        entry_price: entryPrice ? Number(entryPrice) : null,
        stop_loss: Number(stopLoss),
        take_profit: Number(takeProfit),
        risk_percentage: Number(riskPct),
        is_demo_data: allowDemo,
      })
      setEntryPrice('')
      setStopLoss('')
      setTakeProfit('')
      accountQ.refetch()
      positionsQ.refetch()
    } catch (err: any) {
      setError(err.message)
    }
  }

  const handleSync = async () => {
    await api.syncPaper(allowDemo)
    accountQ.refetch()
    positionsQ.refetch()
  }

  const handleReset = async () => {
    await api.resetPaper()
    accountQ.refetch()
    positionsQ.refetch()
  }

  const acc = accountQ.data

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-2.5 text-xs text-sky-300 flex items-center justify-between">
        <span>
          <strong>SIMULATED PAPER TRADING:</strong> Virtual execution only—no real-money orders are ever transmitted.
        </span>
        <div className="flex items-center gap-2">
          <button onClick={handleSync} className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-sky-600 text-white font-semibold">
            <RefreshCw className="w-3 h-3" /> Sync Market P&L
          </button>
          <button onClick={handleReset} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-terminal-border bg-terminal-panel text-terminal-text">
            <RotateCcw className="w-3 h-3" /> Reset $10k
          </button>
        </div>
      </div>

      {acc?.risk_limit_breached && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300 flex items-start gap-2">
          <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <strong>Risk Limit Reached (New Orders Blocked):</strong> {acc.risk_limit_reasons.join(' ')}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-6 gap-3 text-xs">
        {[
          ['Balance', `$${acc?.balance ?? 10000}`],
          ['Equity', `$${acc?.equity ?? 10000}`],
          ['Unrealized P&L', `$${acc?.unrealized_pnl ?? 0}`],
          ['Realized P&L', `$${acc?.realized_pnl ?? 0}`],
          ['Daily Loss %', `${acc?.daily_loss_pct ?? 0}%`],
          ['Win Rate', `${acc?.win_rate_pct ?? 0}% (${acc?.winning_trades ?? 0}W/${acc?.losing_trades ?? 0}L)`],
        ].map(([k, v]) => (
          <div key={String(k)} className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
            <div className="text-terminal-muted">{k}</div>
            <div className="text-base font-bold font-mono tabular-nums mt-0.5">{v}</div>
          </div>
        ))}
      </div>

      {/* Order Form */}
      <form onSubmit={handleOrder} className="rounded-xl border border-terminal-border bg-terminal-panel p-4 grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
        <div className="col-span-2 md:col-span-6 flex items-center gap-2 font-semibold text-terminal-muted uppercase">
          <Wallet className="w-4 h-4 text-sky-400" /> New Virtual Paper Order
        </div>
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-semibold">
          <option value="XAUUSD">XAUUSD</option>
          <option value="EURUSD">EURUSD</option>
          <option value="GBPUSD">GBPUSD</option>
          <option value="BTCUSD">BTCUSD</option>
        </select>
        <select value={direction} onChange={(e) => setDirection(e.target.value)} className="px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-semibold">
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
        </select>
        <input type="number" step="any" placeholder="Entry (blank=market)" value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} className="px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
        <input type="number" step="any" required placeholder="Stop Loss" value={stopLoss} onChange={(e) => setStopLoss(e.target.value)} className="px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
        <input type="number" step="any" required placeholder="Take Profit" value={takeProfit} onChange={(e) => setTakeProfit(e.target.value)} className="px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
        <div className="flex gap-2">
          <input type="number" step="0.1" value={riskPct} onChange={(e) => setRiskPct(e.target.value)} className="w-16 px-2 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
          <button type="submit" className="flex-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold">
            Place Order
          </button>
        </div>
        {error && <div className="col-span-2 md:col-span-6 text-rose-400">{error}</div>}
      </form>

      {/* Positions Table */}
      <div className="rounded-xl border border-terminal-border bg-terminal-panel overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead className="bg-terminal-elevated text-terminal-muted border-b border-terminal-border">
            <tr>
              <th className="p-3">Symbol</th>
              <th className="p-3">Side</th>
              <th className="p-3">Status</th>
              <th className="p-3">Entry</th>
              <th className="p-3">Current / Exit</th>
              <th className="p-3">SL / TP</th>
              <th className="p-3">Risk ($)</th>
              <th className="p-3">P&L</th>
              <th className="p-3">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-terminal-border">
            {(positionsQ.data || []).length === 0 ? (
              <tr>
                <td colSpan={9} className="p-8 text-center text-terminal-muted">
                  No paper positions yet. Execute from a qualified Dashboard analysis or place a virtual order above.
                </td>
              </tr>
            ) : (
              positionsQ.data?.map((p) => {
                const pnl = p.status === 'OPEN' ? p.unrealized_pnl : p.realized_pnl
                return (
                  <tr key={p.trade_id} className="hover:bg-terminal-elevated/40">
                    <td className="p-3 font-semibold">{p.symbol}</td>
                    <td className={`p-3 font-bold ${p.direction === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>{p.direction}</td>
                    <td className="p-3">{p.status}</td>
                    <td className="p-3 font-mono">{p.entry_price}</td>
                    <td className="p-3 font-mono">{p.exit_price ?? p.current_price}</td>
                    <td className="p-3 font-mono">{p.stop_loss} / {p.take_profit}</td>
                    <td className="p-3 font-mono">${p.risk_amount} ({p.risk_percentage}%)</td>
                    <td className={`p-3 font-mono font-bold ${pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      ${pnl.toFixed(2)}
                    </td>
                    <td className="p-3">
                      {p.status === 'OPEN' && (
                        <button
                          onClick={async () => {
                            await api.closePaperOrder(p.trade_id)
                            accountQ.refetch()
                            positionsQ.refetch()
                          }}
                          className="px-2.5 py-1 rounded bg-rose-600/80 hover:bg-rose-500 text-white"
                        >
                          Close
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
