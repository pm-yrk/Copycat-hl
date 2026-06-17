'use client'
import Nav from '../../components/Nav'
import { apiPost } from '../../lib/api'

export default function Pricing(){
  async function checkout(interval:string){ const r=await apiPost('/api/billing/create-checkout-session',{interval}); window.location.href=r.url }
  return <><Nav/><main className="container"><h1>Pricing</h1><div className="grid3 section"><div className="card"><h2>Preview</h2><p className="metric">Free</p><p className="muted">Delayed sample dashboard.</p><button className="btn secondary">Coming soon</button></div><div className="card"><h2>Pro</h2><p className="metric">Monthly</p><p className="muted">Live dashboard, 15-minute updates, Telegram group alerts.</p><button className="btn" onClick={()=>checkout('monthly')}>Start monthly</button></div><div className="card"><h2>Annual</h2><p className="metric">Best value</p><p className="muted">Same Pro features with annual billing.</p><button className="btn" onClick={()=>checkout('annual')}>Start annual</button></div></div><p className="warning">The dashboard is research and market-intelligence software. It does not provide personalized financial advice.</p></main></>
}
