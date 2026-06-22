"use client"

import { useEffect, useMemo, useState } from 'react'
import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import { apiGet } from '../../lib/api'

type Status = Record<string, any>

function compact(n: any) {
  const value = Number(n || 0)
  if (!Number.isFinite(value)) return '0'
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 })
}
function money(n: any) {
  const value = Number(n || 0)
  if (!Number.isFinite(value)) return '$0'
  if (Math.abs(value) >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}b`
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}m`
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}k`
  return `$${value.toFixed(0)}`
}
function freshness(ts: any) {
  const n = Number(ts || 0)
  if (!n) return 'Awaiting first sync'
  const mins = Math.max(0, Math.round((Date.now() - n) / 60000))
  if (mins < 1) return 'Updated just now'
  if (mins < 60) return `Updated ${mins}m ago`
  return `Updated ${Math.round(mins / 60)}h ago`
}
function rowWallet(r: any) {
  return r?.wallet_label || r?.short_wallet || r?.label || (r?.wallet ? `${String(r.wallet).slice(0, 6)}…${String(r.wallet).slice(-4)}` : 'Wallet')
}
function signed(value: any) {
  const n = Number(value || 0)
  if (!Number.isFinite(n)) return '$0'
  return `${n < 0 ? '-' : ''}${money(Math.abs(n))}`
}
function biasLabel(r: any) {
  const label = String(r?.signal_label || r?.tilt || r?.direction || '')
  if (label) return label
  const net = Number(r?.net_value_usd || r?.net_flow_usd || 0)
  if (net > 0) return 'Long bias'
  if (net < 0) return 'Short bias'
  return 'Neutral'
}
function biasClass(label: any) {
  return String(label || '').toLowerCase().includes('short') || Number(label || 0) < 0 ? 'negative' : 'positive'
}
function snapshotBase() {
  const configured = (process.env.NEXT_PUBLIC_SNAPSHOT_BASE_URL || '').replace(/\/+$/, '')
  if (configured) return configured
  if (typeof window !== 'undefined') return `${window.location.origin}/copycat-data`
  return '/copycat-data'
}

export default function ApiAccessPage() {
  const [status, setStatus] = useState<Status>({})
  const [leaderboard, setLeaderboard] = useState<any[]>([])
  const [tokens, setTokens] = useState<any[]>([])
  const [coverage, setCoverage] = useState<any>({})
  const [orders, setOrders] = useState<any[]>([])
  const [baseUrl, setBaseUrl] = useState('/copycat-data')

  useEffect(() => {
    let cancelled = false
    setBaseUrl(snapshotBase())
    async function load() {
      try {
        const [s, l, t, c, feed] = await Promise.all([
          apiGet('/api/data/v1/status').catch(() => ({})),
          apiGet('/api/data/v1/public/leaderboard-preview?limit=12').catch(() => ({})),
          apiGet('/api/data/v1/public/token-screener-preview?limit=12').catch(() => ({})),
          apiGet('/api/data/v1/public/coverage-preview').catch(() => ({})),
          apiGet('/api/dashboard-feed').catch(() => ({})),
        ])
        if (!cancelled) {
          setStatus(s || {})
          setLeaderboard(l?.rows || l?.data || [])
          setTokens(t?.rows || t?.data || [])
          setCoverage(c || {})
          setOrders(feed?.orders || feed?.recent_orders || [])
        }
      } catch {}
    }
    load()
    const id = window.setInterval(load, 60000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [])

  const scanned = Number(status.scanner_candidate_wallets_scored ?? coverage.scanner_candidate_wallets_scored ?? coverage.candidate_wallets_scored ?? 0)
  const discovered = Number(status.wallets_discovered_from_recent_trades ?? coverage.wallets_discovered_from_recent_trades ?? 0)
  const selected = Number(status.selected_wallet_count ?? coverage.selected_wallet_count ?? coverage.wallets_configured ?? 50)
  const liveFetched = Number(coverage.wallets_fetched ?? status.tracked_active_wallets ?? selected ?? 0)
  const assets = Number(status.assets_with_signals ?? coverage.assets_with_signals ?? tokens.length ?? 0)
  const records = Number(coverage.recent_orders || status.recent_orders || orders.length || 0)
  const updatedAt = status.updated_at_ms || coverage.updated_at_ms
  const topClaimReady = Boolean(status.top_claim_ready || coverage.top_claim_ready)
  const claim = useMemo(() => {
    return topClaimReady
      ? `Scanner has selected ${compact(selected)} ranked wallets from ${compact(scanned)} locally indexed Hyperliquid candidates.`
      : `Scanner has selected ${compact(selected)} Copycat-ranked wallets from ${compact(scanned)} locally indexed Hyperliquid candidates. This is not yet an all-Hyperliquid top-50 profit claim.`
  }, [topClaimReady, selected, scanned])

  return <><Nav/><main className="cc-dashboard-shell cc-api-intel-page"><LineBackdrop variant="dashboard" />
    <section className="cc-api-intel-hero cc-card">
      <div className="cc-api-hero-copy">
        <p className="eyebrow live">Copycat Data Intelligence</p>
        <h1>Live Hyperliquid smart-wallet data.</h1>
        <p>Ranked wallet cohorts, market signals, recent order flow and public snapshot endpoints powering the Copycat dashboard.</p>
        <div className="action-row"><a className="primary-btn" href="/dashboard">Open dashboard <span>→</span></a><a className="outline-btn" href="#snapshot-endpoints">View endpoints</a></div>
      </div>
      <aside className="cc-api-status-tile">
        <span>Data status</span>
        <b>{liveFetched}/{selected} live wallets</b>
        <em>{freshness(updatedAt)}</em>
      </aside>
    </section>

    <section className="cc-api-kpi-row cc-api-intel-kpis">
      <article className="cc-card"><small>Scanner universe</small><b>{compact(scanned)}</b><span>{discovered ? `${compact(discovered)} discovered from recent trades` : 'candidate wallets indexed locally'}</span></article>
      <article className="cc-card"><small>Selected cohort</small><b>{compact(selected)}</b><span>Copycat-ranked wallets tracked by the publisher</span></article>
      <article className="cc-card"><small>Market signals</small><b>{compact(assets)}</b><span>assets with live positioning data</span></article>
      <article className="cc-card"><small>Recent activity</small><b>{compact(records)}</b><span>latest tracked-wallet order rows</span></article>
    </section>

    <section className="cc-api-pipeline cc-card">
      <div className="cc-api-pipeline-copy">
        <p className="eyebrow live">How the data is built</p>
        <h2>From Hyperliquid wallets to Copycat signals.</h2>
        <p>Copycat reads public Hyperliquid wallet state, scores the locally discovered candidate universe, selects the live cohort, then publishes compact JSON snapshots for the dashboard and API preview.</p>
      </div>
      <div className="cc-api-flow-map" aria-label="Copycat data pipeline">
        <div><b>Hyperliquid</b><span>public wallet state</span></div>
        <i>↓</i>
        <div><b>Local scanner</b><span>{compact(scanned)} candidates scored</span></div>
        <i>↓</i>
        <div><b>Ranking engine</b><span>quality + exposure filters</span></div>
        <i>↓</i>
        <div><b>Top cohort</b><span>{compact(selected)} selected wallets</span></div>
        <i>↓</i>
        <div><b>Snapshot publisher</b><span>fresh JSON files</span></div>
        <i>↓</i>
        <div><b>Cloudflare R2 API</b><span>dashboard + data preview</span></div>
      </div>
    </section>

    <section className="cc-api-nansen-grid">
      <article className="cc-card cc-api-data-card cc-api-leaderboard-card">
        <header><div><p className="eyebrow live">Smart wallet leaderboard</p><h2>Selected wallet cohort</h2></div><span>scanner-ranked</span></header>
        <div className="cc-api-tab-row"><b>7D</b><span>30D</span><span>90D</span><span>180D</span></div>
        <div className="cc-api-table-wrap"><table><thead><tr><th>#</th><th>Wallet</th><th>Account value</th><th>Open exposure</th><th>Positions</th></tr></thead><tbody>{leaderboard.slice(0, 10).map((r:any, i:number) => <tr key={r.wallet || i}><td>{r.rank || i + 1}</td><td>{rowWallet(r)}</td><td>{money(r.account_value_usd)}</td><td><span className="cc-mini-bar"><i style={{width: `${Math.max(8, Math.min(100, Number(r.open_position_value_usd || 0) / Math.max(1, Number(leaderboard[0]?.open_position_value_usd || 1)) * 100))}%`}} />{money(r.open_position_value_usd)}</span></td><td>{compact(r.open_positions)}</td></tr>)}</tbody></table></div>
      </article>

      <article className="cc-card cc-api-data-card cc-api-market-card">
        <header><div><p className="eyebrow live">Token screener</p><h2>Markets smart wallets are leaning into</h2></div><span>top conviction</span></header>
        <div className="cc-api-tab-row"><span>5m</span><span>1h</span><b>24h</b><span>7D</span></div>
        <div className="cc-api-table-wrap"><table><thead><tr><th>Asset</th><th>Tilt</th><th>Wallets</th><th>Exposure</th><th>Net</th></tr></thead><tbody>{tokens.slice(0, 10).map((r:any, i:number) => { const label = biasLabel(r); return <tr key={r.coin || i}><td>{r.coin || '—'}</td><td className={biasClass(label)}>{label}</td><td>{compact(r.wallets_long)}L / {compact(r.wallets_short)}S</td><td>{money(r.gross_value_usd || r.gross_exposure_usd)}</td><td className={biasClass(r.net_value_usd)}>{signed(r.net_value_usd)}</td></tr> })}</tbody></table></div>
      </article>
    </section>

    <section className="cc-card cc-api-data-card cc-api-activity-card">
      <header><div><p className="eyebrow live">Live smart-wallet tape</p><h2>Recent tracked-wallet activity</h2></div><span>{freshness(updatedAt)}</span></header>
      <div className="cc-api-table-wrap"><table><thead><tr><th>Wallet</th><th>Action</th><th>Asset</th><th>Value</th><th>Time</th></tr></thead><tbody>{orders.slice(0, 10).map((r:any, i:number) => <tr key={`${r.wallet || 'wallet'}-${r.ts_ms || i}`}><td>{rowWallet(r)}</td><td className={biasClass(r.side)}>{r.side || r.action || 'Order'}</td><td>{r.coin || r.asset || '—'}</td><td>{money(r.delta_value_usd || r.position_value_usd || r.value_usd)}</td><td>{freshness(r.ts_ms)}</td></tr>)}</tbody></table></div>
    </section>

    <section id="snapshot-endpoints" className="cc-card cc-api-endpoints-pro">
      <div className="cc-api-endpoints-copy"><p className="eyebrow live">Snapshot endpoints</p><h2>Public read-only data files</h2><p>These endpoints are designed for preview and dashboard delivery. Private keys, paid tiers and historical database queries should be added later behind a backend.</p></div>
      <div className="cc-api-endpoint-grid">
        <code><b>Dashboard feed</b><span>GET {baseUrl}/dashboard-feed.json</span></code>
        <code><b>Performance index</b><span>GET {baseUrl}/performance-index.json</span></code>
        <code><b>Leaderboard preview</b><span>GET {baseUrl}/api/leaderboard-preview.json</span></code>
        <code><b>Token screener</b><span>GET {baseUrl}/api/token-screener-preview.json</span></code>
        <code><b>Coverage status</b><span>GET {baseUrl}/api/coverage-preview.json</span></code>
        <code><b>Ranking audit</b><span>GET {baseUrl}/api/ranking-audit.json</span></code>
      </div>
    </section>

    <footer className="cc-warning-banner cc-api-warning"><span className="cc-shield" aria-hidden>♢</span><div className="cc-footer-main"><strong>Market intelligence only.</strong><em>{claim} Not financial advice. Public API snapshots are read-only and may be delayed, cached or temporarily stale.</em></div><div className="cc-footer-status"><span className="cc-quality-dot" /> Data quality snapshot · {freshness(updatedAt)}</div></footer>
  </main></>
}
