'use client'
import { useEffect, useMemo, useState } from 'react'
import Nav from '../../components/Nav'
import { apiGet } from '../../lib/api'

function money(n:any){return '$'+Number(n||0).toLocaleString(undefined,{maximumFractionDigits:0})}
function compactMoney(n:any){const v=Math.abs(Number(n||0)); const sign=Number(n||0)<0?'-':''; if(v>=1_000_000_000)return sign+'$'+(v/1_000_000_000).toFixed(1)+'b'; if(v>=1_000_000)return sign+'$'+(v/1_000_000).toFixed(1)+'m'; if(v>=1_000)return sign+'$'+(v/1_000).toFixed(1)+'k'; return sign+'$'+v.toFixed(0)}
function pct(n:any){return (Number(n||0)*100).toFixed(1)+'%'}
function cls(n:any){return Number(n)>=0?'positive':'negative'}
function readFlow(n:any){return Number(n)>3?'Accumulation':Number(n)<-3?'Distribution':'Neutral'}
function fmtTime(ms:any){if(!ms)return 'Awaiting refresh'; const d=new Date(Number(ms)); return d.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'})}

const palette=['#38f8d8','#7c5cff','#38bdf8','#f59e0b','#22c55e','#f472b6','#a3e635','#fb7185']

type Segment={coin:string; weight:number; color:string}
function polar(cx:number,cy:number,r:number,angle:number){const a=(angle-90)*Math.PI/180; return {x:cx+r*Math.cos(a), y:cy+r*Math.sin(a)}}
function donutPath(cx:number,cy:number,outer:number,inner:number,start:number,end:number){
  const s1=polar(cx,cy,outer,start), e1=polar(cx,cy,outer,end), s2=polar(cx,cy,inner,start), e2=polar(cx,cy,inner,end)
  const large=end-start>180?1:0
  return `M ${s1.x} ${s1.y} A ${outer} ${outer} 0 ${large} 1 ${e1.x} ${e1.y} L ${e2.x} ${e2.y} A ${inner} ${inner} 0 ${large} 0 ${s2.x} ${s2.y} Z`
}
function AllocationDonut({targets}:{targets:any[]}){
  const parts:Segment[]=useMemo(()=>{
    const clean=(targets||[]).filter(t=>Number(t.target_weight)>0).slice(0,8)
    const total=clean.reduce((a,t)=>a+Number(t.target_weight||0),0)||1
    return clean.map((t,i)=>({coin:t.coin,weight:Number(t.target_weight||0)/total,color:palette[i%palette.length]}))
  },[targets])
  let angle=0
  if(!parts.length)return <div className="empty-chart">Targets will appear after the collector runs.</div>
  return <div className="donut-wrap"><svg viewBox="0 0 220 220" className="donut" role="img" aria-label="Portfolio target allocation donut">
    <circle cx="110" cy="110" r="88" fill="rgba(255,255,255,.025)" />
    {parts.map((p)=>{const start=angle; angle+=p.weight*360; return <path key={p.coin} d={donutPath(110,110,92,58,start,angle-.8)} fill={p.color} className="donut-seg"><title>{p.coin} {(p.weight*100).toFixed(1)}%</title></path>})}
    <circle cx="110" cy="110" r="52" fill="#080d17" />
    <text x="110" y="105" textAnchor="middle" className="donut-kicker">TARGETS</text>
    <text x="110" y="130" textAnchor="middle" className="donut-number">{parts.length}</text>
  </svg><div className="legend">{parts.map(p=><div className="legend-row" key={p.coin}><span style={{background:p.color}}/><b>{p.coin}</b><em>{(p.weight*100).toFixed(1)}%</em></div>)}</div></div>
}
function ExposureBars({signals}:{signals:any[]}){
  const rows=(signals||[]).slice(0,8)
  const max=Math.max(1,...rows.map(r=>Number(r.value_long_usd||0)+Number(r.value_short_usd||0)))
  if(!rows.length)return <div className="empty-chart">Exposure bars will appear after the collector runs.</div>
  return <div className="bars-list">{rows.map(r=>{const l=Number(r.value_long_usd||0), s=Number(r.value_short_usd||0); const lw=Math.max(2,(l/max)*100), sw=Math.max(2,(s/max)*100); return <div className="bar-row" key={r.coin}><div className="bar-label"><b>{r.coin}</b><span>{Number(r.signal).toFixed(2)}</span></div><div className="bar-track" title={`${r.coin}: long ${money(l)} / short ${money(s)}`}><i className="bar-long" style={{width:`${lw}%`}}/><i className="bar-short" style={{width:`${sw}%`}}/></div><div className="bar-values"><span>{compactMoney(l)}</span><span>{compactMoney(s)}</span></div></div>})}</div>
}

export default function Dashboard(){
  const [summary,setSummary]=useState<any>({}); const [signals,setSignals]=useState<any[]>([]); const [targets,setTargets]=useState<any[]>([]); const [flow,setFlow]=useState<any[]>([]); const [err,setErr]=useState('')
  async function load(){try{setErr(''); const [s,si,t,f]=await Promise.all([apiGet('/api/summary'),apiGet('/api/signals'),apiGet('/api/targets'),apiGet('/api/flow')]); setSummary(s); setSignals(si); setTargets(t); setFlow(f)}catch(e:any){setErr(e.message)}}
  useEffect(()=>{load(); const id=setInterval(load,60000); return()=>clearInterval(id)},[])
  const topSignal=signals[0]
  const strongestFlow=flow[0]
  return <><Nav/><main className="container dashboard-container"><section className="dashboard-hero"><div><p className="eyebrow live-dot">Live smart-wallet tape</p><h1>copycat.hl dashboard</h1><p className="muted">Value-weighted positioning from qualified Hyperliquid wallets. Built to show what serious traders are leaning into, and what they are quietly distributing.</p></div><div className="refresh-card"><span>Last signal refresh</span><b>{fmtTime(summary.latest_signal_ts_ms)}</b></div></section>{err&&<p className="warning">{err}</p>}

  <section className="metric-grid section"><div className="card metric-card glow"><p className="muted">Qualified wallets</p><div className="metric">{summary.qualified_wallets||0}</div><small>ranked daily</small></div><div className="card metric-card"><p className="muted">Tracked account value</p><div className="metric">{money(summary.tracked_account_value_usd)}</div><small>latest snapshots</small></div><div className="card metric-card"><p className="muted">Open position value</p><div className="metric">{money(summary.tracked_open_position_value_usd)}</div><small>{summary.open_positions||0} live positions</small></div><div className="card metric-card"><p className="muted">Assets with signals</p><div className="metric">{summary.assets_with_signals||0}</div><small>cross-asset breadth</small></div></section>

  <section className="insight-grid section"><div className="card feature-card"><span className="tag hot-tag">Top signal</span><h2>{topSignal?.coin||'—'}</h2><p className={topSignal?cls(topSignal.signal):''}>{topSignal?Number(topSignal.signal).toFixed(2):'Awaiting data'}</p><small>{topSignal?`${topSignal.wallets_long} long / ${topSignal.wallets_short} short · ${compactMoney(topSignal.net_value_usd)} net`:'Run the collector to populate this card.'}</small></div><div className="card feature-card"><span className="tag">Biggest flow</span><h2>{strongestFlow?.coin||'—'}</h2><p className={strongestFlow?cls(strongestFlow.net_value_flow_usd):''}>{strongestFlow?compactMoney(strongestFlow.net_value_flow_usd):'Awaiting data'}</p><small>{strongestFlow?`${readFlow(strongestFlow.net_buyer_count)} · ${strongestFlow.net_buyer_count} net buyers`:'Recent flow will appear here.'}</small></div><div className="card feature-card"><span className="tag">Portfolio mode</span><h2>{targets?.[0]?.coin||'Reserve'}</h2><p>{targets?.[0]?pct(targets[0].target_weight):'—'}</p><small>Highest target allocation from current signal set.</small></div></section>

  <section className="chart-grid section"><div className="card chart-card"><div className="section-head"><div><p className="eyebrow">Allocation</p><h2>Portfolio targets</h2></div><span className="hint">hover segments</span></div><AllocationDonut targets={targets}/></div><div className="card chart-card"><div className="section-head"><div><p className="eyebrow">Exposure</p><h2>Long vs short value</h2></div><div className="bar-key"><span className="key-long">Long</span><span className="key-short">Short</span></div></div><ExposureBars signals={signals}/></div></section>

  <section className="section"><div className="section-head"><div><p className="eyebrow">Signals</p><h2>Asset signal board</h2></div><span className="hint">value-weighted, not wallet-count only</span></div><div className="table-wrap"><table><thead><tr><th>Asset</th><th>Signal</th><th>Confidence</th><th>Wallets</th><th>Value L/S</th><th>Net value</th><th>% total value</th></tr></thead><tbody>{signals.map(s=><tr key={s.coin}><td><b>{s.coin}</b></td><td className={cls(s.signal)}>{Number(s.signal).toFixed(2)}</td><td><span className={`pill conf-${String(s.confidence||'').toLowerCase()}`}>{s.confidence}</span></td><td>{s.wallets_long} long / {s.wallets_short} short</td><td>{money(s.value_long_usd)} / {money(s.value_short_usd)}</td><td className={cls(s.net_value_usd)}>{money(s.net_value_usd)}</td><td>{pct(s.value_long_pct_total)} long / {pct(s.value_short_pct_total)} short</td></tr>)}</tbody></table></div></section>

  <section className="section"><div className="section-head"><div><p className="eyebrow">Tape</p><h2>Recent buyer / seller pressure</h2></div><span className="hint">largest flow changes first</span></div><div className="table-wrap"><table><thead><tr><th>Asset</th><th>Net buyers</th><th>Bullish flow</th><th>Bearish flow</th><th>Net value flow</th><th>Read</th></tr></thead><tbody>{flow.map(s=><tr key={s.coin}><td><b>{s.coin}</b></td><td className={cls(s.net_buyer_count)}>{s.net_buyer_count}</td><td>{money(s.bullish_value_flow_usd)}</td><td>{money(s.bearish_value_flow_usd)}</td><td className={cls(s.net_value_flow_usd)}>{money(s.net_value_flow_usd)}</td><td><span className={`pill read-${readFlow(s.net_buyer_count).toLowerCase()}`}>{readFlow(s.net_buyer_count)}</span></td></tr>)}</tbody></table></div></section>
  </main></>}
