import React, { useState } from 'react'
import { AlertTriangle, BarChart3, Play } from 'lucide-react'
import { api } from '../services/api'
import type { BacktestResult, Timeframe } from '../types/trading'

interface Props {
  allowDemo: boolean
}

export const BacktestPage: React.FC<Props> = ({ allowDemo }) => {
  const [symbol, setSymbol] = useState('BTCUSD')
  const [timeframe, setTimeframe] = useState<Timeframe>('1h')
  const [initialBalance, setInitialBalance] = useState('10000')
  const [riskPct, setRiskPct] = useState('1.0')
  const [minScore, setMinScore] = useState('65')
  const [minRr, setMinRr] = useState('1.5')
  const [spreadBps, setSpreadBps] = useState('1.5')
  const [slippageBps, setSlippageBps] = useState('1.0')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<BacktestResult | null>(null)

  const handleRun = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await api.runBacktest({
        symbol,
        timeframe,
        initial_balance: Number(initialBalance),
        risk_per_trade_pct: Number(riskPct),
        min_setup_score: Number(minScore),
        min_risk_reward: Number(minRr),
        spread_bps: Number(spreadBps),
        slippage_bps: Number(slippageBps),
        use_demo_if_unavailable: allowDemo,
      })
      setResult(res)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const renderEquityCurve = (curve: BacktestResult['equity_curve']) => {
    if (curve.length < 2) return null
    const values = curve.map((p) => p.balance)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const span = Math.max(max - min, 1)
    const width = 760
    const height = 180
    const pts = curve
      .map((p, idx) => {
        const x = (idx / (curve.length - 1)) * width
        const y = height - ((p.balance - min) / span) * (height - 20) - 10
        return `${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')

    return (
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-44 overflow-visible">
        <polyline
          fill="none"
          stroke="#38bdf8"
          strokeWidth="2.2"
          points={pts}
        />
      </svg>
    )
  }

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-terminal-border bg-terminal-panel p-5 space-y-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-sky-400" />
          <div>
            <h2 className="text-base font-bold">Look-Ahead-Free Historical Backtesting Engine</h2>
            <p className="text-xs text-terminal-muted">
              Simulates next-bar open execution with spread/slippage costs and conservative SL-first intrabar conflict handling.
            </p>
          </div>
        </div>

        <form onSubmit={handleRun} className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 text-xs">
          <label className="space-y-1">
            <span className="text-terminal-muted">Symbol</span>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-semibold"
            >
              <option value="XAUUSD">XAUUSD</option>
              <option value="EURUSD">EURUSD</option>
              <option value="GBPUSD">GBPUSD</option>
              <option value="BTCUSD">BTCUSD</option>
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Timeframe</span>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value as Timeframe)}
              className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border"
            >
              {['5m', '15m', '30m', '1h', '4h', '1d'].map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Initial Balance</span>
            <input type="number" value={initialBalance} onChange={(e) => setInitialBalance(e.target.value)} className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Risk % / Trade</span>
            <input type="number" step="0.1" value={riskPct} onChange={(e) => setRiskPct(e.target.value)} className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Min Setup Score</span>
            <input type="number" value={minScore} onChange={(e) => setMinScore(e.target.value)} className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Min R:R</span>
            <input type="number" step="0.1" value={minRr} onChange={(e) => setMinRr(e.target.value)} className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Spread + Slip (bps)</span>
            <input type="number" step="0.1" value={spreadBps} onChange={(e) => { setSpreadBps(e.target.value); setSlippageBps(e.target.value) }} className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 px-3 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold flex items-center justify-center gap-1.5"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              {loading ? 'Running...' : 'Run Backtest'}
            </button>
          </div>
        </form>

        {error && <p className="text-xs text-rose-400">{error}</p>}
      </div>

      {result && (
        <div className="space-y-5">
          {result.overfitting_warnings.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300 space-y-1">
              <div className="font-semibold flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4" /> Overfitting & Statistical Caveats
              </div>
              {result.overfitting_warnings.map((w, i) => (
                <div key={i}>• {w}</div>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-6 gap-3 text-xs">
            {[
              ['Total Trades', result.total_trades],
              ['Win Rate', `${result.win_rate_pct}%`],
              ['Profit Factor', result.profit_factor ?? 'N/A'],
              ['Net Return', `$${result.net_return_amount} (${result.net_return_pct}%)`],
              ['Max Drawdown', `${result.max_drawdown_pct}%`],
              ['Expectancy', `${result.expectancy_r}R ($${result.expectancy_amount})`],
            ].map(([label, val]) => (
              <div key={String(label)} className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
                <div className="text-terminal-muted">{label}</div>
                <div className="text-base font-bold font-mono tabular-nums mt-0.5">{val}</div>
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-2">
            <div className="flex justify-between text-xs">
              <span className="font-semibold uppercase tracking-wider text-terminal-muted">
                Equity Curve ({result.data_source}{result.is_demo ? ' · DEMO DATA' : ''})
              </span>
              <span className="font-mono">Final Balance: ${result.final_balance}</span>
            </div>
            {renderEquityCurve(result.equity_curve) || (
              <p className="text-xs text-terminal-muted py-6 text-center">No closed trades generated under current filters.</p>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs">
            <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-2">
              <h4 className="font-semibold text-terminal-muted uppercase">Performance By Pattern</h4>
              {result.by_pattern.map((b) => (
                <div key={b.key} className="flex justify-between border-b border-terminal-border/50 pb-1">
                  <span>{b.key} ({b.trades} trades)</span>
                  <span className="font-mono">{b.win_rate_pct}% WR · ${b.net_pnl}</span>
                </div>
              ))}
            </div>
            <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-2">
              <h4 className="font-semibold text-terminal-muted uppercase">Performance By Market Regime</h4>
              {result.by_regime.map((b) => (
                <div key={b.key} className="flex justify-between border-b border-terminal-border/50 pb-1">
                  <span>{b.key} ({b.trades} trades)</span>
                  <span className="font-mono">{b.win_rate_pct}% WR · ${b.net_pnl}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
