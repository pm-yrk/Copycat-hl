'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { apiGet } from '../lib/api'
const COPYCAT_PERFORMANCE_POLL_MS = Number(process.env.NEXT_PUBLIC_PERFORMANCE_POLL_MS || 300000)


type Point = {
  ts_ms: number
  copycat_nav: number
  btc_nav: number
  eth_nav: number
  spx_nav?: number
  live?: boolean
}

type PerfData = {
  status?: string
  mode?: 'live' | 'backtest'
  start_ts_ms?: number
  latest_ts_ms?: number
  copycat_nav?: number
  btc_nav?: number
  eth_nav?: number
  spx_nav?: number
  copycat_return_pct?: number
  btc_return_pct?: number
  eth_return_pct?: number
  spx_return_pct?: number
  max_drawdown_pct?: number
  points?: Point[]
  timeframes?: Partial<Record<TimeframeKey, Point[]>>
  current_weights?: { coin: string; weight: number; direction?: string }[]
  metadata?: any
  stale?: boolean
  warning?: string
}

type SeriesKey = 'copycat_nav' | 'btc_nav' | 'eth_nav' | 'spx_nav'

const INDEX_COLOURS = {
  copycat: '#23E99D',
  btc: '#FFB020',
  eth: '#6EA8FF',
  spx: '#4169E1',
} as const

function LegendDot({ color }: { color: string }) {
  return <span aria-hidden="true" style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 999, background: color, marginRight: 6, boxShadow: `0 0 10px ${color}` }} />
}

function nav(n: any) { return Number(n || 100).toFixed(2) }
function ret(n: any) { const v = Number(n || 0); return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` }
function cls(n: any) { return Number(n || 0) >= 0 ? 'positive' : 'negative' }
function shortDate(ms: any) { if (!ms) return 'Starting now'; return new Date(Number(ms)).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }) }

function normalisePerfPoint(p: any): Point {
  return {
    ...p,
    ts_ms: Number(p?.ts_ms || p?.time || Date.now()),
    copycat_nav: Number(p?.copycat_nav ?? p?.copycat ?? 100),
    btc_nav: Number(p?.btc_nav ?? p?.btc ?? 100),
    eth_nav: Number(p?.eth_nav ?? p?.eth ?? 100),
    spx_nav: Number(p?.spx_nav ?? p?.spx ?? 100),
  }
}
function normalisePerfData(raw: any): PerfData {
  const points = Array.isArray(raw?.points) ? raw.points.map(normalisePerfPoint) : []
  const last = points[points.length - 1] || {}
  return {
    ...(raw || {}),
    points,
    start_ts_ms: Number(raw?.start_ts_ms || points[0]?.ts_ms || 0),
    latest_ts_ms: Number(raw?.latest_ts_ms || raw?.updated_at_ms || last?.ts_ms || 0),
    copycat_nav: Number(raw?.copycat_nav ?? last?.copycat_nav ?? 100),
    btc_nav: Number(raw?.btc_nav ?? last?.btc_nav ?? 100),
    eth_nav: Number(raw?.eth_nav ?? last?.eth_nav ?? 100),
    spx_nav: Number(raw?.spx_nav ?? last?.spx_nav ?? 100),
    copycat_return_pct: Number(raw?.copycat_return_pct ?? (Number(raw?.copycat_nav ?? last?.copycat_nav ?? 100) - 100)),
    btc_return_pct: Number(raw?.btc_return_pct ?? (Number(raw?.btc_nav ?? last?.btc_nav ?? 100) - 100)),
    eth_return_pct: Number(raw?.eth_return_pct ?? (Number(raw?.eth_nav ?? last?.eth_nav ?? 100) - 100)),
    spx_return_pct: Number(raw?.spx_return_pct ?? (Number(raw?.spx_nav ?? last?.spx_nav ?? 100) - 100)),
  }
}


function chartDomain(points: Point[]) {
  const vals: number[] = []
  points.forEach((p: any) => {
    ;(['copycat_nav', 'btc_nav', 'eth_nav', 'spx_nav'] as SeriesKey[]).forEach((key) => {
      const v = Number(p[key])
      if (Number.isFinite(v) && v > 0) vals.push(v)
    })
  })
  if (!vals.length) vals.push(100)
  const min = Math.min(...vals, 100) * 0.995
  const max = Math.max(...vals, 100) * 1.005
  return { min, max, span: Math.max(max - min, 0.0001) }
}

function makePath(points: Point[], key: SeriesKey, domain: { min: number; span: number }, width = 640, height = 190) {
  if (!points.length) return ''
  return points.map((p: any, i) => {
    const x = points.length === 1 ? 0 : (i / (points.length - 1)) * width
    const y = height - ((Number(p[key] || 100) - domain.min) / domain.span) * height
    return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
  }).join(' ')
}



type TimeframeKey = '1D' | '1W' | '1M' | 'YTD' | '1Y' | 'ALL'
const TIMEFRAME_KEYS: TimeframeKey[] = ['1D', '1W', '1M', 'YTD', '1Y', 'ALL']

function fallbackTimeframePoints(data: PerfData, range: TimeframeKey): Point[] {
  const points = (data.points || []).map(normalisePerfPoint)
  if (!points.length || range === 'ALL') return points
  const now = Number(data.latest_ts_ms || points[points.length - 1]?.ts_ms || Date.now())
  const day = 24 * 60 * 60 * 1000
  let cutoff = 0
  if (range === '1D') cutoff = now - day
  if (range === '1W') cutoff = now - 7 * day
  if (range === '1M') cutoff = now - 30 * day
  if (range === '1Y') cutoff = now - 365 * day
  if (range === 'YTD') {
    const d = new Date(now)
    cutoff = Date.UTC(d.getUTCFullYear(), 0, 1)
  }
  const filtered = points.filter((p) => p.ts_ms >= cutoff)
  return filtered.length ? filtered : points
}

function selectTimeframe(data: PerfData, range: TimeframeKey): PerfData {
  const supplied = Array.isArray(data.timeframes?.[range]) ? data.timeframes?.[range] || [] : []
  const points = (supplied.length ? supplied : fallbackTimeframePoints(data, range)).map(normalisePerfPoint)
  if (!points.length) return data
  const first = points[0]
  const last = points[points.length - 1]
  const periodReturn = (key: SeriesKey) => {
    const start = Number(first?.[key] || 0)
    const end = Number(last?.[key] || 0)
    return start > 0 && end > 0 ? ((end / start) - 1) * 100 : 0
  }
  let peak = Number(first.copycat_nav || 100)
  let maxDrawdown = 0
  for (const point of points) {
    const value = Number(point.copycat_nav || 0)
    if (value > peak) peak = value
    if (peak > 0 && value > 0) maxDrawdown = Math.min(maxDrawdown, ((value / peak) - 1) * 100)
  }
  return {
    ...data,
    points,
    latest_ts_ms: points[points.length - 1].ts_ms,
    copycat_nav: last.copycat_nav,
    btc_nav: last.btc_nav,
    eth_nav: last.eth_nav,
    spx_nav: last.spx_nav,
    copycat_return_pct: periodReturn('copycat_nav'),
    btc_return_pct: periodReturn('btc_nav'),
    eth_return_pct: periodReturn('eth_nav'),
    spx_return_pct: periodReturn('spx_nav'),
    max_drawdown_pct: maxDrawdown,
  }
}
function PerformanceChart({ data, compact = false }: { data: PerfData; compact?: boolean }) {
  const points = (data.points || []).filter((p: any) => Number.isFinite(Number(p.copycat_nav)))
  const domain = chartDomain(points)
  const copycat = makePath(points, 'copycat_nav', domain)
  const btc = makePath(points, 'btc_nav', domain)
  const eth = makePath(points, 'eth_nav', domain)
  const spx = makePath(points, 'spx_nav', domain)
  return <div className={`cc-index-chart ${compact ? 'compact' : ''}`}>
    <svg viewBox="0 0 640 190" preserveAspectRatio="none" aria-label="Copycat Index versus BTC, ETH and S&P 500">
      <defs>
        <linearGradient id="copycatIndexFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="rgba(35,233,157,.38)"/><stop offset="100%" stopColor="rgba(35,233,157,0)"/></linearGradient>
        <filter id="indexGlow"><feGaussianBlur stdDeviation="4" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      </defs>
      {copycat ? <path d={`${copycat} L 640 190 L 0 190 Z`} fill="url(#copycatIndexFill)" opacity=".75" /> : null}
      {btc ? <path d={btc} className="btc" style={{ fill: 'none', stroke: INDEX_COLOURS.btc, strokeWidth: 3, strokeLinecap: 'round', strokeLinejoin: 'round', strokeDasharray: 'none', vectorEffect: 'non-scaling-stroke', opacity: 1, filter: 'drop-shadow(0 0 7px rgba(255,176,32,.72))' }} /> : null}
      {eth ? <path d={eth} className="eth" style={{ fill: 'none', stroke: INDEX_COLOURS.eth, strokeWidth: 3, strokeLinecap: 'round', strokeLinejoin: 'round', strokeDasharray: 'none', vectorEffect: 'non-scaling-stroke', opacity: 1, filter: 'drop-shadow(0 0 7px rgba(110,168,255,.72))' }} /> : null}
      {copycat ? <path d={copycat} className="copycat" style={{ fill: 'none', stroke: INDEX_COLOURS.copycat, strokeWidth: 4, strokeLinecap: 'round', strokeLinejoin: 'round', strokeDasharray: 'none', vectorEffect: 'non-scaling-stroke', opacity: 1, filter: 'drop-shadow(0 0 10px rgba(35,233,157,.82))' }} /> : null}
      {spx ? <path d={spx} className="spx" style={{ fill: 'none', stroke: INDEX_COLOURS.spx, strokeWidth: 3, strokeLinecap: 'round', strokeLinejoin: 'round', strokeDasharray: 'none', vectorEffect: 'non-scaling-stroke', opacity: 1, filter: 'drop-shadow(0 0 8px rgba(65,105,225,.78))' }} /> : null}
      {points.length ? <circle cx="640" cy="95" r="0" /> : null}
    </svg>
  </div>
}

export default function PerformanceIndex({ variant = 'dashboard' }: { variant?: 'home' | 'dashboard' }) {
  const [data, setData] = useState<PerfData>({})
  const [err, setErr] = useState('')
  const [range, setRange] = useState<TimeframeKey>('ALL')
  const inFlight = useRef(false)
  const compact = variant === 'home'

  async function load() {
    if (inFlight.current) return
    inFlight.current = true
    try {
      if (compact) {
        const backtest = await apiGet('/api/performance-backtest')
        if ((backtest?.points || []).length) {
          setData(backtest || {})
          setErr('')
          return
        }
        const live = await apiGet('/api/performance-index?max_points=120')
        setData({ ...(live || {}), mode: 'live', warning: backtest?.warning || live?.warning })
        setErr('')
        return
      }
      const r = await apiGet('/api/performance-index?max_points=5000')
      setData({ ...(r || {}), mode: 'live' })
      setErr('')
    } catch (e: any) {
      if (!data.points?.length) setErr('Performance index is warming up…')
    } finally {
      inFlight.current = false
    }
  }

  useEffect(() => { load(); const id = setInterval(load, compact ? 30000 : 10000); return () => clearInterval(id) }, [])

  const weights = useMemo(() => (data.current_weights || []).slice(0, 5), [data.current_weights])
  const isBacktest = data.mode === 'backtest' && (data.points || []).length > 0
  const viewData = isBacktest ? data : selectTimeframe(data, range)
  const headline = compact
    ? (isBacktest ? '1Y methodology backtest' : 'Live model performance')
    : 'Copycat Index vs BTC / ETH / S&P 500'
  const eyebrow = compact && isBacktest ? 'Copycat 1Y backtest' : 'Copycat live strategy index'
  const dateLine = isBacktest
    ? `Backtested from ${shortDate(data.start_ts_ms)} | USDC margin excluded`
    : range === 'ALL'
      ? `Live history from ${shortDate(data.start_ts_ms)} | protected archive | no hindsight`
      : `${range} window | selected-period returns and drawdown | no hindsight`

  return <section className={`cc-index-card ${compact ? 'home' : 'deep cc-index-dashboard-fit'}`}>
    <div className="cc-index-head">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{headline}</h2>
        <span>{dateLine}</span>
      </div>
      <strong className={cls(viewData.copycat_return_pct)}>{ret(viewData.copycat_return_pct)}</strong>
    </div>
    {!compact ? <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '8px 0 10px' }} aria-label="Performance timeframe">
      {TIMEFRAME_KEYS.map((key) => <button key={key} type="button" aria-pressed={range === key} onClick={() => setRange(key)} style={{ border: range === key ? '1px solid rgba(35,233,157,.7)' : '1px solid rgba(148,163,184,.28)', background: range === key ? 'rgba(35,233,157,.12)' : 'transparent', color: 'inherit', borderRadius: 999, padding: '5px 10px', cursor: 'pointer', font: 'inherit', fontSize: 12, fontWeight: 700 }}>{key}</button>)}
    </div> : null}
    <PerformanceChart data={viewData} compact={compact} />
    <div className="cc-index-metrics">
      <div><small><LegendDot color={INDEX_COLOURS.copycat} />Copycat</small><b>{nav(viewData.copycat_nav)}</b><em className={cls(viewData.copycat_return_pct)}>{ret(viewData.copycat_return_pct)}</em></div>
      <div><small><LegendDot color={INDEX_COLOURS.btc} />BTC</small><b>{nav(viewData.btc_nav)}</b><em className={cls(viewData.btc_return_pct)}>{ret(viewData.btc_return_pct)}</em></div>
      <div><small><LegendDot color={INDEX_COLOURS.eth} />ETH</small><b>{nav(viewData.eth_nav)}</b><em className={cls(viewData.eth_return_pct)}>{ret(viewData.eth_return_pct)}</em></div>
      <div><small><LegendDot color={INDEX_COLOURS.spx} />S&P 500</small><b>{nav(viewData.spx_nav)}</b><em className={cls(viewData.spx_return_pct)}>{ret(viewData.spx_return_pct)}</em></div>
      {!compact ? <div><small>Max drawdown</small><b>{ret(viewData.max_drawdown_pct)}</b><em>live model</em></div> : null}
    </div>
    {!compact ? <div className="cc-index-weights"><span>Current model weights</span>{weights.map((w: any) => <i key={w.coin} className={w.direction === 'short' ? 'negative' : 'positive'}>{w.direction === 'short' ? 'SHORT ' : 'LONG '}{w.coin} {(Number(w.weight || 0) * 100).toFixed(0)}%</i>)}</div> : null}
    <p className="cc-index-note">{isBacktest ? 'Simulated historical backtest of the Copycat methodology versus BTC, ETH and an S&P 500 benchmark. USDC margin is excluded. The S&P 500 benchmark is represented by the Hyperliquid Trade[XYZ] SP500 perpetual market for comparison; Copycat is not affiliated with S&P Dow Jones Indices or Trade[XYZ]. Backtested performance is not a reliable indicator of future results.' : "Live model performance from Copycat's signed net exposure allocation. USDC margin is excluded; BTC, ETH and S&P 500 are comparison benchmarks. The S&P 500 benchmark is represented by the Hyperliquid Trade[XYZ] SP500 perpetual market; Copycat is not affiliated with S&P Dow Jones Indices or Trade[XYZ]. Includes a fee/slippage buffer. Past performance is not a reliable indicator of future results."}</p>
    {err || data.warning ? <p className="cc-index-warning">{err || data.warning}</p> : null}
  </section>
}
