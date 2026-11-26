import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BrainCircuit, Play } from 'lucide-react'
import { api } from '../services/api'
import type { Timeframe } from '../types/trading'

interface Props {
  allowDemo: boolean
}

export const ProbabilityLabPage: React.FC<Props> = ({ allowDemo }) => {
  const [symbol, setSymbol] = useState('BTCUSD')
  const [timeframe, setTimeframe] = useState<Timeframe>('1h')
  const [modelType, setModelType] = useState('logistic_regression')
  const [horizon, setHorizon] = useState('24')
  const [training, setTraining] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const statusQ = useQuery({ queryKey: ['ml-status'], queryFn: api.getMlStatus })

  const handleTrain = async (e: React.FormEvent) => {
    e.preventDefault()
    setTraining(true)
    setError(null)
    try {
      await api.trainMl({
        symbol,
        timeframe,
        model_type: modelType,
        horizon_bars: Number(horizon),
        allow_demo: allowDemo,
      })
      await statusQ.refetch()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setTraining(false)
    }
  }

  const runtime = statusQ.data?.current_runtime

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-terminal-border bg-terminal-panel p-5 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <BrainCircuit className="w-5 h-5 text-sky-400" />
            <div>
              <h2 className="text-base font-bold">ML Probability Estimation Lab</h2>
              <p className="text-xs text-terminal-muted">
                Separate from the 0–100 Setup Score. Estimates TP1-before-SL probability using strictly chronological splits and walk-forward validation.
              </p>
            </div>
          </div>
          <span
            className={`px-3 py-1 rounded-full text-xs font-bold ${
              runtime?.validated
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
            }`}
          >
            {runtime?.status || 'PROBABILITY MODEL NOT YET VALIDATED'}
          </span>
        </div>

        <form onSubmit={handleTrain} className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
          <label className="space-y-1">
            <span className="text-terminal-muted">Symbol</span>
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-semibold">
              <option value="BTCUSD">BTCUSD</option>
              <option value="XAUUSD">XAUUSD</option>
              <option value="EURUSD">EURUSD</option>
              <option value="GBPUSD">GBPUSD</option>
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Timeframe</span>
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe)} className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border">
              {['15m', '1h', '4h', '1d'].map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Model Family</span>
            <select value={modelType} onChange={(e) => setModelType(e.target.value)} className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border">
              <option value="logistic_regression">Logistic Regression (Baseline)</option>
              <option value="random_forest">Random Forest</option>
              <option value="gradient_boosting">Gradient Boosting</option>
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Horizon (Candles)</span>
            <input type="number" value={horizon} onChange={(e) => setHorizon(e.target.value)} className="w-full px-2.5 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
          </label>
          <div className="flex items-end">
            <button type="submit" disabled={training} className="w-full py-2 px-3 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold flex items-center justify-center gap-1.5">
              <Play className="w-3.5 h-3.5 fill-current" />
              {training ? 'Training...' : 'Train & Validate'}
            </button>
          </div>
        </form>
        {error && <p className="text-xs text-rose-400">{error}</p>}
      </div>

      {runtime?.validated && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 text-xs">
          <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
            <h4 className="font-semibold uppercase text-terminal-muted">Chronological Test Set Metrics</h4>
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(runtime.test_metrics || {}).map(([k, v]) => (
                <div key={k} className="p-2.5 rounded bg-terminal-elevated border border-terminal-border">
                  <div className="text-terminal-muted uppercase text-[10px]">{k}</div>
                  <div className="text-sm font-bold font-mono mt-0.5">{String(v ?? 'N/A')}</div>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-terminal-muted">{runtime.leakage_note}</p>
            <div className="text-[11px]">
              Walk-Forward Fold Accuracies:{' '}
              <span className="font-mono text-sky-400">
                {(runtime.walk_forward_fold_accuracies || []).join(' | ') || 'N/A'}
              </span>
            </div>
          </div>

          <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
            <h4 className="font-semibold uppercase text-terminal-muted">Calibration & Regime Breakdown</h4>
            <div className="space-y-1.5">
              {(runtime.calibration || []).map((c: any, idx: number) => (
                <div key={idx} className="flex justify-between font-mono border-b border-terminal-border/40 pb-1">
                  <span>Predicted Prob: {(c.predicted_mean * 100).toFixed(1)}%</span>
                  <span>Empirical Freq: {(c.empirical_freq * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
            <div className="pt-2 space-y-1.5">
              {Object.entries(runtime.by_regime || {}).map(([reg, stats]: [string, any]) => (
                <div key={reg} className="flex justify-between">
                  <span className="font-semibold">{reg}</span>
                  <span className="font-mono">
                    {stats.samples} samples · Acc {stats.accuracy} · WinRate {stats.positive_rate}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
