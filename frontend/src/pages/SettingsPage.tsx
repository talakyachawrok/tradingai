import React, { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, Bell, CheckCircle2, Loader2, Save, Settings as SettingsIcon, Volume2, XCircle } from 'lucide-react'
import { api } from '../services/api'
import type { ProviderConnectionTestResult } from '../types/trading'
import { playAlertSound, requestBrowserNotificationPermission } from '../utils/notifications'

interface Props {
  theme: 'dark' | 'light'
  onToggleTheme: () => void
}

export const SettingsPage: React.FC<Props> = ({ theme, onToggleTheme }) => {
  const settingsQ = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const providersQ = useQuery({ queryKey: ['providers'], queryFn: api.listProviders })
  const [form, setForm] = useState<any>(null)
  const [savedMsg, setSavedMsg] = useState<string | null>(null)
  const [testSymbol, setTestSymbol] = useState('XAUUSD')
  const [testingProvider, setTestingProvider] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, ProviderConnectionTestResult>>({})

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
    providersQ.refetch()
  }

  const handleTestProvider = async (providerName: string) => {
    setTestingProvider(providerName)
    try {
      const sym = providerName === 'binance_public' ? 'BTCUSD' : testSymbol
      const res = await api.testProviderConnection(providerName, sym, '1h')
      setTestResults((prev) => ({ ...prev, [providerName]: res }))
    } catch (err: any) {
      setTestResults((prev) => ({
        ...prev,
        [providerName]: {
          provider_name: providerName,
          connected: false,
          status: 'ERROR',
          message: err.message || 'Connection test failed.',
          tested_symbol: testSymbol,
          tested_timeframe: '1h',
          requires_api_key: true,
          subscription_notes: '',
        },
      }))
    } finally {
      setTestingProvider(null)
    }
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
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold uppercase text-terminal-muted">Provider & Connection Tester</h3>
            <div className="flex items-center gap-2">
              <select
                aria-label="Test Symbol"
                value={testSymbol}
                onChange={(e) => setTestSymbol(e.target.value)}
                className="px-2 py-1 rounded bg-terminal-elevated border border-terminal-border font-mono text-[11px]"
              >
                <option value="XAUUSD">XAUUSD</option>
                <option value="EURUSD">EURUSD</option>
                <option value="GBPUSD">GBPUSD</option>
                <option value="BTCUSD">BTCUSD</option>
              </select>
              {form && (
                <select
                  aria-label="Default Active Provider"
                  value={form.data_provider || 'auto'}
                  onChange={(e) => setForm({ ...form, data_provider: e.target.value })}
                  className="px-2 py-1 rounded bg-terminal-elevated border border-terminal-border text-[11px]"
                >
                  <option value="auto">Active: Auto</option>
                  <option value="twelvedata">Active: TwelveData</option>
                  <option value="alphavantage">Active: AlphaVantage</option>
                  <option value="binance_public">Active: Binance Public</option>
                  <option value="webhook_cache">Active: Webhook / CSV</option>
                </select>
              )}
            </div>
          </div>

          <div className="space-y-2.5">
            {(providersQ.data || []).map((p: any) => {
              const testRes = testResults[p.name]
              const isTesting = testingProvider === p.name
              return (
                <div key={p.name} className="p-3 rounded-lg border border-terminal-border bg-terminal-elevated/40 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{p.name}</span>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          testRes
                            ? testRes.connected
                              ? 'bg-emerald-500/15 text-emerald-400'
                              : 'bg-rose-500/15 text-rose-400'
                            : p.configured
                            ? 'bg-sky-500/15 text-sky-400'
                            : 'bg-amber-500/15 text-amber-400'
                        }`}
                      >
                        {testRes ? testRes.status : p.configured ? 'Configured' : 'API Key Missing'}
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleTestProvider(p.name)}
                      disabled={isTesting}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-[11px] font-semibold transition"
                    >
                      {isTesting ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Activity className="w-3 h-3" />
                      )}
                      {isTesting ? 'Testing...' : 'Test API Connection'}
                    </button>
                  </div>

                  <p className="text-[11px] text-terminal-muted">{p.notes}</p>

                  {testRes && (
                    <div
                      className={`p-2 rounded border text-[11px] space-y-0.5 ${
                        testRes.connected
                          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                          : 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 font-semibold">
                        {testRes.connected ? (
                          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                        ) : (
                          <XCircle className="w-3.5 h-3.5 shrink-0" />
                        )}
                        <span>{testRes.message}</span>
                      </div>
                      {testRes.connected && (
                        <div className="font-mono text-[10px] opacity-90">
                          {testRes.tested_symbol} ({testRes.tested_timeframe}) · Price: {testRes.sample_price} · Updated: {testRes.sample_timestamp} · {testRes.latency_ms}ms
                        </div>
                      )}
                      {testRes.subscription_notes && (
                        <div className="text-[10px] opacity-85">{testRes.subscription_notes}</div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
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

          {/* Alert Settings & Confirmation Rules */}
          {form.alerts && (
            <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3 lg:col-span-3">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-terminal-border pb-2">
                <div className="flex items-center gap-2 font-semibold uppercase text-sky-400">
                  <Bell className="w-4 h-4" />
                  Alert Settings & Signal Confirmation Rules
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={async () => {
                      const perm = await requestBrowserNotificationPermission()
                      setSavedMsg(`Browser notification permission: ${perm}`)
                    }}
                    className="px-2.5 py-1 rounded border border-terminal-border bg-terminal-elevated hover:border-sky-500/40"
                  >
                    Enable Browser Alerts
                  </button>
                  <button
                    type="button"
                    onClick={() => playAlertSound()}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-terminal-border bg-terminal-elevated hover:border-sky-500/40"
                  >
                    <Volume2 className="w-3.5 h-3.5" /> Test Sound
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                <div className="space-y-2.5">
                  <div className="font-semibold text-terminal-muted uppercase">Alert Channels & Frequency</div>
                  {[
                    ['enable_buy_alerts', 'Enable BUY Signal Alerts'],
                    ['enable_sell_alerts', 'Enable SELL Signal Alerts'],
                    ['browser_notifications_enabled', 'Browser Desktop Notifications'],
                    ['sound_enabled', 'Alert Sound Effects'],
                  ].map(([k, lbl]) => (
                    <label key={k} className="flex items-center justify-between">
                      <span>{lbl}</span>
                      <input
                        type="checkbox"
                        checked={Boolean(form.alerts[k])}
                        onChange={(e) =>
                          setForm({ ...form, alerts: { ...form.alerts, [k]: e.target.checked } })
                        }
                      />
                    </label>
                  ))}
                  {[
                    ['alert_cooldown_minutes', 'Alert Cooldown (minutes)'],
                    ['signal_expiry_candles', 'Signal Expiry (candles)'],
                    ['signal_expiry_minutes', 'Signal Expiry (minutes)'],
                  ].map(([k, lbl]) => (
                    <label key={k} className="flex items-center justify-between gap-2">
                      <span className="text-terminal-muted">{lbl}</span>
                      <input
                        type="number"
                        value={form.alerts[k]}
                        onChange={(e) =>
                          setForm({ ...form, alerts: { ...form.alerts, [k]: Number(e.target.value) } })
                        }
                        className="w-24 px-2 py-1 rounded bg-terminal-elevated border border-terminal-border font-mono text-right"
                      />
                    </label>
                  ))}
                </div>

                {form.confirmations && (
                  <div className="space-y-2">
                    <div className="font-semibold text-terminal-muted uppercase">Required Confirmation Rules</div>
                    {[
                      ['require_candle_close', 'Candle Close Confirmation'],
                      ['require_market_structure', 'Market Structure Alignment'],
                      ['require_candlestick_pattern', 'Candlestick Pattern Detected'],
                      ['require_trend_alignment', 'Trend Alignment'],
                      ['require_htf_alignment', 'Higher Timeframe Agreement'],
                      ['require_rsi_confirmation', 'RSI Confirmation'],
                      ['require_ema_alignment', 'Full EMA (20/50/200) Stack'],
                      ['require_liquidity_condition', 'Liquidity / S&R Reaction'],
                      ['require_min_risk_reward', 'Minimum Risk/Reward Threshold'],
                    ].map(([k, lbl]) => (
                      <label key={k} className="flex items-center justify-between">
                        <span>{lbl}</span>
                        <input
                          type="checkbox"
                          checked={Boolean(form.confirmations[k])}
                          onChange={(e) =>
                            setForm({
                              ...form,
                              confirmations: { ...form.confirmations, [k]: e.target.checked },
                            })
                          }
                        />
                      </label>
                    ))}
                  </div>
                )}

                <div className="space-y-3">
                  <div className="font-semibold text-terminal-muted uppercase">Monitored Symbols & Timeframes</div>
                  <div className="space-y-1.5">
                    <div className="text-terminal-muted">Selected Symbols</div>
                    <div className="flex flex-wrap gap-2">
                      {['XAUUSD', 'EURUSD', 'GBPUSD', 'BTCUSD'].map((sym) => {
                        const checked = (form.alerts.selected_symbols || []).includes(sym)
                        return (
                          <label key={sym} className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-terminal-border bg-terminal-elevated">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                const cur: string[] = form.alerts.selected_symbols || []
                                const next = e.target.checked ? [...cur, sym] : cur.filter((s) => s !== sym)
                                setForm({ ...form, alerts: { ...form.alerts, selected_symbols: next } })
                              }}
                            />
                            <span className="font-mono">{sym}</span>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <div className="text-terminal-muted">Selected Timeframes</div>
                    <div className="flex flex-wrap gap-2">
                      {['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d'].map((tf) => {
                        const checked = (form.alerts.selected_timeframes || []).includes(tf)
                        return (
                          <label key={tf} className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-terminal-border bg-terminal-elevated">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                const cur: string[] = form.alerts.selected_timeframes || []
                                const next = e.target.checked ? [...cur, tf] : cur.filter((t) => t !== tf)
                                setForm({ ...form, alerts: { ...form.alerts, selected_timeframes: next } })
                              }}
                            />
                            <span className="font-mono">{tf}</span>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

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
