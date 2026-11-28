import type {
  BacktestResult,
  InstrumentSpec,
  JournalEntry,
  MarketDataResponse,
  NotificationItem,
  PaperAccountSummary,
  PaperTradePosition,
  Timeframe,
  ProviderConnectionTestResult,
  TradeAnalysisReport,
  TradeSignalRecord,
  WebhookLogRecord,
} from '../types/trading'

const API_BASE = (import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers || {}),
    },
    ...init,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const errJson = await res.json()
      detail = errJson.detail || JSON.stringify(errJson)
    } catch {
      detail = await res.text()
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<any>('/api/health'),
  listInstruments: () => request<InstrumentSpec[]>('/api/market/instruments'),
  addInstrument: (spec: Partial<InstrumentSpec>) =>
    request<InstrumentSpec>('/api/market/instruments', {
      method: 'POST',
      body: JSON.stringify(spec),
    }),
  listProviders: () => request<any[]>('/api/market/providers'),
  testProviderConnection: (provider: string, symbol: string = 'XAUUSD', timeframe: Timeframe = '1h') =>
    request<ProviderConnectionTestResult>('/api/market/providers/test', {
      method: 'POST',
      body: JSON.stringify({ provider, symbol, timeframe }),
    }),
  getOhlcv: (
    symbol: string,
    timeframe: Timeframe,
    allowDemo: boolean,
    provider?: string,
    refresh: boolean = false
  ) => {
    const params = new URLSearchParams({
      symbol,
      timeframe,
      allow_demo: String(allowDemo),
      refresh: String(refresh),
    })
    if (provider && provider !== 'auto') params.set('provider', provider)
    return request<MarketDataResponse>(`/api/market/ohlcv?${params.toString()}`)
  },
  uploadCsv: (symbol: string, timeframe: Timeframe, file: File) => {
    const form = new FormData()
    form.append('symbol', symbol)
    form.append('timeframe', timeframe)
    form.append('file', file)
    return request<{ symbol: string; timeframe: string; candles_loaded: number }>(
      '/api/market/upload-csv',
      { method: 'POST', body: form }
    )
  },
  getSessionsNews: (symbol: string) =>
    request<any>(`/api/market/sessions-news?symbol=${encodeURIComponent(symbol)}`),

  runAnalysis: (symbol: string, timeframe: Timeframe, allowDemo: boolean, provider?: string) =>
    request<TradeAnalysisReport>('/api/analysis/run', {
      method: 'POST',
      body: JSON.stringify({ symbol, timeframe, allow_demo: allowDemo, provider }),
    }),
  listSignals: (filters: Record<string, string>) => {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => {
      if (v) params.set(k, v)
    })
    return request<TradeSignalRecord[]>(`/api/signals?${params.toString()}`)
  },
  getLatestSignal: (symbol?: string, timeframe?: string) => {
    const params = new URLSearchParams()
    if (symbol) params.set('symbol', symbol)
    if (timeframe) params.set('timeframe', timeframe)
    return request<TradeSignalRecord | null>(`/api/signals/latest?${params.toString()}`)
  },
  trackSignals: (allowDemo: boolean) =>
    request<TradeSignalRecord[]>(`/api/signals/track?allow_demo=${allowDemo}`, {
      method: 'POST',
    }),
  listAnalyses: () => request<TradeAnalysisReport[]>('/api/analysis/history'),
  computePositionSize: (payload: {
    symbol: string
    account_balance: number
    risk_percentage: number
    entry_price: number
    stop_loss: number
  }) =>
    request<any>('/api/analysis/position-size', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listJournal: (filters: Record<string, string>) => {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => {
      if (v) params.set(k, v)
    })
    return request<JournalEntry[]>(`/api/journal?${params.toString()}`)
  },
  updateJournal: (id: string, body: { outcome?: string; notes?: string }) =>
    request<JournalEntry>(`/api/journal/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  runBacktest: (payload: any) =>
    request<BacktestResult>('/api/backtest/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listBacktests: () => request<BacktestResult[]>('/api/backtest/history'),

  getPaperAccount: () => request<PaperAccountSummary>('/api/paper/account'),
  getPaperPositions: () => request<PaperTradePosition[]>('/api/paper/positions'),
  openPaperOrder: (payload: any) =>
    request<PaperTradePosition>('/api/paper/order', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  closePaperOrder: (tradeId: string) =>
    request<PaperTradePosition>(`/api/paper/close/${tradeId}`, { method: 'POST' }),
  syncPaper: (allowDemo: boolean) =>
    request<{ summary: PaperAccountSummary; positions: PaperTradePosition[] }>(
      `/api/paper/sync?allow_demo=${allowDemo}`,
      { method: 'POST' }
    ),
  resetPaper: () => request<PaperAccountSummary>('/api/paper/reset', { method: 'POST' }),

  getWebhookStatus: () => request<any>('/api/webhooks/status'),
  getWebhookLogs: () => request<WebhookLogRecord[]>('/api/webhooks/logs'),
  sendTestWebhook: (payload: any, secret: string) =>
    request<any>('/api/webhooks/tradingview', {
      method: 'POST',
      headers: { 'x-webhook-secret': secret },
      body: JSON.stringify(payload),
    }),

  getMlStatus: () => request<any>('/api/ml/status'),
  trainMl: (payload: any) =>
    request<any>('/api/ml/train', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getSettings: () => request<any>('/api/settings'),
  saveSettings: (userSettings: any) =>
    request<any>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(userSettings),
    }),

  listNotifications: () => request<NotificationItem[]>('/api/notifications'),
  markNotificationRead: (id: string) =>
    request<any>(`/api/notifications/${id}/read`, { method: 'POST' }),
  markAllNotificationsRead: () =>
    request<any>('/api/notifications/read-all', { method: 'POST' }),
}
