'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { apiGet } from '../lib/api'

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
  current_weights?: { coin: string; weight: number; direction?: string }[]
  metadata?: any
  stale?: boolean
  warning?: string
}

type SeriesKey = 'copycat_nav' | 'btc_nav' | 'eth_nav' | 'spx_nav'

function nav(n: any) { return Number(n || 100).toFixed(2) }
function ret(n: any) { const v = Number(n || 0); return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` }
function cls(n: any) { return Number(n || 0) >= 0 ? 'positive' : 'negative' }
function shortDate(ms: any) { if (!ms) return 'Starting now'; return new Date(Number(ms)).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }) }

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
      {btc ? <path d={btc} className="btc" /> : null}
      {eth ? <path d={eth} className="eth" /> : null}
      {spx ? <path d={spx} className="spx" /> : null}
      {copycat ? <path d={copycat} className="copycat" filter="url(#indexGlow)" /> : null}
      {points.length ? <circle cx="640" cy="95" r="0" /> : null}
    </svg>
  </div>
}

export default function PerformanceIndex({ variant = 'dashboard' }: { variant?: 'home' | 'dashboard' }) {
  const [data, setData] = useState<PerfData>({})
  const [err, setErr] = useState('')
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
      const r = await apiGet('/api/performance-index?max_points=240')
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
  const headline = compact
    ? (isBacktest ? '1Y methodology backtest' : 'Live model performance')
    : 'Copycat Index vs BTC / ETH / S&P 500'
  const eyebrow = compact && isBacktest ? 'Copycat 1Y backtest' : 'Copycat live strategy index'
  const dateLine = isBacktest
    ? `Backtested from ${shortDate(data.start_ts_ms)} · USDC margin excluded`
    : `Started ${shortDate(data.start_ts_ms)} · USDC margin excluded · no hindsight`

  return <section className={`cc-index-card ${compact ? 'home' : 'deep'}`}>
    <div className="cc-index-head">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{headline}</h2>
        <span>{dateLine}</span>
      </div>
      <strong className={cls(data.copycat_return_pct)}>{ret(data.copycat_return_pct)}</strong>
    </div>
    <PerformanceChart data={data} compact={compact} />
    <div className="cc-index-metrics">
      <div><small>Copycat</small><b>{nav(data.copycat_nav)}</b><em className={cls(data.copycat_return_pct)}>{ret(data.copycat_return_pct)}</em></div>
      <div><small>BTC</small><b>{nav(data.btc_nav)}</b><em className={cls(data.btc_return_pct)}>{ret(data.btc_return_pct)}</em></div>
      <div><small>ETH</small><b>{nav(data.eth_nav)}</b><em className={cls(data.eth_return_pct)}>{ret(data.eth_return_pct)}</em></div>
      <div><small>S&P 500</small><b>{nav(data.spx_nav)}</b><em className={cls(data.spx_return_pct)}>{ret(data.spx_return_pct)}</em></div>
      {!compact ? <div><small>Max drawdown</small><b>{ret(data.max_drawdown_pct)}</b><em>live model</em></div> : null}
    </div>
    {!compact ? <div className="cc-index-weights"><span>Current model weights</span>{weights.map((w: any) => <i key={w.coin} className={w.direction === 'short' ? 'negative' : 'positive'}>{w.direction === 'short' ? 'SHORT ' : 'LONG '}{w.coin} {(Number(w.weight || 0) * 100).toFixed(0)}%</i>)}</div> : null}
    <p className="cc-index-note">{isBacktest ? 'Simulated historical backtest of the Copycat methodology versus BTC, ETH and the S&P 500. USDC margin is excluded. Backtested performance is not a reliable indicator of future results.' : "Live model performance from Copycat's signed net exposure allocation. USDC margin is excluded; BTC, ETH and the S&P 500 are benchmarks. Includes a fee/slippage buffer. Past performance is not a reliable indicator of future results."}</p>
    {err || data.warning ? <p className="cc-index-warning">{err || data.warning}</p> : null}
  </section>
}
