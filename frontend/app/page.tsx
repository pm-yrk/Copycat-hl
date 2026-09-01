'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import PublicNav from '../components/PublicNav'
import PublicMeshBackdrop from '../components/PublicMeshBackdrop'
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
  const selected = Number(summary.selected_wallet_count || summary.qualified_wallets || summary.tracked_active_wallets || 0)
  const indexed = Number(summary.indexed_wallets || summary.known_wallet_candidates || summary.scanner_candidate_wallets_scored || 0)
  const btc = signals.find((r: any) => String(r?.coin).toUpperCase() === 'BTC') || signals[0]
  const conviction = btc ? Math.round(Math.abs(Number(btc.signal || 0)) * 100) : 0
  const isShort = Number(btc?.signal || 0) < 0
  const symbol = String(btc?.coin || 'BTC').toUpperCase()

  const allocation = useMemo(() => {
    if (!targets.length) return [] as { coin: string; signed: number; abs: number; mixed?: boolean }[]
    const sorted = targets.map((t: any) => ({ coin: String(t.coin || '').toUpperCase(), signed: Number(t.index_weight ?? (String(t.direction).toLowerCase() === 'short' ? -Math.abs(Number(t.target_weight || 0)) : Math.abs(Number(t.target_weight || 0)))) }))
      .filter((t: any) => t.coin && Number.isFinite(t.signed))
      .sort((a: any, b: any) => Math.abs(b.signed) - Math.abs(a.signed))
    const top = sorted.slice(0, 4).map((t: any) => ({ ...t, abs: Math.abs(t.signed), mixed: false }))
    const rest = sorted.slice(4)
    if (rest.length) {
      const restLong = rest.reduce((a: number, t: any) => a + Math.max(t.signed, 0), 0)
      const restShort = rest.reduce((a: number, t: any) => a + Math.abs(Math.min(t.signed, 0)), 0)
      top.push({ coin: 'Other', signed: restLong - restShort, abs: restLong + restShort, mixed: restLong > 0 && restShort > 0 })
    }
    return top
  }, [targets])

  const allocationRows = useMemo(() => {
    if (!allocation.length) return [] as (typeof allocation[number] & { percent: number })[]
    const total = allocation.reduce((a, x) => a + x.abs, 0) || 1
    const rawTenths = allocation.map(x => (x.abs / total) * 1000)
    const tenths = rawTenths.map(Math.floor)
    let remaining = 1000 - tenths.reduce((a, n) => a + n, 0)
    const order = rawTenths.map((n, i) => ({ i, fraction: n - Math.floor(n) })).sort((a, b) => b.fraction - a.fraction)
    for (let i = 0; i < remaining; i++) tenths[order[i % order.length].i] += 1
    return allocation.map((x, i) => ({ ...x, percent: tenths[i] / 10 }))
  }, [allocation])

  const donutStyle = useMemo(() => {
    if (!allocation.length) return {}
    const total = allocation.reduce((a, x) => a + x.abs, 0) || 1
    const colors = ['#ff6178', '#7d75ff', '#23e99d', '#39dce8', '#8190a7']
    let cursor = 0
    const stops = allocation.map((x, i) => {
      const start = cursor
      cursor += (x.abs / total) * 100
      return `${colors[i % colors.length]} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`
    })
    return { background: `conic-gradient(${stops.join(',')})` }
  }, [allocation])

  const perfPoints = perfLive && Array.isArray(perf?.points) ? perf.points : []
  const copycatPath = sparkPath(perfPoints, 'copycat_nav')
  const btcPath = sparkPath(perfPoints, 'btc_nav')
  const ethPath = sparkPath(perfPoints, 'eth_nav')

  return <div className="public-redesign-root">
    <PublicNav />
    <main className="public-redesign-shell public-home">
      <PublicMeshBackdrop variant="home" />
      <section className="public-home-hero">
        <div className="public-hero-copy">
          <p className="public-eyebrow"><span /> Hyperliquid wallet intelligence</p>
          <h1>See what the<br/>best traders are doing.</h1>
          <p className="public-hero-lede">{selected && feedLive ? <>Copycat tracks <strong>{compact(selected)}</strong> of its highest-ranked Hyperliquid wallets and turns their positions into simple signals anyone can understand.</> : <>Copycat turns the positioning of its ranked Hyperliquid wallet cohort into simple signals anyone can understand.</>}</p>
          <div className="public-actions"><Link className="public-primary" href="/dashboard">Open live dashboard <span>→</span></Link><a className="public-secondary" href="#how-it-works">How Copycat works</a></div>
          <div className="public-live-stats">
            <div><i><MiniIcon type="users"/></i><b>{feedLive && selected ? compact(selected) : '—'}</b><span>top wallets tracked</span></div>
            <div><i><MiniIcon type="search"/></i><b>{feedLive && indexed ? compact(indexed) : '—'}</b><span>wallets analysed</span></div>
            <div><i><MiniIcon type="pulse"/></i><b>{feedLive ? 'Live' : '—'}</b><span>{feedLive ? freshness(feedTs) : 'feed unavailable'}</span></div>
          </div>
        </div>

        <aside className={`public-signal-card ${feedLive && btc ? '' : 'is-unavailable'}`}>
          <header><span>What top wallets are doing</span><em className={feedLive ? 'live' : ''}>{feedLive ? 'LIVE' : 'UNAVAILABLE'}</em></header>
          {feedLive && btc ? <>
            <div className="public-signal-title"><div className={`public-token-mark ${symbol === 'BTC' ? 'btc' : ''}`}>{symbol.slice(0, 1)}</div><h2>{symbol}</h2><span className={isShort ? 'short' : 'long'}>{signalLabel(btc.signal)}</span></div>
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
            <header><div><span>Model performance</span><small>{perfLive ? freshness(perfTs) : 'Fresh index data unavailable'}</small></div><em className={perfLive ? 'live' : ''}>{perfLive ? 'LIVE' : 'UNAVAILABLE'}</em></header>
            {perfLive ? <div className="public-perf-tiles">
              <div><span>Copycat Index</span><b className={Number(perf.copycat_return_pct) >= 0 ? 'positive' : 'negative'}>{pct(perf.copycat_return_pct)}</b><svg viewBox="0 0 260 72" preserveAspectRatio="none"><path d={copycatPath}/></svg></div>
              <div><span>BTC</span><b className={Number(perf.btc_return_pct) >= 0 ? 'positive' : 'negative'}>{pct(perf.btc_return_pct)}</b><svg viewBox="0 0 260 72" preserveAspectRatio="none"><path d={btcPath}/></svg></div>
              <div><span>ETH</span><b className={Number(perf.eth_return_pct) >= 0 ? 'positive' : 'negative'}>{pct(perf.eth_return_pct)}</b><svg viewBox="0 0 260 72" preserveAspectRatio="none"><path d={ethPath}/></svg></div>
            </div> : <div className="public-data-empty"><b>Waiting for a fresh performance snapshot.</b><span>No bundled performance number is substituted.</span></div>}
          </article>
          <article className="public-allocation-card">
            <header><div><span>Current allocation</span><small>Signed allocation • 100% gross</small></div><em className={feedLive ? 'live' : ''}>{feedLive ? 'LIVE' : 'UNAVAILABLE'}</em></header>
            {feedLive && allocationRows.length ? <div className="public-allocation-body"><div className="public-donut" style={donutStyle}><i><span>MODEL</span><b>{compact(selected)}</b><small>wallets</small></i></div><div className="public-allocation-list">{allocationRows.map((x, i) => <div key={x.coin}><i data-n={i}/><b>{x.coin}</b><span className={x.mixed ? '' : x.signed < 0 ? 'negative' : 'positive'}>{x.mixed ? `${x.percent.toFixed(1)}% gross` : `${x.signed < 0 ? '-' : '+'}${x.percent.toFixed(1)}%`}</span></div>)}</div></div> : <div className="public-data-empty"><b>Waiting for fresh allocation data.</b><span>Negative means short. Positive means long.</span></div>}
            <p>Absolute weights total 100% <span>•</span> Negative = short <span>•</span> Positive = long</p>
          </article>
        </div>
      </section>

      <section className="public-product-preview">
        <div className="public-product-copy"><p className="public-eyebrow"><span/> Live dashboard</p><h2>Everything important. One screen.</h2><p>Get the full picture without needing to decode raw wallet activity yourself.</p></div>
        <div className="public-dashboard-mini">
          <header><b>Copycat</b><span>Overview&nbsp;&nbsp; Positions&nbsp;&nbsp; Activity</span><em className={feedLive ? 'live' : ''}>{feedLive ? 'LIVE' : 'UNAVAILABLE'}</em></header>
          {feedLive && signals.length ? <div className="public-mini-content">
            <div className="public-mini-position"><span>Market positioning</span><b>{symbol}</b><strong className={isShort ? 'negative' : 'positive'}>{signalLabel(btc.signal)}</strong><div className="public-mini-bar"><i style={{ width: `${conviction}%` }}/></div><small>{compact(btc.wallets_long)} long / {compact(btc.wallets_short)} short&nbsp;&nbsp; • &nbsp;&nbsp;Net {money(btc.net_value_usd)}</small></div>
            <div className="public-mini-movers"><span>Top conviction</span>{signals.slice(0,3).map((r:any)=><div key={r.coin}><b>{r.coin}</b><em className={Number(r.signal)<0?'negative':'positive'}>{Math.round(Math.abs(Number(r.signal))*100)}% {Number(r.signal)<0?'Short':'Long'}</em><strong>{money(r.net_value_usd)}</strong></div>)}</div>
            <div className="public-mini-activity"><span>Recent wallet activity</span>{orders.slice(0,2).map((r:any,i:number)=><div key={`${r.wallet}-${r.ts_ms}-${i}`}><b>{String(r.wallet_label || r.wallet || 'Wallet').replace(/^(.{8}).*(.{4})$/, '$1…$2')}</b><em className={String(r.side).toLowerCase().includes('short')?'negative':'positive'}>{r.side || 'Order'}</em><strong>{r.coin || r.asset}</strong><small>{money(r.delta_value_usd || r.position_value_usd)}</small></div>)}</div>
          </div> : <div className="public-data-empty"><b>Fresh dashboard snapshot unavailable.</b><span>The preview does not fall back to deploy-time demo figures.</span></div>}
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
