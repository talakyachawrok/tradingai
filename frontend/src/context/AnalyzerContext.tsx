import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import type {
  ChartOverlaySettings,
  MarketCategory,
  MarketDataResponse,
  Timeframe,
  TradeAnalysisReport,
} from '../types/trading'
import { playAlertSound, showBrowserNotification } from '../utils/notifications'

const STATE_STORAGE_KEY = 'ai_trading_analyzer_state_v1'
const WATCHLIST_STORAGE_KEY = 'ai_trading_analyzer_watchlist_v1'
const DEFAULT_FAVORITES = ['XAUUSD', 'EURUSD', 'GBPUSD', 'BTCUSD']

export interface PersistedAnalyzerConfig {
  symbol: string
  category: MarketCategory
  timeframe: Timeframe
  provider: string
  candleLimit: number
  allowDemo: boolean
  autoUpdateEnabled: boolean
  pollingIntervalSec: number
  candleCloseOnlyReeval: boolean
  chartSettings: ChartOverlaySettings
  analysis: TradeAnalysisReport | null
}

const DEFAULT_CHART_SETTINGS: ChartOverlaySettings = {
  showEma20: true,
  showEma50: true,
  showEma200: true,
  showLevels: true,
  showTradeLines: true,
}

const DEFAULT_CONFIG: PersistedAnalyzerConfig = {
  symbol: 'BTCUSD',
  category: 'all',
  timeframe: '1h',
  provider: 'auto',
  candleLimit: 300,
  allowDemo: false,
  autoUpdateEnabled: true,
  pollingIntervalSec: 10,
  candleCloseOnlyReeval: true,
  chartSettings: DEFAULT_CHART_SETTINGS,
  analysis: null,
}

function loadStoredState(): PersistedAnalyzerConfig {
  try {
    const raw = window.localStorage.getItem(STATE_STORAGE_KEY)
    if (!raw) return DEFAULT_CONFIG
    const parsed = JSON.parse(raw)
    return {
      ...DEFAULT_CONFIG,
      ...parsed,
      chartSettings: { ...DEFAULT_CHART_SETTINGS, ...(parsed.chartSettings || {}) },
    }
  } catch {
    return DEFAULT_CONFIG
  }
}

function loadWatchlist(): string[] {
  try {
    const raw = window.localStorage.getItem(WATCHLIST_STORAGE_KEY)
    if (!raw) return DEFAULT_FAVORITES
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : DEFAULT_FAVORITES
  } catch {
    return DEFAULT_FAVORITES
  }
}

interface AnalyzerContextValue {
  symbol: string
  category: MarketCategory
  timeframe: Timeframe
  provider: string
  candleLimit: number
  allowDemo: boolean
  autoUpdateEnabled: boolean
  pollingIntervalSec: number
  candleCloseOnlyReeval: boolean
  chartSettings: ChartOverlaySettings
  favorites: string[]
  analysis: TradeAnalysisReport | null
  marketData: MarketDataResponse | undefined
  isLoadingMarket: boolean
  isUpdatingMarket: boolean
  analyzing: boolean
  analyzeError: string | null
  connectionError: string | null
  consecutiveErrors: number
  lastUpdatedAt: string | null
  setSymbol: (sym: string) => void
  setCategory: (cat: MarketCategory) => void
  setTimeframe: (tf: Timeframe) => void
  setProvider: (p: string) => void
  setCandleLimit: (lim: number) => void
  setAllowDemo: (v: boolean) => void
  setAutoUpdateEnabled: (v: boolean) => void
  setPollingIntervalSec: (sec: number) => void
  setCandleCloseOnlyReeval: (v: boolean) => void
  setChartSettings: (next: ChartOverlaySettings) => void
  toggleFavorite: (sym: string) => void
  runManualAnalysis: () => Promise<void>
  refreshMarketData: () => Promise<void>
  resetAnalyzer: () => void
}

const AnalyzerContext = createContext<AnalyzerContextValue | null>(null)

export const AnalyzerProvider: React.FC<{
  children: React.ReactNode
  onNotificationRefresh: () => void
}> = ({ children, onNotificationRefresh }) => {
  const initial = useRef<PersistedAnalyzerConfig>(loadStoredState()).current
  const [symbol, setSymbolState] = useState<string>(initial.symbol)
  const [category, setCategory] = useState<MarketCategory>(initial.category)
  const [timeframe, setTimeframeState] = useState<Timeframe>(initial.timeframe)
  const [provider, setProviderState] = useState<string>(initial.provider)
  const [candleLimit, setCandleLimit] = useState<number>(initial.candleLimit)
  const [allowDemo, setAllowDemo] = useState<boolean>(initial.allowDemo)
  const [autoUpdateEnabled, setAutoUpdateEnabled] = useState<boolean>(initial.autoUpdateEnabled)
  const [pollingIntervalSec, setPollingIntervalSec] = useState<number>(initial.pollingIntervalSec)
  const [candleCloseOnlyReeval, setCandleCloseOnlyReeval] = useState<boolean>(initial.candleCloseOnlyReeval)
  const [chartSettings, setChartSettings] = useState<ChartOverlaySettings>(initial.chartSettings)
  const [favorites, setFavorites] = useState<string[]>(loadWatchlist)
  const [analysis, setAnalysis] = useState<TradeAnalysisReport | null>(initial.analysis)

  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [consecutiveErrors, setConsecutiveErrors] = useState(0)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const queryClient = useQueryClient()
  const lastAlertedSignalKeyRef = useRef<string | null>(null)
  const reevalLockRef = useRef(false)

  const settingsQ = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
    staleTime: 60000,
  })

  // Persist Analyzer state (never storing any API keys or secrets)
  useEffect(() => {
    const payload: PersistedAnalyzerConfig = {
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
      analysis,
    }
    try {
      window.localStorage.setItem(STATE_STORAGE_KEY, JSON.stringify(payload))
    } catch {
      // Ignore quota errors while keeping full in-memory state
    }
  }, [
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
    analysis,
  ])

  useEffect(() => {
    try {
      window.localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(favorites))
    } catch {
      // Ignore storage failures
    }
  }, [favorites])

  const emitSignalAlertIfNew = useCallback(
    (report: TradeAnalysisReport) => {
      const isQualifying =
        report.signal_status === 'BUY SIGNAL' || report.signal_status === 'SELL SIGNAL'
      if (!isQualifying) return

      const dedupKey = `${report.symbol}|${report.timeframe}|${report.data_timestamp}|${report.signal_status}`
      if (lastAlertedSignalKeyRef.current === dedupKey) return
      lastAlertedSignalKeyRef.current = dedupKey

      const alertsCfg = settingsQ.data?.user_settings?.alerts
      const allowDir =
        (report.signal_status === 'BUY SIGNAL' && (alertsCfg?.enable_buy_alerts ?? true)) ||
        (report.signal_status === 'SELL SIGNAL' && (alertsCfg?.enable_sell_alerts ?? true))
      if (!allowDir) return

      if (alertsCfg?.sound_enabled ?? true) {
        playAlertSound()
      }
      if (alertsCfg?.browser_notifications_enabled ?? true) {
        showBrowserNotification(
          `AI TRADING ANALYZER: ${report.signal_status} — ${report.symbol}`,
          `Timeframe: ${report.timeframe} | Entry: ${report.trade_levels.entry_price ?? 'N/A'} | SL: ${report.trade_levels.stop_loss ?? 'N/A'} | TP1: ${report.trade_levels.take_profit_1 ?? 'N/A'}`
        )
      }
    },
    [settingsQ.data?.user_settings?.alerts]
  )

  const effectiveIntervalMs = autoUpdateEnabled
    ? Math.min(60000, pollingIntervalSec * 1000 * Math.pow(2, Math.min(consecutiveErrors, 2)))
    : false

  const marketQ = useQuery({
    queryKey: ['ohlcv', symbol, timeframe, allowDemo, provider, candleLimit],
    queryFn: async () => {
      try {
        const res = await api.getOhlcv(symbol, timeframe, allowDemo, provider, false, candleLimit)
        setConsecutiveErrors(0)
        setConnectionError(null)
        setLastUpdatedAt(new Date().toISOString())
        return res
      } catch (err: any) {
        setConsecutiveErrors((c) => c + 1)
        setConnectionError(err?.message || 'Connection error while polling market data.')
        throw err
      }
    },
    refetchInterval: effectiveIntervalMs,
    refetchIntervalInBackground: false,
    staleTime: Math.max(4000, pollingIntervalSec * 1000 - 1000),
  })

  const executeAnalysis = useCallback(
    async (silent: boolean = false) => {
      if (reevalLockRef.current) return
      reevalLockRef.current = true
      if (!silent) setAnalyzing(true)
      setAnalyzeError(null)
      try {
        const report = await api.runAnalysis(symbol, timeframe, allowDemo, provider, candleLimit)
        setAnalysis(report)
        onNotificationRefresh()
        emitSignalAlertIfNew(report)
      } catch (err: any) {
        if (!silent) setAnalyzeError(err?.message || 'Analysis failed.')
      } finally {
        if (!silent) setAnalyzing(false)
        reevalLockRef.current = false
      }
    },
    [symbol, timeframe, allowDemo, provider, candleLimit, onNotificationRefresh, emitSignalAlertIfNew]
  )

  // Smart automatic signal re-evaluation when new market data arrives:
  // Avoids unnecessary reruns if current analysis matches symbol/tf/provider and latest candle has not changed.
  useEffect(() => {
    if (!autoUpdateEnabled) return
    const data = marketQ.data
    if (!data || data.candles.length < 30) return
    if (data.overview.connection_status === 'DATA_UNAVAILABLE') return
    if (data.integrity.is_stale && !data.overview.is_demo) return

    const latestCandle = data.candles[data.candles.length - 1]
    const sameContext =
      analysis &&
      analysis.symbol === data.overview.symbol &&
      analysis.timeframe === timeframe &&
      analysis.is_demo === data.overview.is_demo

    if (!sameContext) {
      void executeAnalysis(true)
      return
    }

    const latestTs = new Date(latestCandle.timestamp).getTime()
    const analyzedTs = new Date(analysis.data_timestamp).getTime()
    const newCandleArrived = latestTs > analyzedTs

    if (newCandleArrived) {
      void executeAnalysis(true)
      return
    }

    if (!candleCloseOnlyReeval && analysis.indicators.atr_14) {
      const priceDelta = Math.abs(latestCandle.close - analysis.current_price)
      if (priceDelta >= analysis.indicators.atr_14 * 0.2) {
        void executeAnalysis(true)
      }
    }
  }, [marketQ.data, autoUpdateEnabled, candleCloseOnlyReeval, timeframe, analysis, executeAnalysis])

  const setSymbol = useCallback((nextSym: string) => {
    setSymbolState(nextSym)
    setAnalyzeError(null)
    setAnalysis((prev) => (prev?.symbol === nextSym ? prev : null))
  }, [])

  const setTimeframe = useCallback((nextTf: Timeframe) => {
    setTimeframeState(nextTf)
    setAnalyzeError(null)
    setAnalysis((prev) => (prev?.timeframe === nextTf ? prev : null))
  }, [])

  const setProvider = useCallback((nextProv: string) => {
    setProviderState(nextProv)
    setAnalyzeError(null)
  }, [])

  const toggleFavorite = useCallback((sym: string) => {
    setFavorites((prev) =>
      prev.includes(sym) ? prev.filter((item) => item !== sym) : [...prev, sym]
    )
  }, [])

  const refreshMarketData = useCallback(async () => {
    setRefreshing(true)
    setAnalyzeError(null)
    try {
      const fresh = await api.getOhlcv(symbol, timeframe, allowDemo, provider, true, candleLimit)
      queryClient.setQueryData(
        ['ohlcv', symbol, timeframe, allowDemo, provider, candleLimit],
        fresh
      )
      setConsecutiveErrors(0)
      setConnectionError(null)
      setLastUpdatedAt(new Date().toISOString())
    } catch (err: any) {
      setConsecutiveErrors((c) => c + 1)
      setConnectionError(err?.message || 'Failed to refresh market data.')
      setAnalyzeError(err?.message || 'Failed to refresh market data.')
    } finally {
      setRefreshing(false)
    }
  }, [symbol, timeframe, allowDemo, provider, candleLimit, queryClient])

  const resetAnalyzer = useCallback(() => {
    setSymbolState(DEFAULT_CONFIG.symbol)
    setCategory(DEFAULT_CONFIG.category)
    setTimeframeState(DEFAULT_CONFIG.timeframe)
    setProviderState(DEFAULT_CONFIG.provider)
    setCandleLimit(DEFAULT_CONFIG.candleLimit)
    setAllowDemo(DEFAULT_CONFIG.allowDemo)
    setAutoUpdateEnabled(DEFAULT_CONFIG.autoUpdateEnabled)
    setPollingIntervalSec(DEFAULT_CONFIG.pollingIntervalSec)
    setCandleCloseOnlyReeval(DEFAULT_CONFIG.candleCloseOnlyReeval)
    setChartSettings(DEFAULT_CHART_SETTINGS)
    setAnalysis(null)
    setAnalyzeError(null)
    setConnectionError(null)
    window.localStorage.removeItem(STATE_STORAGE_KEY)
  }, [])

  return (
    <AnalyzerContext.Provider
      value={{
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
        marketData: marketQ.data,
        isLoadingMarket: marketQ.isLoading,
        isUpdatingMarket: marketQ.isFetching || refreshing,
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
        runManualAnalysis: () => executeAnalysis(false),
        refreshMarketData,
        resetAnalyzer,
      }}
    >
      {children}
    </AnalyzerContext.Provider>
  )
}

export function useAnalyzer(): AnalyzerContextValue {
  const ctx = useContext(AnalyzerContext)
  if (!ctx) throw new Error('useAnalyzer must be used within AnalyzerProvider')
  return ctx
}
