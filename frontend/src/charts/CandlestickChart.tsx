import React, { useEffect, useRef, useState } from 'react'
import {
  ColorType,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  LineStyle,
  SeriesMarker,
  Time,
  createChart,
} from 'lightweight-charts'
import type {
  ChartOverlaySettings,
  IndicatorChartOverlay,
  MarketOverview,
  OHLCVCandle,
  TradeAnalysisReport,
} from '../types/trading'

interface Props {
  candles: OHLCVCandle[]
  overview?: MarketOverview
  overlays?: IndicatorChartOverlay
  analysis?: TradeAnalysisReport | null
  theme: 'dark' | 'light'
  decimals?: number
  chartSettings?: ChartOverlaySettings
  onChangeChartSettings?: (next: ChartOverlaySettings) => void
}

export const CandlestickChart: React.FC<Props> = ({
  candles,
  overview,
  overlays,
  analysis,
  theme,
  decimals = 5,
  chartSettings,
  onChangeChartSettings,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const [localSettings, setLocalSettings] = useState<ChartOverlaySettings>({
    showEma20: true,
    showEma50: true,
    showEma200: true,
    showLevels: true,
    showTradeLines: true,
  })
  const activeSettings = chartSettings || localSettings
  const updateSetting = (key: keyof ChartOverlaySettings) => {
    const next = { ...activeSettings, [key]: !activeSettings[key] }
    if (onChangeChartSettings) onChangeChartSettings(next)
    else setLocalSettings(next)
  }
  const showEma20 = activeSettings.showEma20
  const showEma50 = activeSettings.showEma50
  const showEma200 = activeSettings.showEma200
  const showLevels = activeSettings.showLevels
  const showTradeLines = activeSettings.showTradeLines
  const [hoverOhlc, setHoverOhlc] = useState<OHLCVCandle | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const isDark = theme === 'dark'
    const chart = createChart(el, {
      width: Math.max(el.clientWidth, 320),
      height: 460,
      layout: {
        background: { type: ColorType.Solid, color: isDark ? '#101624' : '#ffffff' },
        textColor: isDark ? '#94a3b8' : '#334155',
      },
      grid: {
        vertLines: { color: isDark ? '#1a2336' : '#f1f5f9' },
        horzLines: { color: isDark ? '#1a2336' : '#f1f5f9' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: isDark ? '#1f2a40' : '#cbd5e1',
      },
      timeScale: {
        borderColor: isDark ? '#1f2a40' : '#cbd5e1',
        timeVisible: true,
        secondsVisible: false,
      },
    })
    chartRef.current = chart

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceFormat: {
        type: 'price',
        precision: Math.min(decimals, 6),
        minMove: Number((1 / Math.pow(10, Math.min(decimals, 6))).toFixed(6)),
      },
    })

    const toUnix = (ts: string) => Math.floor(new Date(ts).getTime() / 1000) as Time

    const formattedCandles = candles.map((c) => ({
      time: toUnix(c.timestamp),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))
    candleSeries.setData(formattedCandles)

    // Crosshair OHLC inspection
    const candleByTime = new Map<number, OHLCVCandle>()
    candles.forEach((c) => candleByTime.set(Math.floor(new Date(c.timestamp).getTime() / 1000), c))
    chart.subscribeCrosshairMove((param) => {
      if (!param.time) {
        setHoverOhlc(candles[candles.length - 1] || null)
        return
      }
      const match = candleByTime.get(Number(param.time))
      if (match) setHoverOhlc(match)
    })

    // Indicator EMA Overlays
    const activeOverlays = analysis?.overlays || overlays
    const addEmaLine = (
      values: Array<number | null> | undefined,
      timestamps: string[] | undefined,
      color: string,
      enabled: boolean
    ) => {
      if (!enabled || !values || !timestamps) return
      const line: ISeriesApi<'Line'> = chart.addLineSeries({
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      const pts = timestamps
        .map((ts, idx) =>
          values[idx] !== null && values[idx] !== undefined
            ? { time: toUnix(ts), value: values[idx] as number }
            : null
        )
        .filter(Boolean) as Array<{ time: Time; value: number }>
      if (pts.length > 0) line.setData(pts)
    }

    addEmaLine(activeOverlays?.ema_20, activeOverlays?.timestamps, '#38bdf8', showEma20)
    addEmaLine(activeOverlays?.ema_50, activeOverlays?.timestamps, '#f59e0b', showEma50)
    addEmaLine(activeOverlays?.ema_200, activeOverlays?.timestamps, '#a855f7', showEma200)

    // Markers: Structure (BOS / CHoCH), Sweeps, and Patterns
    const markers: SeriesMarker<Time>[] = []
    if (analysis) {
      analysis.market_structure.structure_events.forEach((ev) => {
        markers.push({
          time: toUnix(ev.timestamp),
          position: ev.direction === 'bullish' ? 'aboveBar' : 'belowBar',
          color: ev.event_type === 'CHoCH' ? '#f59e0b' : '#38bdf8',
          shape: ev.direction === 'bullish' ? 'arrowUp' : 'arrowDown',
          text: `${ev.event_type}`,
        })
      })
      analysis.liquidity.sweep_events.forEach((sw) => {
        markers.push({
          time: toUnix(sw.timestamp),
          position: sw.direction === 'bullish' ? 'belowBar' : 'aboveBar',
          color: '#eab308',
          shape: 'circle',
          text: 'Sweep',
        })
      })
      analysis.patterns.slice(0, 3).forEach((pat) => {
        const ts = pat.timestamps[pat.timestamps.length - 1]
        if (ts) {
          markers.push({
            time: toUnix(ts),
            position: pat.classification === 'bearish' ? 'aboveBar' : 'belowBar',
            color:
              pat.classification === 'bullish'
                ? '#10b981'
                : pat.classification === 'bearish'
                ? '#ef4444'
                : '#94a3b8',
            shape: pat.classification === 'bullish' ? 'arrowUp' : 'arrowDown',
            text: pat.name,
          })
        }
      })
    }
    if (markers.length > 0) {
      markers.sort((a, b) => Number(a.time) - Number(b.time))
      candleSeries.setMarkers(markers)
    }

    // S/R, FVG & Liquidity horizontal zones
    if (analysis && showLevels) {
      analysis.liquidity.support_resistance.slice(0, 4).forEach((lvl) => {
        candleSeries.createPriceLine({
          price: lvl.price,
          color: lvl.level_type === 'support' ? 'rgba(16,185,129,0.55)' : 'rgba(239,68,68,0.55)',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `${lvl.level_type === 'support' ? 'SUP' : 'RES'} (${lvl.touches}x)`,
        })
      })
      analysis.liquidity.fair_value_gaps
        .filter((f) => !f.filled)
        .slice(-2)
        .forEach((fvg) => {
          const mid = (fvg.gap_low + fvg.gap_high) / 2
          candleSeries.createPriceLine({
            price: mid,
            color: 'rgba(168,85,247,0.5)',
            lineWidth: 1,
            lineStyle: LineStyle.Dotted,
            axisLabelVisible: false,
            title: `FVG (${fvg.direction})`,
          })
        })
    }

    // Trade plan Entry / SL / TP1 / TP2 / TP3 lines
    if (analysis && showTradeLines && analysis.trade_levels.entry_price) {
      const lv = analysis.trade_levels
      if (lv.entry_price) {
        candleSeries.createPriceLine({
          price: lv.entry_price,
          color: '#38bdf8',
          lineWidth: 2,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: 'ENTRY',
        })
      }
      if (lv.stop_loss) {
        candleSeries.createPriceLine({
          price: lv.stop_loss,
          color: '#ef4444',
          lineWidth: 2,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: 'SL',
        })
      }
      if (lv.take_profit_1) {
        candleSeries.createPriceLine({
          price: lv.take_profit_1,
          color: '#10b981',
          lineWidth: 2,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: 'TP1',
        })
      }
      if (lv.take_profit_2) {
        candleSeries.createPriceLine({
          price: lv.take_profit_2,
          color: '#34d399',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: 'TP2',
        })
      }
      if (lv.take_profit_3) {
        candleSeries.createPriceLine({
          price: lv.take_profit_3,
          color: '#6ee7b7',
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: 'TP3',
        })
      }
    }

    chart.timeScale().fitContent()

    const ro = new ResizeObserver((entries) => {
      if (entries[0]) {
        chart.applyOptions({ width: entries[0].contentRect.width })
      }
    })
    ro.observe(el)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [candles, overlays, analysis, theme, decimals, showEma20, showEma50, showEma200, showLevels, showTradeLines])

  const displayCandle = hoverOhlc || candles[candles.length - 1]

  return (
    <div className="rounded-xl border border-terminal-border bg-terminal-panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 border-b border-terminal-border bg-terminal-elevated/60">
        <div className="flex flex-wrap items-center gap-3 text-xs font-mono tabular-nums">
          {displayCandle ? (
            <>
              <span className="text-terminal-muted">O</span>
              <span>{displayCandle.open.toFixed(decimals)}</span>
              <span className="text-terminal-muted">H</span>
              <span className="text-emerald-400">{displayCandle.high.toFixed(decimals)}</span>
              <span className="text-terminal-muted">L</span>
              <span className="text-rose-400">{displayCandle.low.toFixed(decimals)}</span>
              <span className="text-terminal-muted">C</span>
              <span className="font-semibold">{displayCandle.close.toFixed(decimals)}</span>
              {displayCandle.volume != null && (
                <>
                  <span className="text-terminal-muted">V</span>
                  <span>{displayCandle.volume.toLocaleString()}</span>
                </>
              )}
            </>
          ) : (
            <span className="text-terminal-muted">No OHLC data loaded</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {[
            { label: 'EMA 20', active: showEma20, toggle: () => updateSetting('showEma20'), color: 'text-sky-400' },
            { label: 'EMA 50', active: showEma50, toggle: () => updateSetting('showEma50'), color: 'text-amber-400' },
            { label: 'EMA 200', active: showEma200, toggle: () => updateSetting('showEma200'), color: 'text-purple-400' },
            { label: 'S/R & FVG', active: showLevels, toggle: () => updateSetting('showLevels'), color: 'text-emerald-400' },
            { label: 'SL/TP Lines', active: showTradeLines, toggle: () => updateSetting('showTradeLines'), color: 'text-rose-400' },
          ].map((btn) => (
            <button
              key={btn.label}
              onClick={btn.toggle}
              className={`px-2 py-1 rounded border text-[11px] font-medium transition ${
                btn.active
                  ? `border-sky-500/40 bg-sky-500/10 ${btn.color}`
                  : 'border-terminal-border text-terminal-muted opacity-60 hover:opacity-100'
              }`}
            >
              {btn.label}
            </button>
          ))}
        </div>
      </div>

      {candles.length === 0 ? (
        <div className="h-[460px] flex flex-col items-center justify-center p-6 text-center">
          <div className="px-3 py-1 rounded-full bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-semibold mb-3">
            {overview?.connection_status || 'DATA_UNAVAILABLE'}
          </div>
          <p className="text-sm font-medium max-w-md mb-2">
            {overview?.status_message || 'Live market data is unavailable for this symbol and timeframe.'}
          </p>
          <p className="text-xs text-terminal-muted max-w-lg">
            Configure a provider API key in <code>.env</code>, push candles via TradingView Webhook, upload a CSV file, or enable <strong>Demo Historical Mode</strong> to test the analytical engines.
          </p>
        </div>
      ) : (
        <div ref={containerRef} className="w-full h-[460px]" />
      )}
    </div>
  )
}
