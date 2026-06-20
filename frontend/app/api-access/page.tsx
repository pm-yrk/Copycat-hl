"use client"

import { useEffect, useMemo, useState } from 'react'
import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import { getApiBaseUrl } from '../../lib/supabase'

type Status = Record<string, any>

function compact(n: any) {
  const value = Number(n || 0)
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
function sourceLabel(source: any) {
  const text = String(source || '').toLowerCase()
  if (text.includes('hyperliquid')) return 'Hyperliquid-native capture'
  if (!text || text === 'undefined') return 'Live market capture'
  return String(source).replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase())
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
  return r?.wallet_label || r?.label || r?.wallet || 'Wallet'
}

export default function ApiAccessPage() {
  const [status, setStatus] = useState<Status>({})
  const [leaderboard, setLeaderboard] = useState<any[]>([])
  const [tokens, setTokens] = useState<any[]>([])
  const [coverage, setCoverage] = useState<any>({})
  const [baseUrl, setBaseUrl] = useState('https://hwt-api.onrender.com')

  useEffect(() => {
    let cancelled = false
    getApiBaseUrl().then(async (apiBase) => {
      if (cancelled) return
      setBaseUrl(apiBase)
      try {
        const [s, l, t, c] = await Promise.all([
          fetch(`${apiBase}/api/data/v1/status`, { cache: 'no-store' }).then(r => r.json()).catch(() => ({})),
          fetch(`${apiBase}/api/data/v1/public/leaderboard-preview?limit=8`, { cache: 'no-store' }).then(r => r.json()).catch(() => ({})),
          fetch(`${apiBase}/api/data/v1/public/token-screener-preview?limit=8`, { cache: 'no-store' }).then(r => r.json()).catch(() => ({})),
          fetch(`${apiBase}/api/data/v1/public/coverage-preview`, { cache: 'no-store' }).then(r => r.json()).catch(() => ({})),
        ])
        if (!cancelled) {
          setStatus(s || {})
          setLeaderboard(l?.data || [])
          setTokens(t?.data || [])
          setCoverage(c || {})
        }
      } catch {}
    })
    return () => { cancelled = true }
  }, [])

  const indexed = Number(status.owned_wallets_indexed ?? coverage.indexed_wallets ?? 0)
  const known = Number(status.known_wallet_candidates ?? coverage.known_wallet_candidates ?? indexed)
  const qualified = Number(status.owned_wallets_qualified ?? coverage.qualified_wallets ?? 0)
  const tracked = Number(status.tracked_active_wallets ?? coverage.active_ranked_wallets ?? 0)
  const records = Number(status.stored_owned_fills || 0) + Number(status.stored_live_events || 0)
  const ready = Boolean(status.top_claim_ready || coverage.top_claim_ready)
  const claim = useMemo(() => ready
    ? 'Broad-market ranking coverage is active.'
    : `Coverage is growing: ${compact(indexed)} indexed wallets today. Broad-market top-wallet language unlocks after the coverage threshold is met.`,
    [ready, indexed])

  return <><Nav/><main className="cc-dashboard-shell cc-api-customer-page"><LineBackdrop variant="dashboard" />
    <section className="cc-api-customer-hero cc-card">
      <div>
        <p className="eyebrow live">Copycat Data API</p>
        <h1>Hyperliquid intelligence for apps, traders, and research teams.</h1>
        <p>Use Copycat’s wallet rankings, asset conviction, live flow, and stored fill history inside your own product or workflow.</p>
        <div className="action-row"><a className="primary-btn" href="mailto:paulmurrin13@gmail.com?subject=Copycat%20Data%20API%20access">Request API access <span>→</span></a><a className="outline-btn" href="/pricing">View pricing</a></div>
      </div>
      <aside>
        <span>Data pipeline</span>
        <b>{sourceLabel(status.source)}</b>
        <em>{freshness(status.latest_live_event_ts_ms || status.latest_metric_ts_ms)}</em>
      </aside>
    </section>

    <section className="cc-api-kpi-row">
      <article className="cc-card"><small>Ranked wallet universe</small><b>{compact(indexed)}</b><span>{known ? `${compact(known)} known candidates` : 'indexed wallets'}</span></article>
      <article className="cc-card"><small>Qualified wallets</small><b>{compact(qualified)}</b><span>{tracked ? `${compact(tracked)} active dashboard wallets` : 'copycat scoring filter'}</span></article>
      <article className="cc-card"><small>Stored market records</small><b>{compact(records)}</b><span>{compact(status.stored_owned_fills)} fills · {compact(status.stored_live_events)} live events</span></article>
      <article className="cc-card"><small>Coverage status</small><b>{ready ? 'Broad' : 'Growing'}</b><span>Historical depth shown per endpoint</span></article>
    </section>

    <p className="cc-api-claim-note"><i>♢</i>{claim} Data is market intelligence only, not financial advice.</p>

    <section className="cc-api-product-row">
      <article className="cc-card"><i className="feature-icon users"/><h3>Wallet rankings</h3><p>Copycat-ranked wallets with score, account value, open exposure, realised-PnL inputs, fee data, and freshness timestamps.</p></article>
      <article className="cc-card"><i className="feature-icon signal"/><h3>Asset signals</h3><p>Value-weighted long/short conviction by market, including exposure, confidence, wallet participation, and tilt.</p></article>
      <article className="cc-card"><i className="feature-icon flow"/><h3>Recent flow</h3><p>Buyer/seller pressure, net value flow, and the most important recent market movements from tracked wallets.</p></article>
      <article className="cc-card"><i className="feature-icon clock"/><h3>Historical fills</h3><p>Stored Hyperliquid fills captured by Copycat under Option A. Coverage increases as our own pipeline runs.</p></article>
    </section>

    <section className="cc-api-preview-grid">
      <article className="cc-card cc-api-preview-card">
        <div className="cc-panel-title"><h3>Leaderboard preview</h3><span>sample rows</span></div>
        <div className="cc-scroll-table"><table><thead><tr><th>#</th><th>Wallet</th><th>Score</th><th>Account value</th><th>Open exposure</th></tr></thead><tbody>{leaderboard.slice(0, 8).map((r:any, i:number) => <tr key={r.wallet || i}><td>{r.rank || i + 1}</td><td>{rowWallet(r)}</td><td>{Number(r.copycat_score || r.score || 0).toFixed(1)}</td><td>{money(r.account_value_usd)}</td><td>{money(r.open_position_value_usd)}</td></tr>)}</tbody></table></div>
      </article>
      <article className="cc-card cc-api-preview-card">
        <div className="cc-panel-title"><h3>Asset signal preview</h3><span>top conviction</span></div>
        <div className="cc-scroll-table"><table><thead><tr><th>Asset</th><th>Tilt</th><th>Conviction</th><th>Exposure</th></tr></thead><tbody>{tokens.slice(0, 8).map((r:any, i:number) => <tr key={r.coin || i}><td>{r.coin}</td><td className={String(r.tilt).toLowerCase().includes('short') ? 'negative' : 'positive'}>{r.tilt || '—'}</td><td>{Number(r.conviction_pct || 0).toFixed(0)}%</td><td>{money(r.gross_exposure_usd)}</td></tr>)}</tbody></table></div>
      </article>
    </section>

    <section className="cc-card cc-api-endpoint-card">
      <div><p className="eyebrow live">Developer access</p><h2>Core endpoints</h2><p>Paid keys unlock full responses and higher limits. Public previews are intentionally shortened for the website.</p></div>
      <div className="cc-api-endpoint-list">
        <code>GET {baseUrl}/api/data/v1/public/leaderboard-preview</code>
        <code>GET {baseUrl}/api/data/v1/public/token-screener-preview</code>
        <code>GET {baseUrl}/api/data/v1/public/asset/BTC</code>
        <code>GET {baseUrl}/api/data/v1/leaderboard</code>
        <code>GET {baseUrl}/api/data/v1/wallet/0x...</code>
        <code>GET {baseUrl}/api/data/v1/recent-events</code>
      </div>
    </section>

    <footer className="cc-warning-banner"><span className="cc-shield" aria-hidden>♢</span><div className="cc-footer-main"><strong>Built for customers using the service.</strong><em>Dashboard customers see clear market intelligence. API customers get structured Copycat data with honest coverage labels.</em></div></footer>
  </main></>
}
