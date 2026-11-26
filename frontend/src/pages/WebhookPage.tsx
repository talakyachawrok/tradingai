import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Send, Webhook } from 'lucide-react'
import { api } from '../services/api'

const EXAMPLE_PAYLOAD = `{
  "symbol": "{{ticker}}",
  "timeframe": "{{interval}}",
  "open": {{open}},
  "high": {{high}},
  "low": {{low}},
  "close": {{close}},
  "volume": {{volume}},
  "timestamp": "{{timenow}}",
  "exchange": "{{exchange}}",
  "source": "TradingView",
  "event": "analysis_trigger",
  "secret": "change-me-to-a-strong-random-secret"
}`

export const WebhookPage: React.FC = () => {
  const [symbol, setSymbol] = useState('XAUUSD')
  const [timeframe, setTimeframe] = useState('1h')
  const [closePrice, setClosePrice] = useState('2690.50')
  const [secret, setSecret] = useState('change-me-to-a-strong-random-secret')
  const [testResp, setTestResp] = useState<string | null>(null)

  const statusQ = useQuery({ queryKey: ['webhook-status'], queryFn: api.getWebhookStatus })
  const logsQ = useQuery({
    queryKey: ['webhook-logs'],
    queryFn: api.getWebhookLogs,
    refetchInterval: 8000,
  })

  const handleTest = async (e: React.FormEvent) => {
    e.preventDefault()
    setTestResp(null)
    try {
      const res = await api.sendTestWebhook(
        {
          symbol,
          timeframe,
          close: Number(closePrice),
          timestamp: new Date().toISOString(),
          source: 'TradingView-ManualTest',
          event: 'analysis_trigger',
        },
        secret
      )
      setTestResp(`Accepted (${res.status}): ${res.message}`)
      logsQ.refetch()
    } catch (err: any) {
      setTestResp(`Rejected: ${err.message}`)
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="rounded-xl border border-terminal-border bg-terminal-panel p-5 space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Webhook className="w-5 h-5 text-sky-400" />
              <h2 className="text-base font-bold">TradingView Webhook Integration</h2>
            </div>
            <span
              className={`px-2 py-0.5 rounded font-semibold ${
                statusQ.data?.secret_configured
                  ? 'bg-emerald-500/15 text-emerald-400'
                  : 'bg-amber-500/15 text-amber-400'
              }`}
            >
              {statusQ.data?.secret_configured ? 'Custom Secret Active' : 'Default Dev Secret'}
            </span>
          </div>
          <p className="text-terminal-muted leading-relaxed">
            Configure your TradingView alert to POST JSON to <code>{statusQ.data?.endpoint || '/api/webhooks/tradingview'}</code>. The backend validates the secret, deduplicates within {statusQ.data?.dedup_window_seconds || 300}s, responds immediately with HTTP 202, and runs analysis asynchronously.
          </p>
          <div className="space-y-1">
            <div className="font-semibold text-terminal-muted">TradingView Alert Message JSON Template</div>
            <pre className="p-3 rounded-lg bg-terminal-bg border border-terminal-border font-mono text-[11px] overflow-x-auto">
              {EXAMPLE_PAYLOAD}
            </pre>
          </div>
          <p className="text-[11px] text-terminal-muted">
            Full Pine Script v5 alert indicator is located at <code>tradingview/ai_trading_analyzer_alert.pine</code>.
          </p>
        </div>

        <form onSubmit={handleTest} className="rounded-xl border border-terminal-border bg-terminal-panel p-5 space-y-3 text-xs">
          <h3 className="text-sm font-bold">Webhook Endpoint Tester</h3>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">
              <span className="text-terminal-muted">Symbol</span>
              <input value={symbol} onChange={(e) => setSymbol(e.target.value)} className="w-full px-3 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
            </label>
            <label className="space-y-1">
              <span className="text-terminal-muted">Timeframe</span>
              <input value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className="w-full px-3 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
            </label>
            <label className="space-y-1">
              <span className="text-terminal-muted">Close Price</span>
              <input type="number" step="any" value={closePrice} onChange={(e) => setClosePrice(e.target.value)} className="w-full px-3 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
            </label>
            <label className="space-y-1">
              <span className="text-terminal-muted">Webhook Secret</span>
              <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} className="w-full px-3 py-2 rounded bg-terminal-elevated border border-terminal-border font-mono" />
            </label>
          </div>
          <button type="submit" className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold">
            <Send className="w-3.5 h-3.5" /> Send Test Alert
          </button>
          {testResp && <div className="p-2.5 rounded bg-terminal-elevated border border-terminal-border">{testResp}</div>}
        </form>
      </div>

      <div className="rounded-xl border border-terminal-border bg-terminal-panel overflow-x-auto">
        <div className="px-4 py-3 border-b border-terminal-border text-xs font-bold uppercase tracking-wider text-terminal-muted">
          Recent Webhook Event Logs
        </div>
        <table className="w-full text-xs text-left">
          <thead className="bg-terminal-elevated text-terminal-muted border-b border-terminal-border">
            <tr>
              <th className="p-3">Received (UTC)</th>
              <th className="p-3">Symbol / TF</th>
              <th className="p-3">Event</th>
              <th className="p-3">Status</th>
              <th className="p-3">Message</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-terminal-border">
            {(logsQ.data || []).length === 0 ? (
              <tr>
                <td colSpan={5} className="p-6 text-center text-terminal-muted">No webhook alerts received yet.</td>
              </tr>
            ) : (
              logsQ.data?.map((log) => (
                <tr key={log.alert_id}>
                  <td className="p-3 font-mono">{new Date(log.received_at).toISOString().slice(0, 19).replace('T', ' ')}</td>
                  <td className="p-3 font-semibold">{log.symbol} ({log.timeframe})</td>
                  <td className="p-3">{log.event}</td>
                  <td className="p-3 font-mono">{log.status}</td>
                  <td className="p-3 text-terminal-muted">{log.message}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
