'use client'
import { useEffect, useState } from 'react'
import Nav from '../../components/Nav'
import { apiGet } from '../../lib/api'

function money(n:any){return '$'+Number(n||0).toLocaleString(undefined,{maximumFractionDigits:0})}
function pct(n:any){return (Number(n||0)*100).toFixed(1)+'%'}
function cls(n:any){return Number(n)>=0?'positive':'negative'}

export default function Dashboard(){
  const [summary,setSummary]=useState<any>({}); const [signals,setSignals]=useState<any[]>([]); const [targets,setTargets]=useState<any[]>([]); const [flow,setFlow]=useState<any[]>([]); const [runs,setRuns]=useState<any[]>([]); const [err,setErr]=useState('')
  async function load(){try{setErr(''); const [s,si,t,f,r]=await Promise.all([apiGet('/api/summary'),apiGet('/api/signals'),apiGet('/api/targets'),apiGet('/api/flow'),apiGet('/api/runs')]); setSummary(s); setSignals(si); setTargets(t); setFlow(f); setRuns(r)}catch(e:any){setErr(e.message)}}
  useEffect(()=>{load(); const id=setInterval(load,60000); return()=>clearInterval(id)},[])
  return <><Nav/><main className="container"><h1>Smart-wallet dashboard</h1>{err&&<p className="warning">{err}</p>}<section className="grid section"><div className="card"><p className="muted">Qualified wallets</p><div className="metric">{summary.qualified_wallets||0}</div></div><div className="card"><p className="muted">Tracked account value</p><div className="metric">{money(summary.tracked_account_value_usd)}</div></div><div className="card"><p className="muted">Open position value</p><div className="metric">{money(summary.tracked_open_position_value_usd)}</div></div><div className="card"><p className="muted">Assets with signals</p><div className="metric">{summary.assets_with_signals||0}</div></div></section>
  <section className="section"><h2>Asset signals</h2><table><thead><tr><th>Asset</th><th>Signal</th><th>Confidence</th><th>Wallets</th><th>Value L/S</th><th>Net value</th><th>% total value</th></tr></thead><tbody>{signals.map(s=><tr key={s.coin}><td><b>{s.coin}</b></td><td className={cls(s.signal)}>{Number(s.signal).toFixed(2)}</td><td><span className="pill">{s.confidence}</span></td><td>{s.wallets_long} long / {s.wallets_short} short</td><td>{money(s.value_long_usd)} / {money(s.value_short_usd)}</td><td className={cls(s.net_value_usd)}>{money(s.net_value_usd)}</td><td>{pct(s.value_long_pct_total)} long / {pct(s.value_short_pct_total)} short</td></tr>)}</tbody></table></section>
  <section className="section"><h2>Recent buyer / seller pressure</h2><table><thead><tr><th>Asset</th><th>Net buyers</th><th>Bullish flow</th><th>Bearish flow</th><th>Net value flow</th><th>Read</th></tr></thead><tbody>{flow.map(s=><tr key={s.coin}><td><b>{s.coin}</b></td><td className={cls(s.net_buyer_count)}>{s.net_buyer_count}</td><td>{money(s.bullish_value_flow_usd)}</td><td>{money(s.bearish_value_flow_usd)}</td><td className={cls(s.net_value_flow_usd)}>{money(s.net_value_flow_usd)}</td><td>{s.net_buyer_count>3?'Accumulation':s.net_buyer_count<-3?'Distribution':'Neutral'}</td></tr>)}</tbody></table></section>
  <section className="section"><h2>Portfolio targets</h2><table><thead><tr><th>Asset</th><th>Target weight</th><th>Signal</th><th>Confidence</th></tr></thead><tbody>{targets.map(t=><tr key={t.coin}><td><b>{t.coin}</b></td><td>{pct(t.target_weight)}</td><td className={cls(t.signal)}>{Number(t.signal).toFixed(2)}</td><td>{t.confidence}</td></tr>)}</tbody></table></section>
  <section className="section"><h2>System runs</h2><table><thead><tr><th>Type</th><th>Status</th><th>Message</th></tr></thead><tbody>{runs.slice(0,8).map((r,i)=><tr key={i}><td>{r.run_type}</td><td>{r.status}</td><td>{r.message}</td></tr>)}</tbody></table></section>
  </main></>}
