'use client'

import { useEffect, useState } from 'react'
import Nav from '../../components/Nav'
import { apiGet } from '../../lib/api'

function money(n: any) { return '$' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }) }
function pct(n: any) { return (Number(n || 0) * 100).toFixed(1) + '%' }
function mask(w: string) { return w ? `${w.slice(0, 6)}…${w.slice(-4)}` : '—' }

export default function RankingAuditPage() {
  const [rows, setRows] = useState<any[]>([])
  const [err, setErr] = useState('')
  useEffect(() => {
    apiGet('/api/ranking-audit?limit=50').then((r: any) => setRows(r.wallets || [])).catch((e: any) => setErr(e.message))
  }, [])
  return <><Nav /><main className="cc-audit-shell cc-ranking-audit-shell">
    <section className="cc-audit-hero">
      <p className="eyebrow live">Private ranking audit</p>
      <h1>Top 50 wallet qualification</h1>
      <p>This page explains why each active wallet qualified. Keep it private; it is for checking Copycat’s ranking quality before customers see signals.</p>
    </section>
    {err && <p className="notice gold">{err}</p>}
    <section className="cc-card cc-ranking-method">
      <h3>Ranking V2 formula</h3>
      <div className="cc-method-grid">
        <span>30% net PnL quality</span><span>20% ROI / capital efficiency</span><span>15% consistency</span><span>15% drawdown control</span><span>10% account size</span><span>5% recent activity</span><span>5% anti-fluke</span>
      </div>
    </section>
    <section className="cc-card cc-table-card">
      <div className="cc-panel-title"><h3>Active qualified wallets</h3><span>private admin view</span></div>
      <div className="cc-scroll-table cc-scroll-y cc-ranking-table-wrap">
        <table>
          <thead><tr><th>#</th><th>Wallet</th><th>Score</th><th>Account value</th><th>30d PnL</th><th>All-time PnL</th><th>Consistency</th><th>Drawdown</th><th>Anti-fluke</th><th>Formula</th></tr></thead>
          <tbody>{rows.map((r: any) => <tr key={r.wallet}>
            <td>{r.rank}</td><td>{mask(r.wallet)}</td><td>{Number(r.score || r.active_score || 0).toFixed(1)}</td><td>{money(r.account_value_usd)}</td><td>{money(r.pnl_30d_usd)}</td><td>{money(r.pnl_all_time_usd)}</td><td>{Number(r.consistency_score || 0).toFixed(0)}</td><td>{pct(r.max_drawdown_pct)}</td><td>{Number(r.anti_fluke_score || 0).toFixed(0)}</td><td>{r.ranking_formula}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>
  </main></>
}
