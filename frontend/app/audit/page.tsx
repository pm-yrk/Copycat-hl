'use client'

import { useEffect, useState } from 'react'
import Nav from '../../components/Nav'
import { apiGet } from '../../lib/api'

type AuditCheck = { name: string, status: string, severity: string, detail?: string, metrics?: any }

function money(v: any) {
  const n = Number(v || 0)
  if (!Number.isFinite(n)) return '$0'
  return n.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}
function fmtMs(ms: any) {
  const n = Number(ms || 0)
  if (!n) return 'n/a'
  return new Date(n).toLocaleString()
}
function pct(v: any) {
  const n = Number(v || 0)
  return `${n.toFixed(3)}%`
}
function StatusPill({ status, severity }: { status: string, severity?: string }) {
  return <span className={`audit-pill ${status} ${severity || ''}`}>{status.toUpperCase()}</span>
}

export default function AuditPage() {
  const [audit, setAudit] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  async function load(live = false, full = false) {
    try {
      setLoading(true); setErr('')
      const query = live ? `/api/audit?live=true&full=${full ? 'true' : 'false'}&max_wallets=10` : '/api/audit'
      const data = await apiGet(query)
      setAudit(data)
    } catch (e: any) {
      setErr(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(false); const id = setInterval(() => load(false), 10000); return () => clearInterval(id) }, [])

  const checks: AuditCheck[] = audit?.checks || []
  const failed = checks.filter(c => c.status === 'fail')
  const totals = audit?.totals || {}
  const live = audit?.live_check

  return <><Nav /><main className="audit-shell">
    <section className="audit-hero">
      <p className="eyebrow live">Private data audit</p>
      <h1>Copycat data reconciliation</h1>
      <p>This page compares dashboard values against the database snapshot and can also sample live Hyperliquid data directly.</p>
      <div className="audit-actions">
        <button onClick={() => load(false)} disabled={loading}>{loading ? 'Checking…' : 'Run database audit'}</button>
        <button onClick={() => load(true, false)} disabled={loading}>Run live sample</button>
        <button onClick={() => load(true, true)} disabled={loading}>Run full 50-wallet live audit</button>
      </div>
      {err && <div className="audit-error">{err}</div>}
    </section>

    {audit && <>
      <section className="audit-summary-grid">
        <article><small>Overall status</small><StatusPill status={audit.overall_status} /><span>{failed.length} failed checks</span></article>
        <article><small>Latest snapshot</small><b>{fmtMs(audit.latest_signal_ts_ms)}</b><span>Signal/dashboard source</span></article>
        <article><small>Tracked value</small><b>{money(totals.snapshot_rollup?.tracked_total || totals.signal_rollup?.tracked_total)}</b><span>Completed wallet snapshots</span></article>
        <article><small>Open position value</small><b>{money(totals.position_rollup?.open_total)}</b><span>{totals.position_rollup?.positions || 0} raw positions</span></article>
      </section>

      <section className="audit-card">
        <div className="audit-card-head"><h2>Checks</h2><span>Auto-refreshes every 10 seconds</span></div>
        <div className="audit-check-list">
          {checks.map((c, i) => <div key={`${c.name}-${i}`} className="audit-check-row">
            <StatusPill status={c.status} severity={c.severity} />
            <div><b>{c.name}</b><p>{c.detail}</p></div>
          </div>)}
        </div>
      </section>

      <section className="audit-two-col">
        <div className="audit-card">
          <div className="audit-card-head"><h2>Database rollups</h2></div>
          <table className="audit-table"><tbody>
            <tr><th>Signal rollup tracked total</th><td>{money(totals.signal_rollup?.tracked_total)}</td></tr>
            <tr><th>Wallet snapshot tracked total</th><td>{money(totals.snapshot_rollup?.tracked_total)}</td></tr>
            <tr><th>Raw positions open total</th><td>{money(totals.position_rollup?.open_total)}</td></tr>
            <tr><th>Signal rows open total</th><td>{money(totals.signal_rollup?.signal_open_total)}</td></tr>
            <tr><th>Targets sum</th><td>{Number(totals.target_rollup?.target_sum || 0).toFixed(6)}</td></tr>
            <tr><th>Collector age</th><td>{Number(totals.collector_stale_seconds || 0).toFixed(1)}s</td></tr>
          </tbody></table>
        </div>
        <div className="audit-card">
          <div className="audit-card-head"><h2>Live Hyperliquid check</h2></div>
          {!live && <p className="audit-muted">Click “Run live sample” or “Run full 50-wallet live audit” to compare against Hyperliquid directly.</p>}
          {live && <table className="audit-table"><tbody>
            <tr><th>Wallets checked</th><td>{live.wallets_ok}/{live.wallets_requested}</td></tr>
            <tr><th>Live account value</th><td>{money(live.account_value_usd)}</td></tr>
            <tr><th>DB account value, same wallets</th><td>{money(live.db_completed_snapshot_for_same_wallets?.account_value_usd)}</td></tr>
            <tr><th>Live open value</th><td>{money(live.open_position_value_usd)}</td></tr>
            <tr><th>DB open value, same wallets</th><td>{money(live.db_completed_snapshot_for_same_wallets?.open_position_value_usd)}</td></tr>
            <tr><th>Errors</th><td>{live.errors?.length || 0}</td></tr>
          </tbody></table>}
        </div>
      </section>

      {audit.asset_mismatches?.length > 0 && <section className="audit-card">
        <div className="audit-card-head"><h2>Asset mismatches</h2><span>These must be empty before launch</span></div>
        <div className="audit-scroll"><table className="audit-table"><thead><tr><th>Coin</th><th>Signal long</th><th>Position long</th><th>Signal short</th><th>Position short</th></tr></thead><tbody>
          {audit.asset_mismatches.map((m: any) => <tr key={m.coin}><td>{m.coin}</td><td>{money(m.signal_long_usd)}</td><td>{money(m.position_long_usd)}</td><td>{money(m.signal_short_usd)}</td><td>{money(m.position_short_usd)}</td></tr>)}
        </tbody></table></div>
      </section>}

      <section className="audit-note">
        <strong>Customer-ready rule:</strong> database checks should pass continuously, and the full 50-wallet live audit should pass repeatedly. Live values can differ slightly because Hyperliquid moves while the audit runs.
      </section>
    </>}
  </main></>
}
