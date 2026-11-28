import React, { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertCircle,
  Brain,
  Database,
  Globe,
  Play,
  Plus,
  RefreshCw,
  Upload,
} from 'lucide-react'
import { CandlestickChart } from '../charts/CandlestickChart'
import { AITradeSignalCard } from '../components/AITradeSignalCard'
import { AnalysisReportCard } from '../components/AnalysisReportCard'
import { api } from '../services/api'
import { playAlertSound, showBrowserNotification } from '../utils/notifications'
import type {
  InstrumentSpec,
  Timeframe,
  TradeAnalysisReport,
} from '../types/trading'

const TIMEFRAMES: Array<{ value: Timeframe; label: string }> = [
  { value: '1m', label: '1m' },
  { value: '3m', label: '3m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '30m', label: '30m' },
  { value: '1h', label: '1H' },
  { value: '4h', label: '4H' },
  { value: '1d', label: 'Daily' },
]

interface Props {
  theme: 'dark' | 'light'
  allowDemo: boolean
  setAllowDemo: (v: boolean) => void
  onNotificationRefresh: () => void
}

export const DashboardPage: React.FC<Props> = ({
  theme,
  allowDemo,
  setAllowDemo,
  onNotificationRefresh,
}) => {
  const [symbol, setSymbol] = useState('XAUUSD')
  const [timeframe, setTimeframe] = useState<Timeframe>('1h')
  const [provider, setProvider] = useState('auto')
  const [analysis, setAnalysis] = useState<TradeAnalysisReport | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const [paperBusy, setPaperBusy] = useState(false)
  const [paperMsg, setPaperMsg] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [showDetailedReport, setShowDetailedReport] = useState(false)
  const [showAddSymbol, setShowAddSymbol] = useState(false)
  const [newSymbol, setNewSymbol] = useState('')
  const [newName, setNewName] = useState('')
  const [newAssetClass, setNewAssetClass] = useState('forex')
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const queryClient = useQueryClient()

  const instrumentsQ = useQuery({
    queryKey: ['instruments'],
    queryFn: api.listInstruments,
  })

  const settingsQ = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
  })

  useEffect(() => {
    const savedProvider = settingsQ.data?.user_settings?.data_provider
    if (savedProvider && provider === 'auto') {
      setProvider(savedProvider)
    }
  }, [settingsQ.data?.user_settings?.data_provider])

  const marketQ = useQuery({
    queryKey: ['ohlcv', symbol, timeframe, allowDemo, provider],
    queryFn: () => api.getOhlcv(symbol, timeframe, allowDemo, provider, false),
    refetchInterval: 30000,
  })

  const newsQ = useQuery({
    queryKey: ['sessions-news', symbol],
    queryFn: () => api.getSessionsNews(symbol),
    refetchInterval: 60000,
  })

  const handleRefresh = async () => {
    setRefreshing(true)
    setAnalyzeError(null)
    try {
      const fresh = await api.getOhlcv(symbol, timeframe, allowDemo, provider, true)
      queryClient.setQueryData(['ohlcv', symbol, timeframe, allowDemo, provider], fresh)
    } catch (err: any) {
      setAnalyzeError(err.message || 'Failed to refresh market data.')
    } finally {
      setRefreshing(false)
    }
  }

  const activeSpec: InstrumentSpec | undefined = instrumentsQ.data?.find(
    (i) => i.symbol === symbol
  )
  const decimals = activeSpec?.decimals ?? (symbol.includes('JPY') ? 3 : symbol === 'XAUUSD' || symbol === 'BTCUSD' ? 2 : 5)

  const handleAnalyze = async () => {
    setAnalyzing(true)
    setAnalyzeError(null)
    setPaperMsg(null)
    try {
      const report = await api.runAnalysis(symbol, timeframe, allowDemo, provider)
      setAnalysis(report)
      onNotificationRefresh()

      const alertsCfg = settingsQ.data?.user_settings?.alerts
      const isQualifying =
        report.signal_status === 'BUY SIGNAL' || report.signal_status === 'SELL SIGNAL'
      if (isQualifying) {
        const allowDir =
          (report.signal_status === 'BUY SIGNAL' && (alertsCfg?.enable_buy_alerts ?? true)) ||
          (report.signal_status === 'SELL SIGNAL' && (alertsCfg?.enable_sell_alerts ?? true))
        if (allowDir) {
          if (alertsCfg?.sound_enabled ?? true) {
            playAlertSound()
          }
          if (alertsCfg?.browser_notifications_enabled ?? true) {
            showBrowserNotification(
              `AI TRADING ANALYZER: ${report.signal_status} — ${report.symbol}`,
              `Timeframe: ${report.timeframe} | Entry: ${report.trade_levels.entry_price ?? 'N/A'} | SL: ${report.trade_levels.stop_loss ?? 'N/A'} | TP1: ${report.trade_levels.take_profit_1 ?? 'N/A'}`
            )
          }
        }
      }
    } catch (err: any) {
      setAnalyzeError(err.message || 'Analysis failed.')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setAnalyzeError(null)
    try {
      await api.uploadCsv(symbol, timeframe, file)
      await marketQ.refetch()
    } catch (err: any) {
      setAnalyzeError(err.message)
    } finally {
      e.target.value = ''
    }
  }

  const handleAddSymbol = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newSymbol.trim()) return
    await api.addInstrument({
      symbol: newSymbol.trim().toUpperCase(),
      display_name: newName.trim() || newSymbol.trim().toUpperCase(),
      asset_class: newAssetClass,
      base_currency: newSymbol.trim().toUpperCase().slice(0, 3),
      quote_currency: 'USD',
      decimals: newAssetClass === 'forex' ? 5 : 2,
      min_lot: 0.01,
      lot_step: 0.01,
      is_custom: true,
    })
    setSymbol(newSymbol.trim().toUpperCase())
    setNewSymbol('')
    setNewName('')
    setShowAddSymbol(false)
    instrumentsQ.refetch()
  }

  const handleSendToPaper = async (report: TradeAnalysisReport) => {
    if (!report.trade_levels.stop_loss || !report.trade_levels.take_profit_1) return
    setPaperBusy(true)
    setPaperMsg(null)
    try {
      await api.openPaperOrder({
        symbol: report.symbol,
        direction: report.final_decision === 'BUY SETUP' ? 'BUY' : 'SELL',
        entry_price: report.trade_levels.entry_price,
        stop_loss: report.trade_levels.stop_loss,
        take_profit: report.trade_levels.take_profit_1,
        risk_percentage: 1.0,
        analysis_id: report.analysis_id,
        setup_score: report.setup_score.total_score,
        is_demo_data: report.is_demo,
        notes: `Executed from analysis ${report.analysis_id.slice(0, 8)}`,
      })
      setPaperMsg('Simulated paper trade opened successfully. Review in Paper Trading tab.')
      onNotificationRefresh()
    } catch (err: any) {
      setPaperMsg(`Paper trade blocked: ${err.message}`)
    } finally {
      setPaperBusy(false)
    }
  }

  const overview = marketQ.data?.overview
  const indicators = marketQ.data?.indicators
  const unavailableTfs = marketQ.data?.unavailable_timeframes || []

  const statusTone =
    overview?.connection_status === 'LIVE'
      ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
      : overview?.connection_status === 'DEMO_MODE'
      ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
      : overview?.connection_status === 'WEBHOOK_CACHE'
      ? 'bg-sky-500/15 text-sky-400 border-sky-500/30'
      : 'bg-rose-500/15 text-rose-400 border-rose-500/30'

  return (
    <div className="space-y-5">
      {/* Controls Bar */}
      <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Market Selector */}
          <div className="flex items-center gap-1">
            <select
              aria-label="Market Selector"
              value={symbol}
              onChange={(e) => {
                setSymbol(e.target.value)
                setAnalysis(null)
              }}
              className="px-3 py-2 rounded-lg bg-terminal-elevated border border-terminal-border text-sm font-semibold"
            >
              {(instrumentsQ.data || [{ symbol: 'XAUUSD', display_name: 'Gold / USD' }]).map((inst) => (
                <option key={inst.symbol} value={inst.symbol}>
                  {inst.symbol} — {inst.display_name}
                </option>
              ))}
            </select>
            <button
              onClick={() => setShowAddSymbol((v) => !v)}
              title="Add configurable symbol"
              className="p-2 rounded-lg border border-terminal-border bg-terminal-elevated hover:border-sky-500/50 text-terminal-muted hover:text-terminal-text transition"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>

          {/* Timeframe Selector */}
          <div className="flex flex-wrap items-center gap-1 bg-terminal-elevated p-1 rounded-lg border border-terminal-border">
            {TIMEFRAMES.map((tf) => {
              const isUnavailable = unavailableTfs.includes(tf.value)
              return (
                <button
                  key={tf.value}
                  onClick={() => {
                    setTimeframe(tf.value)
                    setAnalysis(null)
                  }}
                  title={isUnavailable ? `${tf.label} unavailable on active provider` : tf.label}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition ${
                    timeframe === tf.value
                      ? 'bg-sky-600 text-white'
                      : isUnavailable
                      ? 'text-terminal-muted/40 line-through'
                      : 'text-terminal-muted hover:text-terminal-text'
                  }`}
                >
                  {tf.label}
                </button>
              )
            })}
          </div>

          {/* Provider Selector */}
          <select
            aria-label="Data Provider"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="px-2.5 py-2 rounded-lg bg-terminal-elevated border border-terminal-border text-xs"
          >
            <option value="auto">Provider: Auto</option>
            <option value="binance_public">Binance Public (BTC)</option>
            <option value="twelvedata">TwelveData</option>
            <option value="alphavantage">AlphaVantage</option>
            <option value="webhook_cache">Webhook / CSV Cache</option>
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-terminal-border bg-terminal-elevated text-xs cursor-pointer">
            <input
              type="checkbox"
              checked={allowDemo}
              onChange={(e) => setAllowDemo(e.target.checked)}
              className="rounded accent-amber-500"
            />
            <span>Demo Historical Mode</span>
          </label>

          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleCsvUpload}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-terminal-border bg-terminal-elevated hover:border-sky-500/40 text-xs font-medium transition"
          >
            <Upload className="w-3.5 h-3.5" />
            Upload OHLC CSV
          </button>

          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-terminal-border bg-terminal-elevated hover:border-sky-500/40 text-terminal-muted hover:text-terminal-text text-xs font-medium transition"
            title="Force refresh live market data (bypasses cache)"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${marketQ.isFetching || refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>

          <button
            onClick={handleAnalyze}
            disabled={analyzing || !marketQ.data?.candles?.length}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-45 text-white text-xs font-bold tracking-wide transition shadow-sm"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            {analyzing ? 'ANALYZING...' : 'ANALYZE MARKET'}
          </button>
        </div>
      </div>

      {/* Custom Instrument Drawer */}
      {showAddSymbol && (
        <form
          onSubmit={handleAddSymbol}
          className="rounded-xl border border-sky-500/30 bg-terminal-panel p-4 flex flex-wrap items-end gap-3 text-xs"
        >
          <label className="space-y-1">
            <span className="text-terminal-muted">Symbol (e.g. USDJPY, ETHUSD)</span>
            <input
              required
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              placeholder="USDJPY"
              className="block px-3 py-1.5 rounded bg-terminal-elevated border border-terminal-border font-mono"
            />
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Display Name</span>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="US Dollar / Japanese Yen"
              className="block px-3 py-1.5 rounded bg-terminal-elevated border border-terminal-border"
            />
          </label>
          <label className="space-y-1">
            <span className="text-terminal-muted">Asset Class</span>
            <select
              value={newAssetClass}
              onChange={(e) => setNewAssetClass(e.target.value)}
              className="block px-3 py-1.5 rounded bg-terminal-elevated border border-terminal-border"
            >
              <option value="forex">Forex</option>
              <option value="crypto">Crypto</option>
              <option value="metals">Metals</option>
              <option value="indices">Indices</option>
            </select>
          </label>
          <button type="submit" className="px-4 py-2 rounded-lg bg-sky-600 text-white font-semibold">
            Save Instrument
          </button>
        </form>
      )}

      {/* Market Overview Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-3">
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
          <div className="text-[11px] text-terminal-muted">Market</div>
          <div className="text-sm font-bold mt-0.5">{overview?.symbol || symbol}</div>
          <div className="text-[11px] text-terminal-muted truncate">{overview?.display_name}</div>
        </div>
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
          <div className="text-[11px] text-terminal-muted">Current Price</div>
          <div className="text-sm font-bold font-mono tabular-nums mt-0.5">
            {overview?.current_price != null ? overview.current_price.toFixed(decimals) : 'N/A'}
          </div>
          <div
            className={`text-[11px] font-mono tabular-nums ${
              (overview?.price_change || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {overview?.price_change != null
              ? `${overview.price_change >= 0 ? '+' : ''}${overview.price_change.toFixed(decimals)} (${overview.price_change_pct?.toFixed(2)}%)`
              : '—'}
          </div>
        </div>
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
          <div className="text-[11px] text-terminal-muted">Timeframe & Candles</div>
          <div className="text-sm font-bold mt-0.5">{timeframe.toUpperCase()}</div>
          <div className="text-[11px] text-terminal-muted">
            {marketQ.data?.integrity.valid_count ?? 0} candles
            {marketQ.data?.cache_hit ? ' (cached)' : ''}
          </div>
        </div>
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
          <div className="text-[11px] text-terminal-muted">Market Session</div>
          <div className="text-xs font-semibold mt-0.5">{overview?.market_session || '—'}</div>
          <div className="text-[11px] text-terminal-muted">{overview?.session_status}</div>
        </div>
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
          <div className="text-[11px] text-terminal-muted">Data Source</div>
          <div className="text-xs font-semibold mt-0.5">{overview?.data_source || 'none'}</div>
          <span className={`inline-block mt-1 px-1.5 py-0.5 rounded border text-[10px] font-bold ${statusTone}`}>
            {overview?.connection_status || 'DATA_UNAVAILABLE'}
          </span>
        </div>
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
          <div className="text-[11px] text-terminal-muted">Last Update (UTC)</div>
          <div className="text-xs font-mono mt-0.5">
            {overview?.last_data_update ? new Date(overview.last_data_update).toISOString().slice(0, 16).replace('T', ' ') : 'N/A'}
          </div>
          <div className="text-[11px] text-terminal-muted">{overview?.market_status}</div>
        </div>
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
          <div className="text-[11px] text-terminal-muted">How much is the market moving?</div>
          <div className="text-xs font-semibold mt-0.5">{overview?.volatility_condition || 'Unavailable'}</div>
          <div className="text-[11px] text-terminal-muted">
            Momentum (RSI): {indicators?.rsi_14 ?? 'N/A'}
          </div>
        </div>
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
          <div className="text-[11px] text-terminal-muted">Short-Term Trend</div>
          <div className="text-xs font-semibold mt-0.5 truncate">{indicators?.ema_alignment?.replace(/_/g, ' ') || 'unavailable'}</div>
          <div className="text-[11px] text-terminal-muted truncate">{indicators?.macd_condition || '—'}</div>
        </div>
      </div>

      {/* Banners for errors / demo / paper feedback */}
      {overview?.is_demo && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-300 flex items-center gap-2">
          <Database className="w-4 h-4 shrink-0" />
          <span>
            <strong>DEMO MODE ACTIVE:</strong> Static historical sample dataset is displayed for engine inspection. Do not treat demo prices as live market quotes.
          </span>
        </div>
      )}

      {(analyzeError || paperMsg) && (
        <div
          className={`rounded-lg border px-4 py-2.5 text-xs flex items-center gap-2 ${
            analyzeError || paperMsg?.startsWith('Paper trade blocked')
              ? 'border-rose-500/30 bg-rose-500/10 text-rose-300'
              : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
          }`}
        >
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{analyzeError || paperMsg}</span>
        </div>
      )}

      {/* Prominent Beginner-Friendly AI TRADE SIGNAL Section */}
      <AITradeSignalCard
        report={analysis}
        scanning={analyzing}
        dataUnavailable={!marketQ.data?.candles?.length}
        symbol={symbol}
        timeframe={timeframe}
        decimals={decimals}
        onSendToPaper={handleSendToPaper}
        paperSubmitting={paperBusy}
      />

      {/* Main Chart + Side Indicator & Session Panel */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-5">
        <div className="xl:col-span-3">
          {marketQ.isLoading ? (
            <div className="h-[460px] rounded-xl border border-terminal-border bg-terminal-panel flex items-center justify-center text-sm text-terminal-muted">
              Loading market data...
            </div>
          ) : (
            <CandlestickChart
              candles={marketQ.data?.candles || []}
              overview={overview}
              overlays={marketQ.data?.overlays}
              analysis={analysis}
              theme={theme}
              decimals={decimals}
            />
          )}
        </div>

        {/* Right Telemetry Panel */}
        <div className="space-y-4">
          <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-terminal-muted">
              <Activity className="w-4 h-4 text-sky-400" />
              Indicator Snapshot
            </div>
            <div className="space-y-2 text-xs">
              {[
                ['EMA 20', indicators?.ema_20?.toFixed(decimals) ?? 'N/A'],
                ['EMA 50', indicators?.ema_50?.toFixed(decimals) ?? 'N/A'],
                ['EMA 200', indicators?.ema_200?.toFixed(decimals) ?? 'N/A'],
                ['RSI (14)', indicators?.rsi_14 ?? 'N/A'],
                ['ATR (14)', indicators?.atr_14?.toFixed(decimals) ?? 'N/A'],
                ['MACD Hist', indicators?.macd_histogram?.toFixed(decimals) ?? 'N/A'],
                ['Volume Ratio', indicators?.volume_ratio != null ? `${indicators.volume_ratio}x` : 'N/A'],
              ].map(([k, v]) => (
                <div key={String(k)} className="flex justify-between border-b border-terminal-border/50 pb-1">
                  <span className="text-terminal-muted">{k}</span>
                  <span className="font-mono font-medium tabular-nums">{v}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-2.5">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-terminal-muted">
              <Globe className="w-4 h-4 text-emerald-400" />
              Sessions & News Filter
            </div>
            <div className="grid grid-cols-2 gap-1.5 text-[11px]">
              {(newsQ.data?.sessions || []).map((s: any) => (
                <div
                  key={s.name}
                  className={`px-2 py-1.5 rounded border ${
                    s.active
                      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                      : 'border-terminal-border text-terminal-muted'
                  }`}
                >
                  <div className="font-semibold">{s.name}</div>
                  <div className="text-[10px] opacity-80">{s.utc_hours}</div>
                </div>
              ))}
            </div>
            <div className="pt-1 text-[11px] text-terminal-muted">
              News Calendar:{' '}
              <span className="font-semibold text-terminal-text">
                {newsQ.data?.news_status || 'UNAVAILABLE'}
              </span>
              <p className="mt-0.5 leading-snug">{newsQ.data?.news_message}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Expandable Advanced Quantitative Report & Position Sizing */}
      {analysis ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <button
              onClick={() => setShowDetailedReport((v) => !v)}
              className="px-4 py-2 rounded-lg border border-terminal-border bg-terminal-panel hover:border-sky-500/40 text-xs font-semibold transition"
            >
              {showDetailedReport
                ? 'Hide Advanced Technical Report & Position Size Calculator'
                : 'Open Advanced Technical Report & Position Size Calculator'}
            </button>
          </div>
          {showDetailedReport && (
            <AnalysisReportCard
              report={analysis}
              decimals={decimals}
              onSendToPaper={handleSendToPaper}
              paperSubmitting={paperBusy}
            />
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-terminal-border bg-terminal-panel/50 p-6 text-center space-y-2">
          <Brain className="w-7 h-7 text-sky-400 mx-auto opacity-80" />
          <h3 className="text-sm font-semibold">Ready for Quantitative & AI Trade Evaluation</h3>
          <p className="text-xs text-terminal-muted max-w-xl mx-auto">
            Click <strong>ANALYZE MARKET</strong> once valid market data is loaded to scan for qualified BUY/SELL setups, beginner-friendly explanations, entry/SL/TP levels, and multi-timeframe confirmation.
          </p>
        </div>
      )}
    </div>
  )
}
