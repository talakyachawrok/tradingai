import React, { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  BarChart3,
  Bell,
  BellRing,
  BookOpen,
  BrainCircuit,
  CandlestickChart as ChartIcon,
  Menu,
  Moon,
  Settings,
  Sun,
  Wallet,
  Webhook,
  X,
} from 'lucide-react'
import { BacktestPage } from './pages/BacktestPage'
import { DashboardPage } from './pages/DashboardPage'
import { JournalPage } from './pages/JournalPage'
import { PaperTradingPage } from './pages/PaperTradingPage'
import { ProbabilityLabPage } from './pages/ProbabilityLabPage'
import { SettingsPage } from './pages/SettingsPage'
import { SignalHistoryPage } from './pages/SignalHistoryPage'
import { WebhookPage } from './pages/WebhookPage'
import { api } from './services/api'

type NavTab =
  | 'dashboard'
  | 'signals'
  | 'journal'
  | 'backtest'
  | 'paper'
  | 'probability'
  | 'webhooks'
  | 'settings'

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard')
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [allowDemo, setAllowDemo] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') root.classList.add('dark')
    else root.classList.remove('dark')
  }, [theme])

  const healthQ = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30000 })
  const notifQ = useQuery({
    queryKey: ['notifications'],
    queryFn: api.listNotifications,
    refetchInterval: 15000,
  })

  const unreadCount = (notifQ.data || []).filter((n) => !n.read).length

  const navItems: Array<{ id: NavTab; label: string; icon: React.ComponentType<any> }> = [
    { id: 'dashboard', label: 'Market Analyzer', icon: ChartIcon },
    { id: 'signals', label: 'Trade Signal History', icon: BellRing },
    { id: 'journal', label: 'Trade Journal', icon: BookOpen },
    { id: 'backtest', label: 'Backtesting', icon: BarChart3 },
    { id: 'paper', label: 'Paper Trading', icon: Wallet },
    { id: 'probability', label: 'Probability Lab', icon: BrainCircuit },
    { id: 'webhooks', label: 'TradingView Webhooks', icon: Webhook },
    { id: 'settings', label: 'Settings & Risk', icon: Settings },
  ]

  return (
    <div className="min-h-screen flex bg-terminal-bg text-terminal-text">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 border-r border-terminal-border bg-terminal-panel flex flex-col transition-transform lg:static lg:translate-x-0 ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="h-16 px-5 flex items-center justify-between border-b border-terminal-border">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-sky-600/20 border border-sky-500/40 flex items-center justify-center">
              <Activity className="w-4 h-4 text-sky-400" />
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight">AI Trading Analyzer</div>
              <div className="text-[10px] text-terminal-muted uppercase tracking-wider">
                Quantitative Terminal
              </div>
            </div>
          </div>
          <button onClick={() => setMobileMenuOpen(false)} className="lg:hidden text-terminal-muted">
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon
            const active = activeTab === item.id
            return (
              <button
                key={item.id}
                onClick={() => {
                  setActiveTab(item.id)
                  setMobileMenuOpen(false)
                }}
                className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-xs font-medium transition ${
                  active
                    ? 'bg-sky-600/15 text-sky-400 border border-sky-500/30'
                    : 'text-terminal-muted hover:text-terminal-text hover:bg-terminal-elevated'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>

        <div className="p-4 border-t border-terminal-border text-[11px] space-y-1.5 text-terminal-muted">
          <div className="flex items-center justify-between">
            <span>Backend API</span>
            <span className={healthQ.isSuccess ? 'text-emerald-400 font-semibold' : 'text-rose-400'}>
              {healthQ.isSuccess ? 'Online' : 'Offline'}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span>Database</span>
            <span className="font-mono">{healthQ.data?.database?.backend || '—'}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>ML Model</span>
            <span className={healthQ.data?.ml_model_validated ? 'text-emerald-400' : 'text-amber-400'}>
              {healthQ.data?.ml_model_validated ? 'Validated' : 'Unvalidated'}
            </span>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 px-4 lg:px-6 border-b border-terminal-border bg-terminal-panel flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 rounded-lg border border-terminal-border"
            >
              <Menu className="w-4 h-4" />
            </button>
            <h1 className="text-sm font-semibold">
              {navItems.find((n) => n.id === activeTab)?.label}
            </h1>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
              title="Toggle Dark / Light Mode"
              className="p-2 rounded-lg border border-terminal-border bg-terminal-elevated hover:border-sky-500/40 transition"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4" />}
            </button>

            <div className="relative">
              <button
                onClick={() => setNotifOpen((v) => !v)}
                className="p-2 rounded-lg border border-terminal-border bg-terminal-elevated hover:border-sky-500/40 relative transition"
              >
                <Bell className="w-4 h-4" />
                {unreadCount > 0 && (
                  <span className="absolute -top-1 -right-1 px-1.5 py-0.2 rounded-full bg-rose-500 text-white text-[10px] font-bold">
                    {unreadCount}
                  </span>
                )}
              </button>

              {notifOpen && (
                <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto rounded-xl border border-terminal-border bg-terminal-panel shadow-xl z-50 p-3 space-y-2 text-xs">
                  <div className="flex items-center justify-between border-b border-terminal-border pb-2">
                    <span className="font-bold">Notifications</span>
                    <button
                      onClick={async () => {
                        await api.markAllNotificationsRead()
                        notifQ.refetch()
                      }}
                      className="text-sky-400 hover:underline"
                    >
                      Mark all read
                    </button>
                  </div>
                  {(notifQ.data || []).length === 0 ? (
                    <p className="text-terminal-muted py-4 text-center">No notifications yet.</p>
                  ) : (
                    notifQ.data?.slice(0, 15).map((n) => (
                      <div
                        key={n.id}
                        onClick={async () => {
                          if (!n.read) {
                            await api.markNotificationRead(n.id)
                            notifQ.refetch()
                          }
                        }}
                        className={`p-2.5 rounded-lg border cursor-pointer ${
                          n.read
                            ? 'border-terminal-border/50 opacity-70'
                            : 'border-sky-500/40 bg-sky-500/5'
                        }`}
                      >
                        <div className="font-semibold">{n.title}</div>
                        <p className="text-[11px] text-terminal-muted mt-0.5">{n.message}</p>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-6 max-w-[1600px] w-full mx-auto">
          {activeTab === 'dashboard' && (
            <DashboardPage
              theme={theme}
              allowDemo={allowDemo}
              setAllowDemo={setAllowDemo}
              onNotificationRefresh={() => notifQ.refetch()}
            />
          )}
          {activeTab === 'signals' && <SignalHistoryPage allowDemo={allowDemo} />}
          {activeTab === 'journal' && <JournalPage />}
          {activeTab === 'backtest' && <BacktestPage allowDemo={allowDemo} />}
          {activeTab === 'paper' && <PaperTradingPage allowDemo={allowDemo} />}
          {activeTab === 'probability' && <ProbabilityLabPage allowDemo={allowDemo} />}
          {activeTab === 'webhooks' && <WebhookPage />}
          {activeTab === 'settings' && (
            <SettingsPage
              theme={theme}
              onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
            />
          )}
        </main>
      </div>
    </div>
  )
}
export default App
