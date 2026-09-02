'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import PublicNav from '../../components/PublicNav'
import PublicMeshBackdrop from '../../components/PublicMeshBackdrop'
import PublicTokenIcon from '../../components/PublicTokenIcon'
import { apiGetFresh } from '../../lib/api'

const MAX_LIVE_AGE_MS = Number(process.env.NEXT_PUBLIC_PUBLIC_LIVE_MAX_AGE_MS || 5 * 60 * 1000)

type Tab = 'wallets' | 'markets' | 'activity' | 'endpoints'

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
function freshness(ts: any) {
  const n = Number(ts || 0)
  if (!n) return 'Freshness unavailable'
  const secs = Math.max(0, Math.round((Date.now() - n) / 1000))
  if (secs < 60) return secs < 10 ? 'Updated just now' : `Updated ${secs}s ago`
  const mins = Math.round(secs / 60)
  return mins < 60 ? `Updated ${mins}m ago` : `Updated ${Math.round(mins / 60)}h ago`
}
function isFresh(ts: any) {
  const n = Number(ts || 0)
  return Boolean(n && Math.abs(Date.now() - n) <= MAX_LIVE_AGE_MS)
}
function shortWallet(row: any) {
  const w = String(row?.wallet || row?.address || '')
  return /^0x[a-fA-F0-9]{40}$/.test(w) ? `${w.slice(0,8)}…${w.slice(-6)}` : (row?.wallet_label || 'Wallet')
}
function displaySignalValue(row: any) {
  const longUsd = Number(row?.value_long_usd || 0)
  const shortUsd = Number(row?.value_short_usd || 0)
  const total = longUsd + shortUsd
  if (total <= 0) return Number(row?.signal || 0)
  return longUsd >= shortUsd ? longUsd / total : -(shortUsd / total)
}
function signalText(row: any) {
  const value = displaySignalValue(row)
  return `${Math.round(Math.abs(value) * 100)}% ${value < 0 ? 'Short' : 'Long'}`
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
function endpointBase() {
  return (process.env.NEXT_PUBLIC_SNAPSHOT_BASE_URL || 'https://pub-b9e0279f5eb0496b99c7fa37329e6b53.r2.dev').replace(/\/+$/, '')
}

function ApiGlyph({ type }: { type: 'wallets' | 'scan' | 'live' | 'json' | 'source' | 'rank' | 'trophy' | 'code' }) {
  const glyphs: Record<string, string> = { wallets: '♧', scan: '⌕', live: '⌁', json: '</>', source: '≈', rank: '▱', trophy: '♕', code: '</>' }
  return <span aria-hidden="true">{glyphs[type]}</span>
}

export default function ApiAccessPage() {
  const [status, setStatus] = useState<any>({})
  const [coverage, setCoverage] = useState<any>({})
  const [leaderboard, setLeaderboard] = useState<any>({})
  const [screener, setScreener] = useState<any>({})
  const [feed, setFeed] = useState<any>({})
  const [tab, setTab] = useState<Tab>('markets')
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      const results = await Promise.allSettled([
        apiGetFresh('/api/data/v1/status', { timeoutMs: 10000 }),
        apiGetFresh('/api/data/v1/public/coverage-preview', { timeoutMs: 10000 }),
        apiGetFresh('/api/data/v1/public/leaderboard-preview?limit=50', { timeoutMs: 10000 }),
        apiGetFresh('/api/data/v1/public/token-screener-preview?limit=40', { timeoutMs: 10000 }),
        apiGetFresh('/api/dashboard-feed', { timeoutMs: 10000 }),
      ])
      if (cancelled) return
      const [s, c, l, t, f] = results
      if (s.status === 'fulfilled') setStatus(s.value || {})
      if (c.status === 'fulfilled') setCoverage(c.value || {})
      if (l.status === 'fulfilled') setLeaderboard(l.value || {})
      if (t.status === 'fulfilled') setScreener(t.value || {})
      if (f.status === 'fulfilled') setFeed(f.value || {})
      setError(results.every(r => r.status === 'rejected') ? 'Live Copycat API snapshots are temporarily unavailable.' : '')
    }
    load()
    const id = window.setInterval(load, 30000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [])

  const statusTs = Number(status?.updated_at_ms || status?.snapshot_generated_at_ms || 0)
  const coverageTs = Number(coverage?.updated_at_ms || coverage?.as_of_ms || 0)
  const feedTs = Number(feed?.snapshot_generated_at_ms || feed?.server_time_ms || feed?.summary?.latest_signal_ts_ms || 0)
  const boardTs = Number(leaderboard?.updated_at_ms || 0)
  const marketTs = Number(screener?.updated_at_ms || 0)
  const latestTs = Math.max(statusTs, coverageTs, feedTs, boardTs, marketTs)
  const statusLive = isFresh(statusTs)
  const coverageLive = isFresh(coverageTs)
  const feedLive = isFresh(feedTs)
  const boardLive = isFresh(boardTs)
  const marketLive = isFresh(marketTs)
  const live = statusLive || coverageLive || feedLive || boardLive || marketLive

  const summary = feedLive ? (feed?.summary || {}) : {}
  const scanned = Number(
    (feedLive && (summary.indexed_wallets || summary.known_wallet_candidates || summary.registry_wallets || summary.owned_wallets_indexed || summary.scanner_candidate_wallets_scored))
    || (statusLive && status?.scanner_candidate_wallets_scored)
    || (coverageLive && coverage?.scanner_candidate_wallets_scored)
    || 0
  )
  const selected = Number(
    (feedLive && (summary.qualified_wallets || summary.selected_wallet_count || summary.tracked_active_wallets))
    || (statusLive && (status?.selected_wallet_count || status?.tracked_active_wallets))
    || (coverageLive && (coverage?.selected_wallet_count || coverage?.wallets_configured))
    || 0
  )
  const wallets = boardLive ? (leaderboard?.rows || leaderboard?.data || []) : []
  const dashboardMarkets = feedLive && Array.isArray(feed?.signals) ? rankSignalsLikeDashboard(feed.signals) : []
  const markets = dashboardMarkets.length ? dashboardMarkets : (marketLive ? (screener?.rows || screener?.data || []) : [])
  const activity = feedLive ? (feed?.orders || feed?.recent_orders || []) : []
  const marketDataTs = dashboardMarkets.length ? feedTs : marketTs
  const sample = markets[0] || null
  const base = endpointBase()

  const codeSample = useMemo(() => {
    if (!sample) return '{\n  "status": "waiting_for_fresh_snapshot"\n}'
    return JSON.stringify({
      asset: sample.coin,
      direction: displaySignalValue(sample) < 0 ? 'short' : 'long',
      conviction: Math.round(Math.abs(displaySignalValue(sample)) * 100),
      long_wallets: Number(sample.wallets_long || 0),
      short_wallets: Number(sample.wallets_short || 0),
      net_exposure: Number(sample.net_value_usd || 0),
    }, null, 2)
  }, [sample])

  const endpoints = [
    ['Dashboard feed', '/dashboard-feed.json', 'Aggregate live snapshot of market signals, flow, orders and model targets.'],
    ['Ranked wallets', '/api/leaderboard-preview.json', 'Current ranked cohort with account value and open exposure.'],
    ['Token screener', '/api/token-screener-preview.json', 'Market conviction, wallet counts and net positioning.'],
    ['Performance index', '/performance-index.json', 'Copycat Index and live BTC / ETH / S&P benchmark data.'],
    ['Coverage status', '/api/coverage-preview.json', 'Current data freshness, coverage and publisher status.'],
    ['Ranking audit', '/api/ranking-audit.json', 'Ranking methodology and quality-control snapshot.'],
  ]

  return <div className="public-redesign-root">
    <PublicNav/>
    <main className="public-redesign-shell public-api-page">
      <PublicMeshBackdrop variant="api"/>
      <section className="public-api-hero">
        <div>
          <p className="public-eyebrow"><span/> Copycat API</p>
          <h1>Build with smart-<br/>wallet intelligence.</h1>
          <p>Access ranked Hyperliquid wallets, market positioning, portfolio signals and wallet activity through simple read-only endpoints.</p>
          <div className="public-actions"><a className="public-primary" href="#api-endpoints">View documentation <span>→</span></a><a className="public-secondary" href="mailto:paulmurrin13@gmail.com?subject=Copycat%20API%20access">Request API access</a></div>
        </div>
      </section>

      <section className="public-api-stats">
        <article><i><ApiGlyph type="wallets"/></i><b>{live && selected ? compact(selected) : '—'}</b><span>ranked wallets</span></article>
        <article><i><ApiGlyph type="scan"/></i><b>{live && scanned ? compact(scanned) : '—'}</b><span>wallets analysed</span></article>
        <article><i><ApiGlyph type="live"/></i><b>{live ? 'Live' : '—'}</b><span>{live ? freshness(latestTs) : 'fresh feed unavailable'}</span></article>
        <article><i><ApiGlyph type="json"/></i><b>JSON</b><span>REST endpoints</span></article>
      </section>

      <section className="public-api-pipeline">
        <div className="public-section-heading"><p className="public-eyebrow"><span/> How Copycat data is built</p><h2>From Hyperliquid to structured intelligence.</h2></div>
        <div className="public-pipeline-flow">
          <div><i><ApiGlyph type="source"/></i><b>Hyperliquid</b><span>Public wallet + market state</span></div><em>→</em>
          <div><i><ApiGlyph type="scan"/></i><b>Wallet universe</b><span>{live && scanned ? `${compact(scanned)} candidates assessed` : 'Waiting for live count'}</span></div><em>→</em>
          <div><i><ApiGlyph type="rank"/></i><b>Copycat ranking engine</b><span>Performance, scale + exposure checks</span></div><em>→</em>
          <div><i><ApiGlyph type="trophy"/></i><b>Top selection</b><span>{live && selected ? `${compact(selected)} tracked wallets` : 'Waiting for live count'}</span></div><em>→</em>
          <div><i><ApiGlyph type="code"/></i><b>Live API</b><span>Read-only JSON snapshots</span></div>
        </div>
      </section>

      <section className="public-api-code-section">
        <article className="public-code-card">
          <header><div><h2>One request. Structured intelligence.</h2><span><b>GET</b> /api/token-screener-preview.json</span></div><em className={live && sample ? 'live' : ''}>{live && sample ? '200 LIVE' : 'WAITING'}</em></header>
          <pre>{codeSample}</pre>
        </article>
        <div className="public-api-benefits">
          <div><i>ϟ</i><span><b>Simple & predictable</b><small>Clean REST-style snapshot endpoints with consistent JSON responses.</small></span></div>
          <div><i>◇</i><span><b>Built for research & products</b><small>Use Copycat data in dashboards, alerts, bots and analytics workflows.</small></span></div>
          <div><i>▣</i><span><b>Read-only & freshness-aware</b><small>Public pages reject old deploy-time data rather than presenting it as live.</small></span></div>
        </div>
      </section>

      <section className="public-api-browser">
        <header><div className="public-api-tabs">{(['wallets','markets','activity','endpoints'] as Tab[]).map(t => <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t[0].toUpperCase()+t.slice(1)}</button>)}</div><span className={live ? 'live' : ''}>{live ? 'Live data' : 'Fresh data unavailable'}</span></header>
        {tab === 'markets' ? <div className="public-api-table-block"><h3>Market positioning <small>Same dashboard feed • {freshness(marketDataTs || latestTs)}</small></h3>{markets.length ? <div className="public-table-scroll"><table><thead><tr><th>Asset</th><th>Conviction</th><th>Long wallets</th><th>Short wallets</th><th>Net exposure</th></tr></thead><tbody>{markets.slice(0,12).map((r:any)=><tr key={r.coin}><td><span className="public-api-token-cell"><PublicTokenIcon symbol={r.coin}/><b>{r.coin}</b></span></td><td className={displaySignalValue(r) < 0 ? 'negative' : 'positive'}>{signalText(r)}</td><td>{compact(r.wallets_long)}</td><td>{compact(r.wallets_short)}</td><td className={Number(r.net_value_usd)<0?'negative':'positive'}>{money(r.net_value_usd)}</td></tr>)}</tbody></table></div> : <div className="public-data-empty"><b>Waiting for a fresh market snapshot.</b><span>No bundled table is shown as live.</span></div>}</div> : null}
        {tab === 'wallets' ? <div className="public-api-table-block"><h3>Ranked wallet cohort <small>{freshness(boardTs || latestTs)}</small></h3>{wallets.length ? <div className="public-table-scroll"><table><thead><tr><th>#</th><th>Wallet</th><th>Total value</th><th>Perp equity</th><th>Open exposure</th></tr></thead><tbody>{wallets.slice(0,20).map((r:any,i:number)=><tr key={r.wallet || i}><td>{r.rank || i+1}</td><td><a href={r.wallet ? `https://hypurrscan.io/address/${r.wallet}` : '#'} target="_blank" rel="noreferrer">{shortWallet(r)}</a></td><td>{money(r.total_wallet_value_usd)}</td><td>{money(r.perp_account_value_usd ?? r.account_value_usd)}</td><td>{money(r.open_position_value_usd)}</td></tr>)}</tbody></table></div> : <div className="public-data-empty"><b>Waiting for a fresh wallet snapshot.</b><span>No deploy-time wallet values are substituted.</span></div>}</div> : null}
        {tab === 'activity' ? <div className="public-api-table-block"><h3>Recent tracked-wallet activity <small>{freshness(feedTs || latestTs)}</small></h3>{activity.length ? <div className="public-table-scroll"><table><thead><tr><th>Wallet</th><th>Action</th><th>Asset</th><th>Value</th><th>Time</th></tr></thead><tbody>{activity.slice(0,20).map((r:any,i:number)=><tr key={`${r.wallet}-${r.ts_ms}-${i}`}><td>{shortWallet(r)}</td><td className={String(r.side).toLowerCase().includes('short')?'negative':'positive'}>{r.side || r.action || 'Order'}</td><td><span className="public-api-token-cell"><PublicTokenIcon symbol={r.coin || r.asset}/><b>{r.coin || r.asset || '—'}</b></span></td><td>{money(r.delta_value_usd || r.position_value_usd || r.value_usd)}</td><td>{freshness(r.ts_ms)}</td></tr>)}</tbody></table></div> : <div className="public-data-empty"><b>Waiting for fresh wallet activity.</b><span>Activity only appears when the live feed is current.</span></div>}</div> : null}
        {tab === 'endpoints' ? <div className="public-api-tab-endpoints">{endpoints.map(([title,path,desc])=><code key={title}><b>{title}</b><span>GET {base}{path}</span><em>{desc}</em></code>)}</div> : null}
      </section>

      <section id="api-endpoints" className="public-api-endpoint-section">
        <div className="public-section-heading"><p className="public-eyebrow"><span/> API endpoints</p><h2>Core Copycat snapshots.</h2></div>
        <div className="public-api-endpoint-grid">{endpoints.map(([title,path,desc],i)=><article key={title}><i>{['▦','♧','⌕','⌁','◇','✓'][i]}</i><h3>{title}</h3><p>{desc}</p><code><b>GET</b> {path}</code></article>)}</div>
      </section>

      {error ? <div className="public-live-warning">{error}</div> : null}
      <footer className="public-disclaimer"><span>◇</span><p><b>Read-only public snapshots.</b> Data is refreshed by the active Copycat publisher and may become temporarily unavailable if freshness checks fail. Market intelligence only, not financial advice.</p><Link href="/risk-disclaimer">Learn more →</Link></footer>
    </main>
  </div>
}
