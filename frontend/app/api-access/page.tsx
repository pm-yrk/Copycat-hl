'use client'

import { useEffect, useMemo, useState } from 'react'
import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import { getApiBaseUrl } from '../../lib/supabase'

type Status = {
  status?: string
  source?: string
  nansen_required?: boolean
  tracked_active_wallets?: number
  known_wallet_candidates?: number
  owned_wallets_indexed?: number
  owned_wallets_qualified?: number
  stored_owned_fills?: number
  stored_live_events?: number
  markets_monitored?: number
  top_claim_ready?: boolean
  top_claim_min_indexed_wallets?: number
}

type LeaderRow = {
  rank: number
  wallet_label: string
  wallet: string
  account_value_usd?: number
  pnl_30d_usd?: number
  roi_30d_pct?: number
  score?: number
  qualifies?: boolean
}

type TokenRow = {
  coin: string
  price_usd?: number
  change_24h_pct?: number | null
  volume_24h_usd?: number
  open_interest_usd?: number
  tracked_net_usd?: number
  tracked_wallets_long?: number
  tracked_wallets_short?: number
}

function compactUsd(value?: number | null) {
  const n = Number(value || 0)
  if (!Number.isFinite(n)) return '$0'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 2 }).format(n)
}

function pct(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—'
  return `${Number(value).toFixed(2)}%`
}

export default function ApiAccessPage() {
  const [status, setStatus] = useState<Status>({})
  const [leaderboard, setLeaderboard] = useState<LeaderRow[]>([])
  const [tokens, setTokens] = useState<TokenRow[]>([])
  const [baseUrl, setBaseUrl] = useState('https://hwt-api.onrender.com')

  useEffect(() => {
    let cancelled = false
    getApiBaseUrl().then(async (apiBase) => {
      if (cancelled) return
      setBaseUrl(apiBase)
      try {
        const [statusRes, leaderboardRes, tokenRes] = await Promise.all([
          fetch(`${apiBase}/api/data/v1/status`, { cache: 'no-store' }),
          fetch(`${apiBase}/api/data/v1/public/leaderboard-preview`, { cache: 'no-store' }),
          fetch(`${apiBase}/api/data/v1/public/token-screener-preview`, { cache: 'no-store' }),
        ])
        if (statusRes.ok && !cancelled) setStatus(await statusRes.json())
        if (leaderboardRes.ok && !cancelled) {
          const payload = await leaderboardRes.json()
          setLeaderboard(payload.data || payload || [])
        }
        if (tokenRes.ok && !cancelled) {
          const payload = await tokenRes.json()
          setTokens(payload.data || payload || [])
        }
      } catch {}
    })
    return () => { cancelled = true }
  }, [])

  const coverage = useMemo(() => {
    const indexed = Number(status.owned_wallets_indexed || 0)
    const known = Number(status.known_wallet_candidates || 0)
    const min = Number(status.top_claim_min_indexed_wallets || 10000)
    return { indexed, known, min, ready: Boolean(status.top_claim_ready) }
  }, [status])

  return <><Nav/><main className="page-shell cc-api-page cc-api-terminal"><LineBackdrop variant="landing"/>
    <section className="cc-api-hero cc-api-terminal-hero">
      <p className="eyebrow">Copycat Data API</p>
      <h1>Hyperliquid wallet intelligence, owned by Copycat.</h1>
      <p>Leaderboards, token screens, tracked-wallet fills, exposure data, live events and backtest-ready historical coverage. Built from Hyperliquid-native data, not Nansen.</p>
      <div className="action-row"><a className="primary-btn" href="mailto:paulmurrin13@gmail.com?subject=Copycat%20Data%20API%20access">Request API access <span>→</span></a><a className="outline-btn" href="/dashboard">View live dashboard</a></div>
    </section>

    <section className="cc-api-status-grid cc-api-kpi-grid">
      <article><span>Source</span><b>{status.source || 'hyperliquid_native'}</b><em>Nansen required: {status.nansen_required === false ? 'No' : 'No for live API'}</em></article>
      <article><span>Wallet universe</span><b>{coverage.indexed.toLocaleString()} indexed</b><em>{coverage.known.toLocaleString()} known candidates</em></article>
      <article><span>Top-50 claim</span><b>{coverage.ready ? 'Ready' : 'Scoped'}</b><em>threshold {coverage.min.toLocaleString()} indexed wallets</em></article>
      <article><span>Stored data</span><b>{(status.stored_live_events ?? 0).toLocaleString()} events</b><em>{(status.stored_owned_fills ?? 0).toLocaleString()} owned fills</em></article>
    </section>

    <section className="cc-api-terminal-grid">
      <article className="cc-api-terminal-card">
        <header><div><h2>Most profitable addresses</h2><p>Copycat-ranked wallets from the indexed Hyperliquid universe.</p></div><span>7D · 30D · 90D</span></header>
        <div className="cc-api-mini-table">
          <div className="cc-api-mini-head"><span>Name</span><span>Total PnL</span><span>ROI</span><span>Score</span></div>
          {leaderboard.slice(0, 12).map((row) => <div className="cc-api-mini-row" key={`${row.rank}-${row.wallet}`}><span><b>{row.wallet_label}</b><em>{row.qualifies ? 'qualified' : 'indexed'}</em></span><span>{compactUsd(row.pnl_30d_usd)}</span><span>{pct(row.roi_30d_pct)}</span><span>{Number(row.score || 0).toFixed(1)}</span></div>)}
          {!leaderboard.length && <p className="cc-api-empty">Leaderboard preview will appear after the owned scanner indexes wallets.</p>}
        </div>
      </article>

      <article className="cc-api-terminal-card">
        <header><div><h2>Hyperliquid perps screener</h2><p>Market universe, prices, volume, open interest and Copycat tracked net position.</p></div><span>Live</span></header>
        <div className="cc-api-mini-table cc-api-token-table">
          <div className="cc-api-mini-head"><span>Token</span><span>Price</span><span>24h</span><span>OI</span><span>Tracked net</span></div>
          {tokens.slice(0, 14).map((row) => <div className="cc-api-mini-row" key={row.coin}><span><b>{row.coin}</b><em>{compactUsd(row.volume_24h_usd)} vol</em></span><span>{compactUsd(row.price_usd)}</span><span className={Number(row.change_24h_pct || 0) >= 0 ? 'good' : 'bad'}>{pct(row.change_24h_pct)}</span><span>{compactUsd(row.open_interest_usd)}</span><span className={Number(row.tracked_net_usd || 0) >= 0 ? 'good' : 'bad'}>{compactUsd(row.tracked_net_usd)}</span></div>)}
          {!tokens.length && <p className="cc-api-empty">Token screener appears once hwt-market-universe is running.</p>}
        </div>
      </article>
    </section>

    <section className="cc-api-doc-card cc-api-customer-card">
      <div><p className="eyebrow">API v1</p><h2>Customer-ready endpoints</h2><p>Use <code>X-Copycat-Api-Key</code> or <code>Authorization: Bearer YOUR_KEY</code>. Preview/status endpoints are public; full datasets require a key.</p></div>
      <div className="cc-api-endpoints">
        <code>GET {baseUrl}/api/data/v1/status</code>
        <code>GET {baseUrl}/api/data/v1/coverage</code>
        <code>GET {baseUrl}/api/data/v1/leaderboard-v2</code>
        <code>GET {baseUrl}/api/data/v1/token-screener</code>
        <code>GET {baseUrl}/api/data/v1/wallet-universe</code>
        <code>GET {baseUrl}/api/data/v1/wallet/0x...</code>
        <code>GET {baseUrl}/api/data/v1/historical-fills</code>
        <code>GET {baseUrl}/api/data/v1/backfill-coverage</code>
        <code>GET {baseUrl}/api/data/v1/historical-sources</code>
      </div>
    </section>

    <section className="feature-row cc-api-feature-row"><article><i className="feature-icon users"/><span>01</span><h3>Owned wallet universe</h3><p>Continuous scanner expands and scores Copycat’s known Hyperliquid wallets without relying on Nansen.</p></article><article><i className="feature-icon bolt"/><span>02</span><h3>Historical fill backfill</h3><p>Backfills the maximum official recent fill history available per wallet, then stores all future observations permanently.</p></article><article><i className="feature-icon bars"/><span>03</span><h3>Market screener</h3><p>Captures Hyperliquid perps metadata, market contexts, volume, open interest, and Copycat tracked exposure.</p></article></section>
    <p className="risk-bar green-risk"><i>♢</i> Data and market intelligence only. Not financial advice. Coverage is explicit: Copycat ranks wallets from its indexed Hyperliquid universe until all-platform coverage is proven.</p>
  </main></>
}
