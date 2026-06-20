"use client"

import { useEffect, useMemo, useState } from 'react'
import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import { getApiBaseUrl } from '../../lib/supabase'

type Status = any

function compact(n: any) {
  const value = Number(n || 0)
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 })
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
          fetch(`${apiBase}/api/data/v1/public/leaderboard-preview`, { cache: 'no-store' }).then(r => r.json()).catch(() => ({})),
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

  const claim = useMemo(() => status.guarded_claim_label || coverage.ranking_scope_label || 'Copycat-ranked wallets from our indexed Hyperliquid universe', [status, coverage])

  return <><Nav/><main className="page-shell cc-api-page"><LineBackdrop variant="landing"/>
    <section className="cc-api-hero cc-api-hero-pro">
      <p className="eyebrow">Copycat Data API</p>
      <h1>Hyperliquid wallet intelligence, built from our own data layer.</h1>
      <p>Programmatic access to wallet rankings, asset conviction, recent flow, live events, and historical fills captured through Copycat’s Hyperliquid-native pipeline.</p>
      <div className="action-row"><a className="primary-btn" href="mailto:paulmurrin13@gmail.com?subject=Copycat%20Data%20API%20access">Request API access <span>→</span></a><a className="outline-btn" href="/pricing">View pricing</a></div>
      <div className="cc-api-truth-note">{claim}. Historical coverage is shown per endpoint; market intelligence only.</div>
    </section>

    <section className="cc-api-status-grid cc-api-status-grid-pro">
      <article><span>Source</span><b>{status.source || 'hyperliquid_native'}</b><em>Nansen required: {status.nansen_required === false ? 'No' : 'No for live path'}</em></article>
      <article><span>Indexed wallets</span><b>{compact(status.owned_wallets_indexed ?? coverage.indexed_wallets)}</b><em>{compact(status.known_wallet_candidates ?? coverage.known_wallet_candidates)} known candidates</em></article>
      <article><span>Qualified wallets</span><b>{compact(status.owned_wallets_qualified ?? coverage.qualified_wallets)}</b><em>{compact(status.tracked_active_wallets ?? coverage.active_ranked_wallets)} active dashboard wallets</em></article>
      <article><span>Stored fills/events</span><b>{compact(status.stored_owned_fills ?? coverage.stored_fills)}</b><em>{compact(status.stored_live_events ?? coverage.stored_live_events)} live events</em></article>
    </section>

    <section className="cc-api-product-grid">
      <article><h3>Leaderboard API</h3><p>Copycat-ranked wallets with score, account value, open exposure, realised PnL inputs, fee data, and freshness timestamps.</p><code>GET {baseUrl}/api/data/v1/leaderboard</code></article>
      <article><h3>Asset conviction API</h3><p>Value-weighted long/short conviction and exposure across tracked wallets, designed for dashboards and trading tools.</p><code>GET {baseUrl}/api/data/v1/public/token-screener-preview</code></article>
      <article><h3>Historical fills API</h3><p>Stored Hyperliquid fills captured by Copycat. Coverage grows over time under Option A: official Hyperliquid-native capture.</p><code>GET {baseUrl}/api/data/v1/wallet/0x.../fills</code></article>
    </section>

    <section className="cc-api-live-panels">
      <div className="cc-api-doc-card cc-api-table-card"><div><p className="eyebrow">Preview</p><h2>Ranked wallets</h2><p>Public preview is shortened. Paid API keys unlock full endpoints and higher limits.</p></div><table><thead><tr><th>#</th><th>Wallet</th><th>Score</th><th>Account value</th><th>Open exposure</th></tr></thead><tbody>{leaderboard.slice(0, 8).map((r:any) => <tr key={r.wallet}><td>{r.rank}</td><td>{r.wallet_label}</td><td>{Number(r.copycat_score || 0).toFixed(1)}</td><td>${compact(r.account_value_usd)}</td><td>${compact(r.open_position_value_usd)}</td></tr>)}</tbody></table></div>
      <div className="cc-api-doc-card cc-api-table-card"><div><p className="eyebrow">Preview</p><h2>Token screener</h2><p>Most valuable directional consensus from tracked wallets.</p></div><table><thead><tr><th>Asset</th><th>Tilt</th><th>Conviction</th><th>Exposure</th></tr></thead><tbody>{tokens.slice(0, 8).map((r:any) => <tr key={r.coin}><td>{r.coin}</td><td className={r.tilt === 'long' ? 'positive' : 'negative'}>{r.tilt}</td><td>{Number(r.conviction_pct || 0).toFixed(0)}%</td><td>${compact(r.gross_exposure_usd)}</td></tr>)}</tbody></table></div>
    </section>

    <section className="cc-api-doc-card"><div><p className="eyebrow">API v1</p><h2>Core endpoints</h2><p>Use <code>X-Copycat-Api-Key</code> or <code>Authorization: Bearer YOUR_KEY</code>. Public preview endpoints are rate-limited and intentionally shortened.</p></div><div className="cc-api-endpoints"><code>GET {baseUrl}/api/data/v1/status</code><code>GET {baseUrl}/api/data/v1/public/coverage-preview</code><code>GET {baseUrl}/api/data/v1/public/platform-health</code><code>GET {baseUrl}/api/data/v1/public/leaderboard-preview</code><code>GET {baseUrl}/api/data/v1/public/token-screener-preview</code><code>GET {baseUrl}/api/data/v1/public/asset/BTC</code><code>GET {baseUrl}/api/data/v1/leaderboard</code><code>GET {baseUrl}/api/data/v1/wallet/0x...</code><code>GET {baseUrl}/api/data/v1/recent-events</code></div></section>
    <p className="risk-bar green-risk"><i>♢</i> Data and market intelligence only. Not financial advice. Option A historical coverage grows from data Copycat lawfully captures and stores from Hyperliquid-native sources.</p>
  </main></>
}
