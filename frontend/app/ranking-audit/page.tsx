'use client'

import { useEffect, useState } from 'react'
import Nav from '../../components/Nav'
import { apiGet } from '../../lib/api'

function money(n: any) { return '$' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }) }
function value(n: any, suffix = '') { return n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 }) + suffix }
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
      <h3>Active ranking evidence</h3>
      <div className="cc-method-grid">
        <span>Verified net PnL</span><span>ROI / capital efficiency</span><span>Profitable-week consistency</span><span>Trading activity</span><span>Win rate</span><span>Profit factor</span><span>Largest-win concentration</span>
      </div>
    </section>
    <section className="cc-card cc-table-card">
      <div className="cc-panel-title"><h3>Active qualified wallets</h3><span>private admin view</span></div>
      <div className="cc-scroll-table cc-scroll-y cc-ranking-table-wrap">
        <table>
          <thead><tr><th>#</th><th>Wallet</th><th>Score</th><th>Account value</th><th>Net PnL</th><th>ROI</th><th>Active days</th><th>Profitable weeks</th><th>Win rate</th><th>Profit factor</th><th>Largest win share</th><th>Formula</th></tr></thead>
          <tbody>{rows.map((r: any) => <tr key={r.wallet}>
            <td>{r.rank}</td><td>{mask(r.wallet)}</td><td>{value(r.score ?? r.active_score)}</td><td>{r.account_value_usd == null ? '—' : money(r.account_value_usd)}</td><td>{r.net_pnl_usd == null ? '—' : money(r.net_pnl_usd)}</td><td>{value(r.roi_pct, '%')}</td><td>{value(r.active_days)}</td><td>{value(r.profitable_weeks)} / {value(r.observed_weeks)}</td><td>{value(r.win_rate_pct, '%')}</td><td>{value(r.profit_factor)}</td><td>{value(r.largest_win_share_pct, '%')}</td><td>{r.ranking_formula || '—'}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>
  </main></>
}
