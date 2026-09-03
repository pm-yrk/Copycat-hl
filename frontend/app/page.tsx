'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import PublicNav from '../components/PublicNav'
import PublicMeshBackdrop from '../components/PublicMeshBackdrop'
import PublicTokenIcon, { canonicalPublicToken } from '../components/PublicTokenIcon'
import { apiGetFresh } from '../lib/api'

const MAX_LIVE_AGE_MS = Number(process.env.NEXT_PUBLIC_PUBLIC_LIVE_MAX_AGE_MS || 5 * 60 * 1000)

type Feed = Record<string, any>
type Perf = Record<string, any>

function compact(n: any) {
  const v = Number(n)
  return Number.isFinite(v) ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'
}
function money(n: any) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  const sign = v < 0 ? '-' : ''
  const a = Math.abs(v)
  if (a >= 1_000_000_000) return `${sign}$${(a / 1_000_000_000).toFixed(1)}b`
  if (a >= 1_000_000) return `${sign}$${(a / 1_000_000).toFixed(1)}m`
  if (a >= 1_000) return `${sign}$${(a / 1_000).toFixed(1)}k`
  return `${sign}$${a.toFixed(0)}`
}
function pct(n: any, digits = 1) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`
}
function freshness(ts: any) {
  const n = Number(ts || 0)
  if (!n) return 'Live feed unavailable'
  const secs = Math.max(0, Math.round((Date.now() - n) / 1000))
  if (secs < 60) return secs < 10 ? 'Updated just now' : `Updated ${secs}s ago`
  const mins = Math.round(secs / 60)
  return mins < 60 ? `Updated ${mins}m ago` : `Updated ${Math.round(mins / 60)}h ago`
}
function isFresh(ts: any) {
  const n = Number(ts || 0)
  return Boolean(n && Math.abs(Date.now() - n) <= MAX_LIVE_AGE_MS)
}
function signalLabel(signal: any) {
  const v = Number(signal || 0)
  const a = Math.abs(v)
  const strength = a >= .75 ? 'Strong' : a >= .45 ? 'Moderate' : 'Light'
  return `${strength} ${v >= 0 ? 'Long' : 'Short'}`
}
function displaySignalValue(row: any) {
  const longUsd = Number(row?.value_long_usd || 0)
  const shortUsd = Number(row?.value_short_usd || 0)
  const total = longUsd + shortUsd
  if (total <= 0) return Number(row?.signal || 0)
  return longUsd >= shortUsd ? longUsd / total : -(shortUsd / total)
}
function rankSignalsLikeDashboard(rows: any[]) {
  const confidenceRank: Record<string, number> = { high: 3, medium: 2, med: 2, low: 1, reserve: 0 }
  const parts = (row: any) => ({
    confidence: confidenceRank[String(row?.confidence || '').toLowerCase()] ?? 0,
    strength: Math.abs(displaySignalValue(row)),
    wallets: Number(row?.wallets_long || 0) + Number(row?.wallets_short || 0),
    net: Math.abs(Number(row?.net_value_usd || 0)),
    gross: Number(row?.value_long_usd || 0) + Number(row?.value_short_usd || 0),
  })
  return [...(rows || [])].sort((a: any, b: any) => {
    const av = parts(a)
    const bv = parts(b)
    return (bv.confidence - av.confidence)
      || (bv.strength - av.strength)
      || (bv.wallets - av.wallets)
      || (bv.net - av.net)
      || (bv.gross - av.gross)
  })
}
function performanceWindow(points: any[], hours = 24) {
  const sorted = [...(points || [])]
    .map((point: any) => ({ ...point, ts_ms: Number(point?.ts_ms || point?.time || 0) }))
    .filter((point: any) => point.ts_ms && Number.isFinite(Number(point.copycat_nav)))
    .sort((a: any, b: any) => a.ts_ms - b.ts_ms)
  if (!sorted.length) return []
  const latest = sorted[sorted.length - 1].ts_ms
  const cutoff = latest - hours * 60 * 60 * 1000
  const windowed = sorted.filter((point: any) => point.ts_ms >= cutoff)
  return windowed.length >= 2 ? windowed : sorted.slice(-2)
}
function performanceReturn(points: any[], key: string) {
  if (points.length < 2) return NaN
  const first = Number(points[0]?.[key])
  const last = Number(points[points.length - 1]?.[key])
  return Number.isFinite(first) && Number.isFinite(last) && first !== 0 ? ((last / first) - 1) * 100 : NaN
}
function sparkPath(points: any[], key: string, width = 260, height = 72) {
  const rows = (points || []).slice(-90).map((p: any) => Number(p?.[key])).filter(Number.isFinite)
  if (rows.length < 2) return ''
  const lo = Math.min(...rows)
  const hi = Math.max(...rows)
  const span = Math.max(hi - lo, .0001)
  return rows.map((v, i) => {
    const x = (i / (rows.length - 1)) * width
    const y = height - ((v - lo) / span) * height
    return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}
function publicTokenColour(symbol: string, index: number) {
  const colours: Record<string, string> = {
    HYPE:'#43e8d0', ETH:'#627eea', BTC:'#f7931a', SOL:'#14f195', ZEC:'#f4b728',
    NEAR:'#00ec97', AAVE:'#8b7dff', TRX:'#ff4b4b', XRP:'#4b9fff', USDC:'#2775ca',
    PUMP:'#61c685', LIT:'#35d0b4', BNB:'#f3ba2f', XLM:'#44bdec',
  }
  const palette = ['#43e8d0','#8057ff','#44bdec','#ffb020','#25d366','#f35ea6','#a6e22e','#ff5b72','#38bdf8','#f97316','#8190a7','#d7a785','#4b9fff']
  return colours[canonicalPublicToken(symbol)] || palette[index % palette.length]
}

function MiniIcon({ type }: { type: 'users' | 'search' | 'pulse' | 'layers' | 'bell' | 'position' | 'allocation' | 'activity' | 'narrative' }) {
  const paths: Record<string, React.ReactNode> = {
    users: <><circle cx="8" cy="7" r="3"/><circle cx="16" cy="8" r="2.4"/><path d="M3 19c.4-4 2.4-6 5-6s4.7 2 5 6M13 14c3.4-.5 5.5 1.2 6 4"/></>,
    search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></>,
    pulse: <path d="M2 13h4l2-6 4 11 3-8 2 3h5"/>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m4 12 8 5 8-5M4 16l8 5 8-5"/></>,
    bell: <><path d="M6 17h12l-2-3V9a4 4 0 0 0-8 0v5l-2 3Z"/><path d="M10 20h4"/></>,
    position: <><path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/></>,
    allocation: <><circle cx="12" cy="12" r="9"/><path d="M12 3v9h9M12 12 6 19"/></>,
    activity: <><path d="M3 12h4l2-6 4 12 3-8 2 2h3"/></>,
    narrative: <><path d="M5 3h10l4 4v14H5z"/><path d="M15 3v5h5M8 12h8M8 16h6"/></>,
  }
  return <svg className="public-icon-svg" viewBox="0 0 24 24" aria-hidden="true">{paths[type]}</svg>
}

export default function Home() {
  const [feed, setFeed] = useState<Feed>({})
  const [perf, setPerf] = useState<Perf>({})
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      const [feedResult, perfResult] = await Promise.allSettled([
        apiGetFresh('/api/dashboard-feed', { timeoutMs: 10000 }),
        apiGetFresh('/api/performance-index?max_points=240', { timeoutMs: 10000 }),
      ])
      if (cancelled) return
      if (feedResult.status === 'fulfilled') setFeed(feedResult.value || {})
      if (perfResult.status === 'fulfilled') setPerf(perfResult.value || {})
      setError(feedResult.status === 'rejected' && perfResult.status === 'rejected' ? 'Live Copycat data is temporarily unavailable.' : '')
    }
    load()
    const id = window.setInterval(load, 30000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [])

  const feedTs = Number(feed?.snapshot_generated_at_ms || feed?.server_time_ms || feed?.summary?.latest_signal_ts_ms || 0)
  const perfTs = Number(perf?.snapshot_generated_at_ms || perf?.latest_ts_ms || 0)
  const feedLive = isFresh(feedTs)
  const perfLive = isFresh(perfTs)
  const summary = feedLive ? (feed?.summary || {}) : {}
  const signals = feedLive && Array.isArray(feed?.signals) ? feed.signals : []
  const targets = feedLive && Array.isArray(feed?.targets) ? feed.targets : []
  const orders = feedLive && Array.isArray(feed?.orders) ? feed.orders : []
  const selected = Number(summary.qualified_wallets || summary.selected_wallet_count || summary.tracked_active_wallets || 0)
  const indexed = Number(summary.indexed_wallets || summary.known_wallet_candidates || summary.registry_wallets || summary.owned_wallets_indexed || summary.scanner_candidate_wallets_scored || 0)
  const rankedSignals = useMemo(() => rankSignalsLikeDashboard(signals), [signals])
  const btc = signals.find((r: any) => String(r?.coin).toUpperCase() === 'BTC') || rankedSignals[0]
  const btcSignal = displaySignalValue(btc)
  const conviction = btc ? Math.round(Math.abs(btcSignal) * 100) : 0
  const isShort = btcSignal < 0
  const symbol = String(btc?.coin || 'BTC').toUpperCase()

  const allocation = useMemo(() => {
    const rows = [...targets]
      .map((target: any) => {
        const coin = canonicalPublicToken(target.coin)
        const weight = Math.abs(Number(target.target_weight ?? target.index_weight ?? 0))
        const direction = String(target.direction || (Number(target.index_weight || 0) < 0 ? 'short' : 'long')).toLowerCase()
        return { coin, signed: direction === 'short' ? -weight : weight, abs: weight, mixed: false }
      })
      .filter((row: any) => row.coin && row.coin !== 'USDC' && row.abs > 0)
      .sort((a: any, b: any) => b.abs - a.abs)

    const top = rows.slice(0, 12)
    const rest = rows.slice(12)
    if (rest.length) {
      const restLong = rest.reduce((sum: number, row: any) => sum + Math.max(row.signed, 0), 0)
      const restShort = rest.reduce((sum: number, row: any) => sum + Math.abs(Math.min(row.signed, 0)), 0)
      top.push({ coin: 'OTHER', signed: restLong - restShort, abs: restLong + restShort, mixed: true })
    }
    return top
  }, [targets])

  const allocationRows = useMemo(() => {
    if (!allocation.length) return [] as (typeof allocation[number] & { percent: number })[]
    const total = allocation.reduce((sum, row) => sum + row.abs, 0) || 1
    const rawTenths = allocation.map(row => (row.abs / total) * 1000)
    const tenths = rawTenths.map(Math.floor)
    let remaining = 1000 - tenths.reduce((sum, value) => sum + value, 0)
    const order = rawTenths.map((value, index) => ({ index, fraction: value - Math.floor(value) })).sort((a, b) => b.fraction - a.fraction)
    for (let i = 0; i < remaining; i++) tenths[order[i % order.length].index] += 1
    return allocation.map((row, index) => ({ ...row, percent: tenths[index] / 10 }))
  }, [allocation])

  const donutStyle = useMemo(() => {
    if (!allocation.length) return {}
    const total = allocation.reduce((sum, row) => sum + row.abs, 0) || 1
    let cursor = 0
    const stops = allocation.map((row, index) => {
      const start = cursor
      cursor += (row.abs / total) * 100
      return `${publicTokenColour(row.coin, index)} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`
    })
    return { background: `conic-gradient(${stops.join(',')})` }
  }, [allocation])

  const perfPoints = perfLive && Array.isArray(perf?.points) ? perf.points : []
  const perf24hPoints = useMemo(() => performanceWindow(perfPoints, 24), [perfPoints])
  const perf24hReturns = useMemo(() => ({
    copycat: performanceReturn(perf24hPoints, 'copycat_nav'),
    btc: performanceReturn(perf24hPoints, 'btc_nav'),
    eth: performanceReturn(perf24hPoints, 'eth_nav'),
  }), [perf24hPoints])
  const perfReady = perfLive && perf24hPoints.length >= 2
  const copycatPath = sparkPath(perf24hPoints, 'copycat_nav')
  const btcPath = sparkPath(perf24hPoints, 'btc_nav')
  const ethPath = sparkPath(perf24hPoints, 'eth_nav')

  const flows = feedLive && Array.isArray(feed?.flow) ? feed.flow : []
  const topAccumulation = [...flows].filter((row: any) => Number(row?.net_value_flow_usd || 0) > 0).sort((a: any, b: any) => Number(b?.net_value_flow_usd || 0) - Number(a?.net_value_flow_usd || 0))[0]
  const topDistribution = [...flows].filter((row: any) => Number(row?.net_value_flow_usd || 0) < 0).sort((a: any, b: any) => Number(a?.net_value_flow_usd || 0) - Number(b?.net_value_flow_usd || 0))[0]
  const telegramLongValue = signals.reduce((sum: number, row: any) => sum + Math.max(0, Number(row?.value_long_usd || 0)), 0)
  const telegramShortValue = signals.reduce((sum: number, row: any) => sum + Math.max(0, Number(row?.value_short_usd || 0)), 0)
  const telegramTotalValue = telegramLongValue + telegramShortValue
  const telegramIsLong = telegramLongValue >= telegramShortValue
  const telegramBias = telegramIsLong ? 'LONG' : 'SHORT'
  const telegramBiasShare = telegramTotalValue > 0 ? Math.round((Math.max(telegramLongValue, telegramShortValue) / telegramTotalValue) * 100) : 0
  const telegramStories = feedLive && Array.isArray(feed?.market_narrative?.stories) ? feed.market_narrative.stories : []
  const telegramStory = telegramStories[0]

  return <div className="public-redesign-root">
    <PublicNav />
    <main className="public-redesign-shell public-home">
      <PublicMeshBackdrop variant="home" />
      <section className="public-home-hero">
        <div className="public-hero-copy">
          <p className="public-eyebrow"><span /> Hyperliquid wallet intelligence</p>
          <h1>See what the<br/>best traders are doing.</h1>
          <p className="public-hero-lede">{selected && feedLive ? <>Copycat tracks <strong>{compact(selected)}</strong> of its highest-ranked Hyperliquid wallets and turns their positions into simple signals anyone can understand.</> : <>Copycat turns the positioning of its ranked Hyperliquid wallet cohort into simple signals anyone can understand.</>}</p>
          <div className="public-live-stats">
            <div><i><MiniIcon type="users"/></i><b>{feedLive && selected ? compact(selected) : '—'}</b><span>top wallets tracked</span></div>
            <div><i><MiniIcon type="search"/></i><b>{feedLive && indexed ? compact(indexed) : '—'}</b><span>wallets analysed</span></div>
            <div><i><MiniIcon type="pulse"/></i><b>{feedLive ? 'Live' : '—'}</b><span>{feedLive ? freshness(feedTs) : 'feed unavailable'}</span></div>
          </div>
        </div>

        <aside className={`public-signal-card ${feedLive && btc ? '' : 'is-unavailable'}`}>
          <header><span>What top wallets are doing</span><em className={feedLive ? 'live' : ''}>{feedLive ? 'LIVE' : 'UNAVAILABLE'}</em></header>
          {feedLive && btc ? <>
            <div className="public-signal-title"><PublicTokenIcon symbol={symbol} className="public-token-icon-large"/><h2>{symbol}</h2><span className={isShort ? 'short' : 'long'}>{signalLabel(btcSignal)}</span></div>
            <div className="public-signal-metrics"><div><span>Long</span><b className="positive">{compact(btc.wallets_long)}</b></div><div><span>Short</span><b className="negative">{compact(btc.wallets_short)}</b></div><div><span>Net positioning</span><b className={Number(btc.net_value_usd || 0) < 0 ? 'negative' : 'positive'}>{money(btc.net_value_usd)}</b></div></div>
            <div className="public-bias-row"><div><span>{isShort ? 'Short' : 'Long'} bias</span><b className={isShort ? 'negative' : 'positive'}>{conviction}% {isShort ? 'Short' : 'Long'}</b></div><em>{conviction}%</em></div>
            <div className="public-bias-track"><i className={isShort ? 'short' : 'long'} style={{ width: `${Math.max(2, conviction)}%` }} /></div>
            <div className="public-meaning"><strong>What this means</strong><p>Top tracked wallets are leaning <b>{isShort ? 'bearish' : 'bullish'}</b> on {symbol} right now. They have more capital positioned {isShort ? 'short than long' : 'long than short'}.</p></div>
            <small>{freshness(btc.ts_ms || feedTs)}</small>
          </> : <div className="public-data-empty"><b>Waiting for a fresh Copycat snapshot.</b><span>Old bundled data is never shown here as live.</span></div>}
        </aside>
      </section>

      <section id="how-it-works" className="public-steps">
        <article><div className="public-step-icon"><MiniIcon type="users"/></div><span>01</span><h3>Find the best traders</h3><p>Copycat ranks wallets using profitability, consistency, scale and risk-aware quality checks.</p></article>
        <article><div className="public-step-icon"><MiniIcon type="layers"/></div><span>02</span><h3>Combine their positions</h3><p>We aggregate their long and short exposure into one readable market view and model allocation.</p></article>
        <article><div className="public-step-icon"><MiniIcon type="bell"/></div><span>03</span><h3>Watch when they change</h3><p>Live snapshots reveal conviction shifts, accumulation, distribution and changes in positioning.</p></article>
      </section>

      <section className="public-portfolio-section">
        <div className="public-section-heading"><p className="public-eyebrow"><span/> Copycat model</p><h2>One portfolio. Based on {feedLive && selected ? `all ${compact(selected)} wallets.` : 'the tracked cohort.'}</h2><p>The Copycat Index converts signed net exposure into a model portfolio. USDC margin is excluded from allocation.</p></div>
        <div className="public-portfolio-grid">
          <article className="public-performance-card">
            <header><div><span>Model performance</span><small>Last 24 hours • {perfLive ? freshness(perfTs) : 'Fresh index data unavailable'}</small></div><em className={perfReady ? 'live' : ''}>{perfReady ? '24H LIVE' : 'UNAVAILABLE'}</em></header>
            {perfReady ? <div className="public-perf-tiles">
              <div><span><i className="public-index-mark">◇</i>Copycat Index</span><b className={perf24hReturns.copycat >= 0 ? 'positive' : 'negative'}>{pct(perf24hReturns.copycat)}</b><svg viewBox="0 0 260 72" preserveAspectRatio="none"><path d={copycatPath}/></svg><small className="public-perf-axis"><em>24h ago</em><em>Now</em></small></div>
              <div><span><PublicTokenIcon symbol="BTC"/>BTC</span><b className={perf24hReturns.btc >= 0 ? 'positive' : 'negative'}>{pct(perf24hReturns.btc)}</b><svg viewBox="0 0 260 72" preserveAspectRatio="none"><path d={btcPath}/></svg><small className="public-perf-axis"><em>24h ago</em><em>Now</em></small></div>
              <div><span><PublicTokenIcon symbol="ETH"/>ETH</span><b className={perf24hReturns.eth >= 0 ? 'positive' : 'negative'}>{pct(perf24hReturns.eth)}</b><svg viewBox="0 0 260 72" preserveAspectRatio="none"><path d={ethPath}/></svg><small className="public-perf-axis"><em>24h ago</em><em>Now</em></small></div>
            </div> : <div className="public-data-empty"><b>Waiting for a complete 24-hour performance window.</b><span>No unclear all-time percentage is substituted.</span></div>}
          </article>
          <article className="public-allocation-card">
            <header><div><span>Current allocation</span><small>Same live targets as dashboard • 100% gross</small></div><em className={feedLive ? 'live' : ''}>{feedLive ? 'LIVE' : 'UNAVAILABLE'}</em></header>
            {feedLive && allocationRows.length ? <div className="public-allocation-body"><div className="public-donut" style={donutStyle}><i><span>MODEL</span><b>{compact(selected)}</b><small>wallets</small></i></div><div className="public-allocation-list">{allocationRows.map((row, index) => <div key={row.coin}><i data-n={index} style={{ background: publicTokenColour(row.coin, index) }}/><PublicTokenIcon symbol={row.coin}/><b>{row.coin === 'OTHER' ? 'Other' : row.coin}</b><span className={row.mixed ? '' : row.signed < 0 ? 'negative' : 'positive'}>{row.mixed ? `${row.percent.toFixed(1)}% mixed` : `${row.signed < 0 ? '-' : '+'}${row.percent.toFixed(1)}%`}</span></div>)}</div></div> : <div className="public-data-empty"><b>Waiting for fresh allocation data.</b><span>Negative means short. Positive means long.</span></div>}
            <p>Exact dashboard target weights <span>•</span> USDC margin excluded <span>•</span> Absolute weights total 100%</p>
          </article>
        </div>
      </section>

      <section className="public-product-preview">
        <div className="public-product-copy"><p className="public-eyebrow"><span/> Live dashboard</p><h2>Everything important. One screen.</h2><p>A high-fidelity live preview using the same dashboard feed—not invented sales-demo figures.</p></div>
        <div className="public-dashboard-mini">
          <div className="public-dashboard-framebar"><span><i/><i/><i/></span><b>Copycat dashboard preview</b><em className={feedLive ? 'live' : ''}>{feedLive ? 'LIVE DATA' : 'UNAVAILABLE'}</em></div>
          {feedLive && signals.length ? <div className="public-dashboard-shot">
            <header className="public-shot-nav"><b><span>Copy</span><em>cat</em></b><nav>Overview&nbsp;&nbsp; Positions&nbsp;&nbsp; Activity&nbsp;&nbsp; Performance</nav><small>{freshness(feedTs)}</small></header>
            <div className="public-shot-kpis">
              <article><small>Copycat-ranked wallets</small><b>{compact(selected)}</b><span>{compact(indexed)} indexed</span></article>
              <article><small>Tracked wallet value</small><b>{money(summary.tracked_total_wallet_value_usd ?? summary.tracked_account_value_usd)}</b><span>{compact(summary.wallets_with_complete_total_value || 0)}/{compact(selected)} fully valued</span></article>
              <article><small>Open position value</small><b>{money(summary.tracked_open_position_value_usd)}</b><span>{compact(summary.open_positions || 0)} live positions</span></article>
              <article><small>Assets with signals</small><b>{compact(summary.assets_with_signals || signals.length)}</b><span>cross-asset breadth</span></article>
            </div>
            <div className="public-shot-grid">
              <article className="public-shot-allocation"><header><b>Portfolio allocation</b><span>USDC excluded</span></header><div><div className="public-shot-donut" style={donutStyle}><i>100%</i></div><div className="public-shot-allocation-list">{allocationRows.slice(0,5).map((row,index)=><span key={row.coin}><PublicTokenIcon symbol={row.coin}/><b>{row.coin}</b><em className={row.signed < 0 ? 'negative' : 'positive'}>{row.signed < 0 ? 'short' : 'long'} {row.percent.toFixed(0)}%</em></span>)}</div></div></article>
              <article className="public-shot-signals"><header><b>Asset signal board</b><span>live conviction</span></header><div>{rankedSignals.slice(0,5).map((row:any,index:number)=>{const value=displaySignalValue(row);return <span key={row.coin}><i>{index+1}</i><PublicTokenIcon symbol={row.coin}/><b>{row.coin}</b><em className={value < 0 ? 'negative' : 'positive'}>{Math.round(Math.abs(value)*100)}% {value < 0 ? 'Short' : 'Long'}</em><small>{money(row.net_value_usd)}</small></span>})}</div></article>
              <article className="public-shot-performance"><header><b>Model performance</b><span>Last 24 hours</span></header>{perfReady ? <><div className="public-shot-chart"><svg viewBox="0 0 260 72" preserveAspectRatio="none"><path d={copycatPath}/></svg></div><div className="public-shot-performance-legend"><span><i className="public-index-mark">◇</i>Copycat <b className={perf24hReturns.copycat < 0 ? 'negative' : 'positive'}>{pct(perf24hReturns.copycat)}</b></span><span><PublicTokenIcon symbol="BTC"/>BTC <b className={perf24hReturns.btc < 0 ? 'negative' : 'positive'}>{pct(perf24hReturns.btc)}</b></span><span><PublicTokenIcon symbol="ETH"/>ETH <b className={perf24hReturns.eth < 0 ? 'negative' : 'positive'}>{pct(perf24hReturns.eth)}</b></span></div></> : <div className="public-data-empty"><b>24h window warming up.</b></div>}</article>
            </div>
            <div className="public-shot-orders"><header><b>Most recent orders</b><span>same live cohort as dashboard</span></header><div>{orders.slice(0,3).map((row:any,index:number)=><span key={`${row.wallet}-${row.ts_ms}-${index}`}><PublicTokenIcon symbol={row.coin || row.asset}/><b>{row.coin || row.asset}</b><em className={String(row.side).toLowerCase().includes('short')?'negative':'positive'}>{row.side || 'Order'}</em><small>{String(row.wallet_label || row.wallet || 'Wallet').replace(/^(.{8}).*(.{4})$/, '$1…$2')}</small><strong>{money(row.delta_value_usd || row.position_value_usd)}</strong></span>)}</div></div>
          </div> : <div className="public-data-empty"><b>Fresh dashboard snapshot unavailable.</b><span>The preview never substitutes made-up data.</span></div>}
        </div>
        <div className="public-telegram-preview">
          <div className="public-telegram-copy">
            <p className="public-eyebrow"><span/> Telegram intelligence</p>
            <h3>The market comes to you.</h3>
            <p>Get one clean hourly pulse, then immediate alerts only when the smart-wallet data, large orders, news or catalysts genuinely change.</p>
            <div className="public-telegram-points">
              <span><i>🕐</i><b>Hourly market pulse</b><small>The important positioning, signals and flows in one message.</small></span>
              <span><i>⚡</i><b>Meaningful instant alerts</b><small>Large moves and breaking events—not constant notification noise.</small></span>
              <span><i>🐋</i><b>Built from the live dashboard</b><small>The same Copycat intelligence, formatted for Telegram.</small></span>
            </div>
          </div>
          <div className="public-telegram-window">
            <header><span className="public-telegram-avatar">C</span><div><b>Copycat Intelligence</b><small>Telegram alert preview</small></div><em>•••</em></header>
            <div className="public-telegram-chat">
              {feedLive && rankedSignals.length ? <article className="public-telegram-bubble">
                <strong>🐈 COPYCAT MARKET PULSE</strong>
                {telegramTotalValue > 0 ? <section><b>📊 MARKET POSITIONING</b><span className={telegramIsLong ? 'positive' : 'negative'}>{telegramIsLong ? '🟢' : '🔴'} {telegramBiasShare}% {telegramBias} by tracked value</span><small>🟢 Long {money(telegramLongValue)}&nbsp;&nbsp;·&nbsp;&nbsp;🔴 Short {money(telegramShortValue)}</small></section> : null}
                <section><b>🎯 STRONGEST SIGNALS</b>{rankedSignals.slice(0,3).map((row:any)=>{const value=displaySignalValue(row);return <span key={row.coin} className={value < 0 ? 'negative' : 'positive'}>{value < 0 ? '🔴' : '🟢'} {row.coin} — {value < 0 ? 'SHORT' : 'LONG'} {Math.round(Math.abs(value)*100)}%</span>})}</section>
                {topAccumulation || topDistribution ? <section><b>🐋 SMART-WALLET FLOWS</b>{topAccumulation ? <span>🟢 {topAccumulation.coin}: {Math.max(0,Number(topAccumulation.net_buyer_count||0))} more wallets buying · +{money(Math.abs(Number(topAccumulation.net_value_flow_usd||0)))}</span> : null}{topDistribution ? <span>🔴 {topDistribution.coin}: {Math.abs(Math.min(0,Number(topDistribution.net_buyer_count||0)))} more wallets selling · {money(Number(topDistribution.net_value_flow_usd||0))}</span> : null}</section> : null}
                {allocationRows.length ? <section><b>🧭 COPYCAT ALLOCATION</b><span>{allocationRows.slice(0,3).map(row=>`${row.coin} ${row.signed < 0 ? '-' : '+'}${row.percent.toFixed(1)}%`).join('  ·  ')}</span></section> : null}
                {telegramStory ? <section><b>🗞️ MARKET NEWS</b><span>{telegramStory.source || 'Market source'} — {String(telegramStory.title || '').slice(0,120)}</span></section> : null}
              </article> : <article className="public-telegram-bubble public-telegram-empty"><strong>🐈 COPYCAT MARKET PULSE</strong><span>Live alert example will appear with the next dashboard snapshot.</span></article>}
            </div>
            <footer><i/><span>Live example using the current Copycat dashboard feed</span></footer>
          </div>
        </div>

        <div className="public-feature-list">
          <div><i><MiniIcon type="position"/></i><span><b>Market positioning</b><small>See where tracked wallets are long, short, and by how much.</small></span></div>
          <div><i><MiniIcon type="allocation"/></i><span><b>Copycat allocation</b><small>Understand the exact live model portfolio and net exposure.</small></span></div>
          <div><i><MiniIcon type="activity"/></i><span><b>Wallet activity</b><small>Track meaningful position changes as they arrive.</small></span></div>
          <div><i><MiniIcon type="narrative"/></i><span><b>Market narrative</b><small>Plain-English context for what is driving the numbers.</small></span></div>
        </div>
      </section>

      {error ? <div className="public-live-warning">{error}</div> : null}
      <footer className="public-disclaimer"><span>◇</span><p><b>Market intelligence only, not financial advice.</b> Crypto trading can result in loss. Top-wallet claims are scoped to Copycat’s indexed Hyperliquid universe.</p><Link href="/risk-disclaimer">Learn more →</Link></footer>
    </main>
  </div>
}
