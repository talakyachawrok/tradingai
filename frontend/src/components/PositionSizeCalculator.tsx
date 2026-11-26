import React, { useEffect, useState } from 'react'
import { Calculator } from 'lucide-react'
import { api } from '../services/api'

interface Props {
  symbol: string
  defaultEntry?: number
  defaultStopLoss?: number
}

export const PositionSizeCalculator: React.FC<Props> = ({
  symbol,
  defaultEntry,
  defaultStopLoss,
}) => {
  const [balance, setBalance] = useState('10000')
  const [riskPct, setRiskPct] = useState('1.0')
  const [entry, setEntry] = useState(defaultEntry ? String(defaultEntry) : '')
  const [sl, setSl] = useState(defaultStopLoss ? String(defaultStopLoss) : '')
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (defaultEntry) setEntry(String(defaultEntry))
    if (defaultStopLoss) setSl(String(defaultStopLoss))
  }, [defaultEntry, defaultStopLoss])

  const handleCalculate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      const res = await api.computePositionSize({
        symbol,
        account_balance: Number(balance),
        risk_percentage: Number(riskPct),
        entry_price: Number(entry),
        stop_loss: Number(sl),
      })
      setResult(res)
    } catch (err: any) {
      setError(err.message)
    }
  }

  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-elevated/40 p-4 space-y-3">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-terminal-muted">
        <Calculator className="w-4 h-4 text-sky-400" />
        Position Size Calculator ({symbol})
      </div>
      <form onSubmit={handleCalculate} className="grid grid-cols-2 gap-2.5 text-xs">
        <label className="space-y-1">
          <span className="text-terminal-muted">Account Balance ($)</span>
          <input
            type="number"
            step="any"
            required
            value={balance}
            onChange={(e) => setBalance(e.target.value)}
            className="w-full px-2.5 py-1.5 rounded bg-terminal-bg border border-terminal-border font-mono"
          />
        </label>
        <label className="space-y-1">
          <span className="text-terminal-muted">Risk (%)</span>
          <input
            type="number"
            step="0.1"
            required
            value={riskPct}
            onChange={(e) => setRiskPct(e.target.value)}
            className="w-full px-2.5 py-1.5 rounded bg-terminal-bg border border-terminal-border font-mono"
          />
        </label>
        <label className="space-y-1">
          <span className="text-terminal-muted">Entry Price</span>
          <input
            type="number"
            step="any"
            required
            value={entry}
            onChange={(e) => setEntry(e.target.value)}
            className="w-full px-2.5 py-1.5 rounded bg-terminal-bg border border-terminal-border font-mono"
          />
        </label>
        <label className="space-y-1">
          <span className="text-terminal-muted">Stop Loss</span>
          <input
            type="number"
            step="any"
            required
            value={sl}
            onChange={(e) => setSl(e.target.value)}
            className="w-full px-2.5 py-1.5 rounded bg-terminal-bg border border-terminal-border font-mono"
          />
        </label>
        <button
          type="submit"
          className="col-span-2 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold transition"
        >
          Calculate Position Size
        </button>
      </form>

      {error && <p className="text-xs text-rose-400">{error}</p>}

      {result && (
        <div className="rounded border border-terminal-border bg-terminal-panel p-3 text-xs space-y-1">
          {result.specs_available ? (
            <>
              <div className="flex justify-between">
                <span className="text-terminal-muted">Recommended Lot Size:</span>
                <span className="font-mono font-bold text-emerald-400">
                  {result.recommended_lots} lots ({result.recommended_units} units)
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-terminal-muted">Capital at Risk:</span>
                <span className="font-mono">${result.risk_amount}</span>
              </div>
              <p className="text-[11px] text-terminal-muted pt-1">{result.details}</p>
            </>
          ) : (
            <p className="text-amber-400 font-medium">{result.warning}</p>
          )}
          {result.warning && result.specs_available && (
            <p className="text-[11px] text-amber-400 pt-1">{result.warning}</p>
          )}
        </div>
      )}
    </div>
  )
}
