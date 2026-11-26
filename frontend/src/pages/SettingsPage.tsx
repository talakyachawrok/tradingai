import React, { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Save, Settings as SettingsIcon } from 'lucide-react'
import { api } from '../services/api'

interface Props {
  theme: 'dark' | 'light'
  onToggleTheme: () => void
}

export const SettingsPage: React.FC<Props> = ({ theme, onToggleTheme }) => {
  const settingsQ = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const providersQ = useQuery({ queryKey: ['providers'], queryFn: api.listProviders })
  const [form, setForm] = useState<any>(null)
  const [savedMsg, setSavedMsg] = useState<string | null>(null)

  useEffect(() => {
    if (settingsQ.data?.user_settings) {
      setForm(settingsQ.data.user_settings)
    }
  }, [settingsQ.data])

  const handleSave = async () => {
    if (!form) return
    setSavedMsg(null)
    await api.saveSettings(form)
    setSavedMsg('Settings saved to database successfully.')
    settingsQ.refetch()
  }

  const env = settingsQ.data?.environment
  const db = settingsQ.data?.database

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-terminal-border bg-terminal-panel p-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <SettingsIcon className="w-5 h-5 text-sky-400" />
          <div>
            <h2 className="text-base font-bold">System, Risk Management & Provider Settings</h2>
            <p className="text-xs text-terminal-muted">
              Secret API keys remain strictly server-side in environment variables (never exposed to browser code).
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onToggleTheme} className="px-3 py-2 rounded-lg border border-terminal-border bg-terminal-elevated text-xs font-medium">
            Theme: {theme === 'dark' ? 'Dark' : 'Light'}
          </button>
          <button onClick={handleSave} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold">
            <Save className="w-3.5 h-3.5" /> Save Settings
          </button>
        </div>
      </div>

      {savedMsg && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-xs text-emerald-300 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" /> {savedMsg}
        </div>
      )}

      {/* Environment & Provider Connection Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 text-xs">
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
          <h3 className="font-semibold uppercase text-terminal-muted">Provider & Integration Status</h3>
          <div className="space-y-2">
            {(providersQ.data || []).map((p: any) => (
              <div key={p.name} className="p-2.5 rounded border border-terminal-border bg-terminal-elevated/40">
                <div className="flex justify-between font-semibold">
                  <span>{p.name}</span>
                  <span className={p.configured ? 'text-emerald-400' : 'text-amber-400'}>
                    {p.configured ? 'Configured' : 'API Key Missing'}
                  </span>
                </div>
                <p className="text-[11px] text-terminal-muted mt-0.5">{p.notes}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
          <h3 className="font-semibold uppercase text-terminal-muted">Database, AI & News Status</h3>
          <div className="space-y-2">
            <div className="flex justify-between border-b border-terminal-border/50 pb-1.5">
              <span className="text-terminal-muted">Database Backend</span>
              <span className="font-mono">{db?.backend} ({db?.connected ? 'Connected' : 'Disconnected'})</span>
            </div>
            <div className="text-[11px] text-terminal-muted">{db?.message}</div>
            <div className="flex justify-between border-b border-terminal-border/50 pb-1.5 pt-2">
              <span className="text-terminal-muted">AI Explanation Provider</span>
              <span className="font-mono">{env?.ai_provider} ({env?.ai_key_configured ? 'Key Active' : 'Deterministic Fallback'})</span>
            </div>
            <div className="flex justify-between border-b border-terminal-border/50 pb-1.5">
              <span className="text-terminal-muted">News Calendar Provider</span>
              <span className="font-mono">{env?.news_provider} ({env?.news_configured ? 'Active' : 'Unavailable'})</span>
            </div>
            <div className="flex justify-between">
              <span className="text-terminal-muted">Stale Data Threshold</span>
              <span className="font-mono">{env?.stale_data_threshold_seconds}s</span>
            </div>
          </div>
        </div>
      </div>

      {/* Editable Risk, Indicator & Scoring Weight Configuration */}
      {form && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 text-xs">
          <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
            <h3 className="font-semibold uppercase text-terminal-muted">Risk Management Rules</h3>
            {[
              ['max_risk_per_trade_pct', 'Max Risk / Trade (%)'],
              ['max_daily_loss_pct', 'Max Daily Loss (%)'],
              ['max_daily_trades', 'Max Daily Trades'],
              ['max_consecutive_losses', 'Max Consecutive Losses'],
              ['min_risk_reward', 'Min Risk/Reward'],
              ['min_setup_score', 'Min Setup Score (0-100)'],
              ['max_open_paper_trades', 'Max Open Paper Trades'],
            ].map(([key, label]) => (
              <label key={key} className="flex items-center justify-between gap-2">
                <span className="text-terminal-muted">{label}</span>
                <input
                  type="number"
                  step="any"
                  value={form.risk[key]}
                  onChange={(e) =>
                    setForm({ ...form, risk: { ...form.risk, [key]: Number(e.target.value) } })
                  }
                  className="w-24 px-2 py-1 rounded bg-terminal-elevated border border-terminal-border font-mono text-right"
                />
              </label>
            ))}
            <label className="flex items-center justify-between pt-1">
              <span className="text-terminal-muted">Require HTF Alignment</span>
              <input
                type="checkbox"
                checked={form.risk.require_htf_alignment}
                onChange={(e) =>
                  setForm({
                    ...form,
                    risk: { ...form.risk, require_htf_alignment: e.target.checked },
                  })
                }
              />
            </label>
          </div>

          <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
            <h3 className="font-semibold uppercase text-terminal-muted">Indicator Parameters</h3>
            {[
              ['ema_fast', 'EMA Fast'],
              ['ema_medium', 'EMA Medium'],
              ['ema_slow', 'EMA Slow'],
              ['rsi_period', 'RSI Period'],
              ['rsi_overbought', 'RSI Overbought'],
              ['rsi_oversold', 'RSI Oversold'],
              ['atr_period', 'ATR Period'],
            ].map(([key, label]) => (
              <label key={key} className="flex items-center justify-between gap-2">
                <span className="text-terminal-muted">{label}</span>
                <input
                  type="number"
                  step="any"
                  value={form.indicators[key]}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      indicators: { ...form.indicators, [key]: Number(e.target.value) },
                    })
                  }
                  className="w-24 px-2 py-1 rounded bg-terminal-elevated border border-terminal-border font-mono text-right"
                />
              </label>
            ))}
          </div>

          <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
            <h3 className="font-semibold uppercase text-terminal-muted">Setup Scoring Weights</h3>
            {Object.entries(form.scoring_weights).map(([key, val]) => (
              <label key={key} className="flex items-center justify-between gap-2">
                <span className="text-terminal-muted capitalize">{key.replace(/_/g, ' ')}</span>
                <input
                  type="number"
                  step="1"
                  value={Number(val)}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      scoring_weights: { ...form.scoring_weights, [key]: Number(e.target.value) },
                    })
                  }
                  className="w-24 px-2 py-1 rounded bg-terminal-elevated border border-terminal-border font-mono text-right"
                />
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
