"use client"

import { useEffect, useMemo, useState } from 'react'
import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import { apiGet } from '../../lib/api'

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
function freshness(ts: any) {
  const n = Number(ts || 0)
  if (!n) return 'Awaiting first sync'
  const mins = Math.max(0, Math.round((Date.now() - n) / 60000))
  if (mins < 1) return 'Updated just now'
  if (mins < 60) return `Updated ${mins}m ago`
  return `Updated ${Math.round(mins / 60)}h ago`
}
function fmtTime(ms: any) {
  if (!ms) return 'Awaiting first refresh'
  return new Date(Number(ms)).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }).replace(',', '')
}
function rowWallet(r: any) {
  return r?.wallet_label || r?.short_wallet || r?.label || (r?.wallet ? `${String(r.wallet).slice(0, 6)}…${String(r.wallet).slice(-4)}` : 'Wallet')
}
function snapshotBase() {
  const configured = (process.env.NEXT_PUBLIC_SNAPSHOT_BASE_URL || '').replace(/\/+$/, '')
  if (configured) return configured
  if (typeof window !== 'undefined') return `${window.location.origin}/copycat-data`
  return '/copycat-data'
}
function scoreLabel(r: any) {
  const score = Number(r?.copycat_score ?? r?.score ?? 0)
  return score > 0 ? score.toFixed(1) : '—'
}
function biasLabel(r: any) {
  let net = Number(r?.net_position_value_usd ?? r?.net_exposure_usd ?? r?.signed_exposure_usd ?? 0)
  if (!net && Array.isArray(r?.positions)) {
    net = r.positions.reduce((sum: number, p: any) => sum + Number(p?.signed_notional_usd || 0), 0)
  }
  if (net > 0) return 'Long'
  if (net < 0) return 'Short'
  if (Number(r?.open_position_value_usd || 0) > 0) return 'Active'
  return '—'
}
function tiltClass(value: any) {
  const text = String(value || '').toLowerCase()
  if (text.includes('short')) return 'negative'
  if (text.includes('long')) return 'positive'
  return ''
}
function conviction(row: any) {
  const direct = row?.signal_label || row?.tilt || row?.direction
  if (direct) return String(direct)
  const signal = Number(row?.signal || 0)
  if (!Number.isFinite(signal) || signal === 0) return '—'
  return `${Math.round(Math.abs(signal) * 100)}% ${signal < 0 ? 'Short' : 'Long'}`
}

const endpoints = [
  ['GET', '/dashboard-feed.json', 'Main dashboard snapshot: wallet coverage, signals, allocation, flows and recent orders.'],
  ['GET', '/performance-index.json', 'Live Copycat model index and BTC / ETH / S&P 500 benchmark values.'],
  ['GET', '/api/leaderboard-preview.json', 'Public wallet preview with account value and current open exposure.'],
  ['GET', '/api/token-screener-preview.json', 'Asset-level long/short conviction, confidence and value-weighted exposure.'],
  ['GET', '/api/coverage-preview.json', 'Freshness, wallet coverage, scanner universe and snapshot health metadata.'],
  ['GET', '/api/ranking-audit.json', 'Internal methodology/audit snapshot used to verify ranking coverage and scanner status.'],
]

export default function ApiAccessPage() {
  const [status, setStatus] = useState<Status>({})
  const [leaderboard, setLeaderboard] = useState<any[]>([])
  const [tokens, setTokens] = useState<any[]>([])
  const [flow, setFlow] = useState<any[]>([])
  const [coverage, setCoverage] = useState<any>({})
  const [audit, setAudit] = useState<any>({})
  const [baseUrl, setBaseUrl] = useState('/copycat-data')

  useEffect(() => {
    let cancelled = false
    setBaseUrl(snapshotBase())
    async function load() {
      try {
        const [s, l, t, c, a, feed] = await Promise.all([
          apiGet('/api/data/v1/status').catch(() => ({})),
          apiGet('/api/data/v1/public/leaderboard-preview?limit=8').catch(() => ({})),
          apiGet('/api/data/v1/public/token-screener-preview?limit=8').catch(() => ({})),
          apiGet('/api/data/v1/public/coverage-preview').catch(() => ({})),
          apiGet('/api/ranking-audit').catch(() => ({})),
          apiGet('/api/dashboard-feed').catch(() => ({})),
        ])
        if (!cancelled) {
          setStatus(s || {})
          setCoverage(c || {})
          setAudit(a || {})
          setLeaderboard((a?.wallets && a.wallets.length ? a.wallets : l?.rows || l?.data || []).slice(0, 8))
          setTokens(t?.rows || t?.data || [])
          setFlow(feed?.flow || [])
        }
      } catch {}
    }
    load()
    const id = window.setInterval(load, 60000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [])

  const updatedAt = Number(status.updated_at_ms || coverage.updated_at_ms || audit.updated_at_ms || 0)
  const scanned = Number(status.scanner_candidate_wallets_scored ?? coverage.scanner_candidate_wallets_scored ?? audit.wallets_scanned ?? coverage.candidate_wallets_scored ?? 0)
  const discovered = Number(status.wallets_discovered_from_recent_trades ?? coverage.wallets_discovered_from_recent_trades ?? audit.wallets_discovered_from_recent_trades ?? 0)
  const selected = Number(status.selected_wallet_count ?? coverage.selected_wallet_count ?? audit.selected_wallet_count ?? status.tracked_active_wallets ?? 0)
  const tracked = Number(status.tracked_active_wallets ?? coverage.wallets_fetched ?? selected ?? 0)
  const assets = Number(status.assets_with_signals ?? coverage.assets_with_signals ?? tokens.length ?? 0)
  const records = Number(coverage.recent_orders || status.recent_orders || 0)
  const dataHealthy = tracked > 0 && selected > 0 && tracked >= selected
  const statusText = dataHealthy ? 'Data quality healthy' : 'Data quality checking'
  const claim = useMemo(() => `Public snapshot API showing ${compact(tracked)} tracked wallets selected from ${compact(scanned)} locally scanned Hyperliquid candidates.`, [scanned, tracked])

  return <><Nav/><main className="cc-dashboard-shell cc-api-customer-page cc-api-polished-page"><LineBackdrop variant="dashboard" />
    <section className="cc-api-customer-hero cc-card cc-api-polished-hero">
      <div>
        <p className="eyebrow live">Copycat Data API</p>
        <h1>Live smart-wallet intelligence snapshots for Hyperliquid.</h1>
        <p>Read-only JSON snapshots for wallet rankings, asset conviction, portfolio weights, recent order flow and data-quality checks.</p>
        <div className="action-row"><a className="primary-btn" href="/dashboard">Open dashboard <span>→</span></a><a className="outline-btn" href="#endpoints">View endpoints</a></div>
      </div>
      <aside className={dataHealthy ? 'healthy' : 'checking'}>
        <span>Snapshot status</span>
        <b><i className="cc-pulse-dot" /> {dataHealthy ? 'Healthy' : 'Checking'}</b>
        <em>{freshness(updatedAt)}</em>
      </aside>
    </section>

    <section className="cc-api-kpi-row cc-api-polished-kpis">
      <article className="cc-card"><small>Tracked wallets</small><b>{compact(tracked)}</b><span>{selected ? `${compact(selected)} selected for the dashboard` : 'publisher wallet list'}</span></article>
      <article className="cc-card"><small>Scanner universe</small><b>{compact(scanned)}</b><span>{discovered ? `${compact(discovered)} discovered from recent trades` : 'local candidate pool'}</span></article>
      <article className="cc-card"><small>Assets with signals</small><b>{compact(assets)}</b><span>value-weighted live wallet state</span></article>
      <article className="cc-card"><small>Recent order rows</small><b>{compact(records)}</b><span>published in the latest snapshot</span></article>
    </section>

    <p className="cc-api-claim-note cc-api-polished-note"><i>◆</i>{claim} Market intelligence only. This is not yet a verified all-Hyperliquid top-50 profit claim.</p>

    <section className="cc-api-preview-grid cc-api-priority-preview">
      <article className="cc-card cc-api-preview-card">
        <div className="cc-panel-title"><h3>Ranked wallet preview</h3><span>scanner score + live exposure</span></div>
        <div className="cc-scroll-table"><table><thead><tr><th>#</th><th>Wallet</th><th>Score</th><th>Account value</th><th>Open exposure</th><th>Bias</th></tr></thead><tbody>{leaderboard.slice(0, 8).map((r:any, i:number) => {
          const bias = biasLabel(r)
          return <tr key={r.wallet || i}><td>{r.rank || i + 1}</td><td>{rowWallet(r)}</td><td>{scoreLabel(r)}</td><td>{money(r.account_value_usd)}</td><td>{money(r.open_position_value_usd)}</td><td className={tiltClass(bias)}>{bias}</td></tr>
        })}</tbody></table></div>
      </article>
      <article className="cc-card cc-api-preview-card">
        <div className="cc-panel-title"><h3>Asset signal preview</h3><span>top conviction</span></div>
        <div className="cc-scroll-table"><table><thead><tr><th>Asset</th><th>Signal</th><th>Confidence</th><th>Exposure</th><th>Wallets</th></tr></thead><tbody>{tokens.slice(0, 8).map((r:any, i:number) => {
          const sig = conviction(r)
          return <tr key={r.coin || i}><td>{r.coin}</td><td className={tiltClass(sig)}>{sig}</td><td>{r.confidence || '—'}</td><td>{money(r.gross_exposure_usd || r.gross_value_usd)}</td><td>{compact(Number(r.wallets_long || 0) + Number(r.wallets_short || 0))}</td></tr>
        })}</tbody></table></div>
      </article>
    </section>

    <section id="endpoints" className="cc-api-endpoint-grid">
      {endpoints.map(([method, path, description]) => <article className="cc-card cc-api-endpoint-mini" key={path}>
        <small>{method}</small>
        <code>{baseUrl}{path}</code>
        <p>{description}</p>
      </article>)}
    </section>

    <section className="cc-api-product-row cc-api-polished-product-row">
      <article className="cc-card"><i className="feature-icon users"/><h3>Wallet ranking feed</h3><p>Current selected wallets with scanner score, account value, open exposure and current directional bias.</p></article>
      <article className="cc-card"><i className="feature-icon signal"/><h3>Asset intelligence</h3><p>Value-weighted long/short conviction by asset, including confidence, wallet participation and gross exposure.</p></article>
      <article className="cc-card"><i className="feature-icon flow"/><h3>Recent flow</h3><p>{flow.length ? `${compact(flow.length)} asset flow rows available in the live dashboard snapshot.` : 'Buyer/seller pressure and recent tracked-wallet order activity.'}</p></article>
      <article className="cc-card"><i className="feature-icon clock"/><h3>Coverage audit</h3><p>Freshness, selected-wallet count, scanner universe and consistency checks for customer trust.</p></article>
    </section>

    <footer className="cc-warning-banner"><span className="cc-shield" aria-hidden><svg viewBox="0 0 24 24"><path d="M12 3l7 3v5.2c0 4.5-2.7 8.4-7 9.8-4.3-1.4-7-5.3-7-9.8V6l7-3z"/><path d="M9.2 12.1l1.7 1.7 3.9-4.1"/></svg></span><div className="cc-footer-main"><strong>Market intelligence only.</strong><em>Not financial advice. Copycat tracks {compact(tracked)} selected wallets from {compact(scanned)} locally scanned candidates. Not claiming all-Hyperliquid top 50 yet.</em><small>Live coverage: {compact(tracked)}/{compact(selected || tracked)} wallets · Scanner universe: {compact(scanned)} · Snapshot API preview</small></div><div className={`cc-footer-meta ${dataHealthy ? 'healthy' : 'checking'}`}><span className="cc-footer-quality"><span className="cc-pulse-dot" /><b>{statusText}</b></span><small>Signal refresh: {fmtTime(updatedAt)} UTC · Snapshot/cache refresh</small></div></footer>
  </main></>
}
