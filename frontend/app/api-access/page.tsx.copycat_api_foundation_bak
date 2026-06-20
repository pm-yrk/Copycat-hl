'use client'

import { useEffect, useState } from 'react'
import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import { getApiBaseUrl } from '../../lib/supabase'

type Status = {
  status?: string
  source?: string
  nansen_required?: boolean
  tracked_active_wallets?: number
  owned_wallets_indexed?: number
  owned_wallets_qualified?: number
  stored_owned_fills?: number
  stored_live_events?: number
}

export default function ApiAccessPage() {
  const [status, setStatus] = useState<Status>({})
  const [baseUrl, setBaseUrl] = useState('https://hwt-api.onrender.com')

  useEffect(() => {
    let cancelled = false
    getApiBaseUrl().then(async (apiBase) => {
      if (cancelled) return
      setBaseUrl(apiBase)
      try {
        const res = await fetch(`${apiBase}/api/data/v1/status`, { cache: 'no-store' })
        if (res.ok && !cancelled) setStatus(await res.json())
      } catch {}
    })
    return () => { cancelled = true }
  }, [])

  return <><Nav/><main className="page-shell cc-api-page"><LineBackdrop variant="landing"/><section className="cc-api-hero"><p className="eyebrow">Copycat Data API</p><h1>Hyperliquid wallet intelligence, owned by Copycat.</h1><p>Programmatic access to our own wallet leaderboard, tracked-wallet fills, live events, and exposure data. Built from Hyperliquid-native data, not Nansen.</p><div className="action-row"><a className="primary-btn" href="mailto:paulmurrin13@gmail.com?subject=Copycat%20Data%20API%20access">Request API access <span>→</span></a><a className="outline-btn" href="/dashboard">View live dashboard</a></div></section><section className="cc-api-status-grid"><article><span>Source</span><b>{status.source || 'hyperliquid_native'}</b><em>Nansen required: {status.nansen_required === false ? 'No' : 'No for live API'}</em></article><article><span>Tracked wallets</span><b>{status.tracked_active_wallets ?? 0}</b><em>active Copycat cohort</em></article><article><span>Owned wallets indexed</span><b>{status.owned_wallets_indexed ?? 0}</b><em>{status.owned_wallets_qualified ?? 0} qualified</em></article><article><span>Stored events</span><b>{status.stored_live_events ?? 0}</b><em>{status.stored_owned_fills ?? 0} owned fills stored</em></article></section><section className="cc-api-doc-card"><div><p className="eyebrow">API v1</p><h2>Endpoints</h2><p>Use <code>X-Copycat-Api-Key</code> or <code>Authorization: Bearer YOUR_KEY</code>. The status and historical-source endpoints are public; data endpoints require a key.</p></div><div className="cc-api-endpoints"><code>GET {baseUrl}/api/data/v1/status</code><code>GET {baseUrl}/api/data/v1/leaderboard</code><code>GET {baseUrl}/api/data/v1/wallet/0x...</code><code>GET {baseUrl}/api/data/v1/wallet/0x.../fills</code><code>GET {baseUrl}/api/data/v1/exposures</code><code>GET {baseUrl}/api/data/v1/recent-events</code><code>GET {baseUrl}/api/data/v1/historical-sources</code></div></section><section className="feature-row cc-api-feature-row"><article><i className="feature-icon users"/><span>01</span><h3>Owned leaderboard</h3><p>Wallet ranking using Copycat’s stored Hyperliquid-native account, fill, PnL, and exposure data.</p></article><article><i className="feature-icon bolt"/><span>02</span><h3>Live events</h3><p>Tracked-wallet fills are streamed through Hyperliquid WebSocket and stored for faster dashboard updates.</p></article><article><i className="feature-icon bars"/><span>03</span><h3>API product</h3><p>API keys, usage logging, rate limits, wallet profiles, exposures, recent events, and historical-source registry.</p></article></section><p className="risk-bar green-risk"><i>♢</i> Data and market intelligence only. Not financial advice. Historical data coverage depends on what Copycat has lawfully collected and stored.</p></main></>
}
