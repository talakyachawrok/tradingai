import React, { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Brain,
  Database,
  Globe,
  Loader2,
  Play,
  Plus,
  Radio,
  RefreshCw,
  RotateCcw,
  Upload,
} from 'lucide-react'
import { CandlestickChart } from '../charts/CandlestickChart'
import { AITradeSignalCard } from '../components/AITradeSignalCard'
import { AnalysisReportCard } from '../components/AnalysisReportCard'
import { MarketSelector } from '../components/MarketSelector'
import { useAnalyzer } from '../context/AnalyzerContext'
import { api } from '../services/api'
import type { InstrumentSpec, Timeframe, TradeAnalysisReport } from '../types/trading'

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
  onNotificationRefresh: () => void
}

export const DashboardPage: React.FC<Props> = ({ theme, onNotificationRefresh }) => {
  const {
    symbol,
    category,
    timeframe,
    provider,
    candleLimit,
    allowDemo,
    autoUpdateEnabled,
    pollingIntervalSec,
    candleCloseOnlyReeval,
    chartSettings,
    favorites,
    analysis,
    marketData,
    isLoadingMarket,
    isUpdatingMarket,
    analyzing,
    analyzeError,
    connectionError,
    consecutiveErrors,
    lastUpdatedAt,
    setSymbol,
    setCategory,
    setTimeframe,
    setProvider,
    setCandleLimit,
    setAllowDemo,
    setAutoUpdateEnabled,
    setPollingIntervalSec,
    setCandleCloseOnlyReeval,
    setChartSettings,
    toggleFavorite,
    runManualAnalysis,
    refreshMarketData,
    resetAnalyzer,
  } = useAnalyzer()

  const [paperBusy, setPaperBusy] = useState(false)
  const [paperMsg, setPaperMsg] = useState<string | null>(null)
  const [csvError, setCsvError] = useState<string | null>(null)
  const [showDetailedReport, setShowDetailedReport] = useState(false)
  const [showAddSymbol, setShowAddSymbol] = useState(false)
  const [newSymbol, setNewSymbol] = useState('')
  const [newName, setNewName] = useState('')
  const [newAssetClass, setNewAssetClass] = useState('forex')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const instrumentsQ = useQuery({
    queryKey: ['instruments'],
    queryFn: api.listInstruments,
    staleTime: 60000,
  })

  const providersQ = useQuery({
    queryKey: ['providers'],
    queryFn: api.listProviders,
    staleTime: 60000,
  })

  const newsQ = useQuery({
    queryKey: ['sessions-news', symbol],
    queryFn: () => api.getSessionsNews(symbol),
    refetchInterval: 60000,
  })

  const activeSpec: InstrumentSpec | undefined = instrumentsQ.data?.find(
    (i) => i.symbol === symbol
  )
  const decimals =
    activeSpec?.decimals ??
    (symbol.includes('JPY') ? 3 : symbol === 'XAUUSD' || symbol === 'BTCUSD' ? 2 : 5)

  const handleCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setCsvError(null)
    try {
      await api.uploadCsv(symbol, timeframe, file)
      await refreshMarketData()
    } catch (err: any) {
      setCsvError(err.message)
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

  const overview = marketData?.overview
  const indicators = marketData?.indicators
  const unavailableTfs = marketData?.unavailable_timeframes || []
  const isStaleData = Boolean(marketData?.integrity?.is_stale && !overview?.is_demo)

  const activeProviderCap =
    provider !== 'auto'
      ? (providersQ.data || []).find((p) => p.name === provider)
      : undefined
  const providerUnsupportedSymbol =
    activeProviderCap &&
    activeProviderCap.supported_symbols.length > 0 &&
    !activeProviderCap.supported_symbols.includes(symbol)

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
      <div className="rounded-xl border border-terminal-border bg-terminal-panel p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Searchable Categorized Market Selector */}
            <div className="flex items-center gap-1">
              <MarketSelector
                instruments={instrumentsQ.data || []}
                providers={providersQ.data || []}
                selectedSymbol={symbol}
                selectedCategory={category}
                selectedProvider={provider}
                favorites={favorites}
                onSelectSymbol={setSymbol}
                onSelectCategory={setCategory}
                onToggleFavorite={toggleFavorite}
              />
              <button
                onClick={() => setShowAddSymbol((v) => !v)}
                title="Add custom symbol"
                className="p-2.5 rounded-lg border border-terminal-border bg-terminal-elevated hover:border-sky-500/50 text-terminal-muted hover:text-terminal-text transition"
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
                    onClick={() => setTimeframe(tf.value)}
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

            {/* Provider & Candle Count */}
            <select
              aria-label="Data Provider"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="px-2.5 py-2 rounded-lg bg-terminal-elevated border border-terminal-border text-xs"
            >
              <option value="auto">Provider: Auto</option>
              <option value="binance_public">Binance / Kraken (Crypto)</option>
              <option value="twelvedata">TwelveData (Multi-Asset)</option>
              <option value="alphavantage">AlphaVantage (FX)</option>
              <option value="webhook_cache">Webhook / CSV Cache</option>
            </select>

            <select
              aria-label="Candle Count"
              value={candleLimit}
              onChange={(e) => setCandleLimit(Number(e.target.value))}
              className="px-2.5 py-2 rounded-lg bg-terminal-elevated border border-terminal-border text-xs font-mono"
            >
              <option value={100}>100 candles</option>
              <option value={200}>200 candles</option>
              <option value={300}>300 candles</option>
              <option value={500}>500 candles</option>
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
              Upload CSV
            </button>

            <button
              onClick={refreshMarketData}
              disabled={isUpdatingMarket}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-terminal-border bg-terminal-elevated hover:border-sky-500/40 text-terminal-muted hover:text-terminal-text text-xs font-medium transition"
              title="Manual refresh (bypasses cache)"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isUpdatingMarket ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>

            <button
              onClick={resetAnalyzer}
              title="Reset saved Analyzer state"
              className="inline-flex items-center gap-1 px-2.5 py-2 rounded-lg border border-terminal-border bg-terminal-elevated hover:border-rose-500/40 text-terminal-muted hover:text-rose-300 text-xs transition"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset</span>
            </button>

            <button
              onClick={runManualAnalysis}
              disabled={analyzing || !marketData?.candles?.length}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-45 text-white text-xs font-bold tracking-wide transition shadow-sm"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              {analyzing ? 'ANALYZING...' : 'ANALYZE MARKET'}
            </button>
          </div>
        </div>

        {/* Automatic Live Update & Telemetry Strip */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-terminal-border/60 text-xs">
          <div className="flex flex-wrap items-center gap-3">
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={autoUpdateEnabled}
                onChange={(e) => setAutoUpdateEnabled(e.target.checked)}
                className="rounded accent-emerald-500"
              />
              <span className="font-medium">Auto-Update & Signal Re-eval</span>
            </label>

            <select
              aria-label="Polling Interval"
              value={pollingIntervalSec}
              onChange={(e) => setPollingIntervalSec(Number(e.target.value))}
              disabled={!autoUpdateEnabled}
              className="px-2 py-1 rounded bg-terminal-elevated border border-terminal-border text-[11px] font-mono disabled:opacity-50"
            >
              <option value={5}>Every 5s</option>
              <option value={10}>Every 10s</option>
              <option value={15}>Every 15s</option>
              <option value={30}>Every 30s</option>
            </select>

            <label
              className="inline-flex items-center gap-1.5 text-[11px] text-terminal-muted cursor-pointer"
              title="Only trigger full AI/signal re-evaluation when a new candle closes/arrives"
            >
              <input
                type="checkbox"
                checked={candleCloseOnlyReeval}
                onChange={(e) => setCandleCloseOnlyReeval(e.target.checked)}
                className="rounded accent-sky-500"
              />
              <span>Re-evaluate on new candle close</span>
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 text-[11px]">
            {isUpdatingMarket && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-sky-500/15 text-sky-300 font-semibold">
                <Loader2 className="w-3 h-3 animate-spin" />
                Updating...
              </span>
            )}
            {consecutiveErrors > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 font-semibold">
                <AlertTriangle className="w-3 h-3" />
                Recovering ({consecutiveErrors})
              </span>
            )}
            {overview?.connection_status === 'LIVE' && !isStaleData && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 font-bold">
                <Radio className="w-3 h-3 animate-pulse" />
                LIVE
              </span>
            )}
            {isStaleData && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-bold">
                <AlertTriangle className="w-3 h-3" />
                STALE DATA
              </span>
            )}
            <span className="text-terminal-muted font-mono">
              Synced:{' '}
              {lastUpdatedAt
                ? new Date(lastUpdatedAt).toISOString().slice(11, 19) + ' UTC'
                : 'Pending'}
            </span>
          </div>
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
              <option value="commodities">Commodities</option>
              <option value="indices">Indices</option>
              <option value="stocks">Stocks</option>
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
          <div className="text-[11px] text-terminal-muted truncate">
            {overview?.display_name || activeSpec?.display_name}
          </div>
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
            {marketData?.integrity.valid_count ?? 0} candles
            {marketData?.cache_hit ? ' (cached)' : ''}
          </div>
        </div>
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
          <div className="text-[11px] text-terminal-muted">Market Session</div>
          <div className="text-xs font-semibold mt-0.5">{overview?.market_session || '—'}</div>
          <div className="text-[11px] text-terminal-muted">{overview?.session_status}</div>
        </div>
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-3">
          <div className="text-[11px] text-terminal-muted">Data Source</div>
          <div className="text-xs font-semibold mt-0.5 truncate">{overview?.data_source || 'none'}</div>
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

      {/* Banners for unsupported provider/symbol, stale data, errors, demo, or paper feedback */}
      {providerUnsupportedSymbol && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-2.5 text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>
            <strong>{symbol}</strong> is not supported by provider <strong>{provider}</strong>. Switch Provider to <strong>Auto</strong> or select a supported instrument.
          </span>
        </div>
      )}

      {isStaleData && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>
            <strong>STALE DATA WARNING:</strong> Market candles are {marketData?.integrity.stale_seconds}s old. BUY/SELL signals are paused until fresh data arrives.
          </span>
        </div>
      )}

      {overview?.is_demo && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-300 flex items-center gap-2">
          <Database className="w-4 h-4 shrink-0" />
          <span>
            <strong>DEMO MODE ACTIVE:</strong> Static historical sample dataset is displayed for engine inspection. Do not treat demo prices as live market quotes.
          </span>
        </div>
      )}

      {(analyzeError || csvError || connectionError || paperMsg) && (
        <div
          className={`rounded-lg border px-4 py-2.5 text-xs flex items-center gap-2 ${
            analyzeError || csvError || connectionError || paperMsg?.startsWith('Paper trade blocked')
              ? 'border-rose-500/30 bg-rose-500/10 text-rose-300'
              : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
          }`}
        >
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{analyzeError || csvError || connectionError || paperMsg}</span>
        </div>
      )}

      {/* Prominent Beginner-Friendly AI TRADE SIGNAL Section */}
      <AITradeSignalCard
        report={analysis}
        scanning={analyzing}
        dataUnavailable={!marketData?.candles?.length || isStaleData}
        symbol={symbol}
        timeframe={timeframe}
        decimals={decimals}
        onSendToPaper={handleSendToPaper}
        paperSubmitting={paperBusy}
      />

      {/* Main Chart + Side Indicator & Session Panel */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-5">
        <div className="xl:col-span-3">
          {isLoadingMarket ? (
            <div className="h-[460px] rounded-xl border border-terminal-border bg-terminal-panel flex items-center justify-center text-sm text-terminal-muted">
              Loading market data...
            </div>
          ) : (
            <CandlestickChart
              candles={marketData?.candles || []}
              overview={overview}
              overlays={marketData?.overlays}
              analysis={analysis}
              theme={theme}
              decimals={decimals}
              chartSettings={chartSettings}
              onChangeChartSettings={setChartSettings}
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
            Click <strong>ANALYZE MARKET</strong> (or keep Auto-Update enabled) once valid market data is loaded to scan for qualified BUY/SELL setups, beginner-friendly explanations, entry/SL/TP levels, and multi-timeframe confirmation.
          </p>
        </div>
      )}
    </div>
  )
}
