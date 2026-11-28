import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, Search, Star } from 'lucide-react'
import type { InstrumentSpec, MarketCategory, ProviderCapability } from '../types/trading'

interface Props {
  instruments: InstrumentSpec[]
  providers: ProviderCapability[]
  selectedSymbol: string
  selectedCategory: MarketCategory
  selectedProvider: string
  favorites: string[]
  onSelectSymbol: (symbol: string) => void
  onSelectCategory: (cat: MarketCategory) => void
  onToggleFavorite: (symbol: string) => void
}

const CATEGORIES: Array<{ id: MarketCategory; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'favorites', label: 'Watchlist' },
  { id: 'forex', label: 'Forex' },
  { id: 'crypto', label: 'Crypto' },
  { id: 'commodities', label: 'Commodities' },
  { id: 'indices', label: 'Indices' },
  { id: 'stocks', label: 'Stocks' },
]

export const MarketSelector: React.FC<Props> = ({
  instruments,
  providers,
  selectedSymbol,
  selectedCategory,
  selectedProvider,
  favorites,
  onSelectSymbol,
  onSelectCategory,
  onToggleFavorite,
}) => {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const rootRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const activeProviderCap = useMemo(() => {
    if (selectedProvider === 'auto') return null
    return providers.find((p) => p.name === selectedProvider) || null
  }, [providers, selectedProvider])

  const isSymbolSupported = (inst: InstrumentSpec): boolean => {
    if (!activeProviderCap) return true
    if (activeProviderCap.supported_symbols.length === 0) return true
    return activeProviderCap.supported_symbols.includes(inst.symbol)
  }

  const currentInstrument = useMemo(
    () => instruments.find((i) => i.symbol === selectedSymbol),
    [instruments, selectedSymbol]
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return instruments.filter((inst) => {
      const cat = inst.asset_class === 'metals' ? 'commodities' : inst.asset_class
      if (selectedCategory === 'favorites' && !favorites.includes(inst.symbol)) return false
      if (
        selectedCategory !== 'all' &&
        selectedCategory !== 'favorites' &&
        cat !== selectedCategory
      ) {
        return false
      }
      if (!q) return true
      return (
        inst.symbol.toLowerCase().includes(q) ||
        inst.display_name.toLowerCase().includes(q) ||
        cat.toLowerCase().includes(q)
      )
    })
  }, [instruments, selectedCategory, favorites, search])

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label="Market Selector"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center justify-between gap-2.5 min-w-[230px] px-3 py-2 rounded-lg bg-terminal-elevated border border-terminal-border hover:border-sky-500/50 text-left transition"
      >
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-bold">{selectedSymbol}</span>
            {currentInstrument && (
              <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-terminal-panel border border-terminal-border text-terminal-muted">
                {currentInstrument.asset_class}
              </span>
            )}
          </div>
          <div className="text-[11px] text-terminal-muted truncate max-w-[185px]">
            {currentInstrument?.display_name || selectedSymbol}
          </div>
        </div>
        <ChevronDown className={`w-4 h-4 text-terminal-muted transition ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute left-0 mt-2 w-[360px] sm:w-[440px] max-w-[92vw] rounded-xl border border-terminal-border bg-terminal-panel shadow-2xl z-50 overflow-hidden">
          {/* Search Input */}
          <div className="p-2.5 border-b border-terminal-border bg-terminal-elevated/60">
            <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-terminal-bg border border-terminal-border">
              <Search className="w-3.5 h-3.5 text-terminal-muted shrink-0" />
              <input
                autoFocus
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search symbol or name (e.g. XAUUSD, Gold, Apple, SOL)..."
                className="w-full bg-transparent text-xs outline-none placeholder:text-terminal-muted"
              />
            </div>

            {/* Category Tabs */}
            <div className="flex flex-wrap gap-1 mt-2">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => onSelectCategory(cat.id)}
                  className={`px-2 py-1 rounded text-[11px] font-medium transition ${
                    selectedCategory === cat.id
                      ? 'bg-sky-600 text-white'
                      : 'bg-terminal-panel text-terminal-muted hover:text-terminal-text border border-terminal-border'
                  }`}
                >
                  {cat.id === 'favorites' ? `★ ${cat.label}` : cat.label}
                </button>
              ))}
            </div>
          </div>

          {/* Instrument List */}
          <div className="max-h-72 overflow-y-auto divide-y divide-terminal-border/50">
            {filtered.length === 0 ? (
              <div className="p-6 text-center text-xs text-terminal-muted">
                No instruments match "{search}" in this category.
              </div>
            ) : (
              filtered.map((inst) => {
                const supported = isSymbolSupported(inst)
                const isFav = favorites.includes(inst.symbol)
                const isSelected = inst.symbol === selectedSymbol
                return (
                  <div
                    key={inst.symbol}
                    className={`flex items-center justify-between gap-2 px-3 py-2 text-xs transition ${
                      isSelected ? 'bg-sky-500/10' : 'hover:bg-terminal-elevated/60'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        onSelectSymbol(inst.symbol)
                        setOpen(false)
                      }}
                      className="flex-1 flex items-center justify-between gap-2 text-left min-w-0"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-bold font-mono">{inst.symbol}</span>
                          <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-terminal-elevated text-terminal-muted">
                            {inst.asset_class}
                          </span>
                          {!supported && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-400">
                              Unsupported by {selectedProvider}
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-terminal-muted truncate">
                          {inst.display_name}
                        </div>
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        onToggleFavorite(inst.symbol)
                      }}
                      title={isFav ? 'Remove from Watchlist' : 'Add to Watchlist'}
                      className="p-1 rounded hover:bg-terminal-elevated"
                    >
                      <Star
                        className={`w-3.5 h-3.5 ${
                          isFav ? 'fill-amber-400 text-amber-400' : 'text-terminal-muted'
                        }`}
                      />
                    </button>
                  </div>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
