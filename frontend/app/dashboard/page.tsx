'use client'

import { useEffect, useMemo, useState } from 'react'
import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import { apiGet } from '../../lib/api'

function money(n: any) { return '$' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }) }
function compactMoney(n: any) { const v=Math.abs(Number(n||0)); const sign=Number(n||0)<0?'-':''; if(v>=1e9)return sign+'$'+(v/1e9).toFixed(1)+'b'; if(v>=1e6)return sign+'$'+(v/1e6).toFixed(1)+'m'; if(v>=1e3)return sign+'$'+(v/1e3).toFixed(1)+'k'; return sign+'$'+v.toFixed(0) }
function pct(n:any){return (Number(n||0)*100).toFixed(1)+'%'}
function cls(n:any){return Number(n)>=0?'positive':'negative'}
function flowRead(n:any){return Number(n)>3?'Accumulation':Number(n)<-3?'Distribution':'Neutral'}
function fmtTime(ms:any){if(!ms)return 'Awaiting refresh'; const d=new Date(Number(ms)); return d.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'})}
function ago(ms:any){if(!ms)return 'latest'; const m=Math.max(0,Math.round((Date.now()-Number(ms))/60000)); if(m<1)return 'just now'; if(m<60)return `${m}m ago`; return `${Math.round(m/60)}h ago`}
function maskWallet(w:string){return w?`Wallet ${w.slice(0,4)}…${w.slice(-4)}`:'Top wallet'}

const palette=['#43E8D0','#8057FF','#44BDEC','#FFB020','#25D366','#F35EA6','#A6E22E','#FF5B72']
const fallbackColours:Record<string,string>={HYPE:'#43E8D0',ETH:'#627EEA',BTC:'#F7931A',SOL:'#14F195',ZEC:'#F4B728',NEAR:'#00EC97',AAVE:'#8B7DFF',TRX:'#FF4B4B',XRP:'#4B9FFF',USDC:'#2775CA'}

const staticLogoUrls: Record<string, string> = {
  BTC:'https://cryptologos.cc/logos/bitcoin-btc-logo.svg?v=040', ETH:'https://cryptologos.cc/logos/ethereum-eth-logo.svg?v=040',
  SOL:'https://cryptologos.cc/logos/solana-sol-logo.svg?v=040', USDC:'https://cryptologos.cc/logos/usd-coin-usdc-logo.svg?v=040',
  USDT:'https://cryptologos.cc/logos/tether-usdt-logo.svg?v=040', DOGE:'https://cryptologos.cc/logos/dogecoin-doge-logo.svg?v=040',
  AAVE:'https://cryptologos.cc/logos/aave-aave-logo.svg?v=040', TRX:'https://cryptologos.cc/logos/tron-trx-logo.svg?v=040',
  XRP:'https://cryptologos.cc/logos/xrp-xrp-logo.svg?v=040', AVAX:'https://cryptologos.cc/logos/avalanche-avax-logo.svg?v=040',
  BNB:'https://cryptologos.cc/logos/bnb-bnb-logo.svg?v=040', LINK:'https://cryptologos.cc/logos/chainlink-link-logo.svg?v=040',
  UNI:'https://cryptologos.cc/logos/uniswap-uni-logo.svg?v=040', LTC:'https://cryptologos.cc/logos/litecoin-ltc-logo.svg?v=040',
  DOT:'https://cryptologos.cc/logos/polkadot-new-dot-logo.svg?v=040', FIL:'https://cryptologos.cc/logos/filecoin-fil-logo.svg?v=040',
  ATOM:'https://cryptologos.cc/logos/cosmos-atom-logo.svg?v=040', NEAR:'https://cryptologos.cc/logos/near-protocol-near-logo.svg?v=040',
  ZEC:'https://cryptologos.cc/logos/zcash-zec-logo.svg?v=040', ARB:'https://cryptologos.cc/logos/arbitrum-arb-logo.svg?v=040',
  SUI:'https://cryptologos.cc/logos/sui-sui-logo.svg?v=040', OP:'https://cryptologos.cc/logos/optimism-ethereum-op-logo.svg?v=040',
  APE:'https://cryptologos.cc/logos/apecoin-ape-ape-logo.svg?v=040', INJ:'https://cryptologos.cc/logos/injective-inj-logo.svg?v=040',
  FET:'https://cryptologos.cc/logos/artificial-superintelligence-alliance-fet-logo.svg?v=040',
}

function iconSources(symbol: string, apiUrl?: string) {
  const clean = String(symbol || '').toUpperCase().replace(/[^A-Z0-9]/g, '')
  const lower = clean.toLowerCase()
  const sources = [
    apiUrl,
    staticLogoUrls[clean],
    // broad public icon set, good for large caps and many majors
    `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/svg/color/${lower}.svg`,
    // second public icon set used by several crypto dashboards
    `https://assets.coincap.io/assets/icons/${lower}@2x.png`,
  ].filter(Boolean) as string[]
  return sources
}

function TokenLogo({ coin, icons }: { coin:string, icons:Record<string,string> }) {
  const symbol=String(coin||'').toUpperCase()
  const [sourceIndex,setSourceIndex]=useState(0)
  const color=fallbackColours[symbol] || '#35f1cf'
  const sources=iconSources(symbol, icons[symbol])
  useEffect(()=>setSourceIndex(0),[symbol, icons[symbol]])
  const src=sources[sourceIndex]
  return <span className="token-logo" style={{['--coin' as any]:color}}>
    {src ? <img src={src} alt={`${symbol} logo`} onError={()=>setSourceIndex(i => i + 1)}/> : <span className="token-fallback-mark"><i/><b>{symbol.slice(0,2)}</b></span>}
  </span>
}

function Spark(){return <svg viewBox="0 0 92 32" className="mini-spark" aria-hidden="true"><path d="M2 25 L15 22 L27 24 L39 14 L51 20 L62 9 L74 12 L90 7"/></svg>}

function AllocationDonut({targets}:{targets:any[]}){
  const parts=useMemo(()=>{const clean=(targets||[]).filter(t=>Number(t.target_weight)>0).slice(0,6); const total=clean.reduce((a,t)=>a+Number(t.target_weight||0),0)||1; return clean.map((t,i)=>({coin:t.coin,weight:Number(t.target_weight||0)/total,color:palette[i%palette.length]}))},[targets])
  let angle=-90
  const path=(cx:number,cy:number,r1:number,r2:number,a0:number,a1:number)=>{const p=(r:number,a:number)=>{const rad=a*Math.PI/180; return {x:cx+r*Math.cos(rad),y:cy+r*Math.sin(rad)}}; const s1=p(r1,a0),e1=p(r1,a1),s2=p(r2,a1),e2=p(r2,a0); const large=a1-a0>180?1:0; return `M ${s1.x} ${s1.y} A ${r1} ${r1} 0 ${large} 1 ${e1.x} ${e1.y} L ${s2.x} ${s2.y} A ${r2} ${r2} 0 ${large} 0 ${e2.x} ${e2.y} Z`}
  if(!parts.length) return <div className="empty-state">Targets will appear after refresh.</div>
  return <div className="donut-layout"><svg viewBox="0 0 220 220" className="donut-svg">{parts.map(p=>{const start=angle; angle+=p.weight*360; return <path key={p.coin} d={path(110,110,92,58,start,angle-1)} fill={p.color}><title>{p.coin} {(p.weight*100).toFixed(1)}%</title></path>})}<circle cx="110" cy="110" r="52"/><text x="110" y="106" textAnchor="middle">TARGETS</text><text x="110" y="132" textAnchor="middle">{parts.length}</text></svg><div className="donut-legend">{parts.map(p=><div key={p.coin}><i style={{background:p.color}}/><b>{p.coin}</b><span>{(p.weight*100).toFixed(1)}%</span></div>)}</div></div>
}
function ExposureBars({signals,icons}:{signals:any[],icons:Record<string,string>}){
  const rows=(signals||[]).slice(0,6); const max=Math.max(1,...rows.map(r=>Number(r.value_long_usd||0)+Number(r.value_short_usd||0)))
  if(!rows.length)return <div className="empty-state">Exposure appears after refresh.</div>
  return <div className="exposure-list">{rows.map(r=>{const l=Number(r.value_long_usd||0),s=Number(r.value_short_usd||0); const total=l+s||1; return <div className="ex-row" key={r.coin}><div className="ex-name"><TokenLogo coin={r.coin} icons={icons}/><b>{r.coin}</b><span>{Number(r.signal).toFixed(2)}</span></div><div className="ex-track"><div style={{width:`${Math.max(7,((l+s)/max)*100)}%`}}><i style={{width:`${(l/total)*100}%`}}/><em style={{width:`${(s/total)*100}%`}}/></div></div><small>{compactMoney(l)}</small><small>{compactMoney(s)}</small></div>})}</div>
}

const marketRows=[['Total market cap','$2.61T','-0.76%'],['24h volume','$98.47B','+3.21%'],['BTC dominance','52.1%','+0.35%'],['ETH dominance','17.3%','-0.12%']]

export default function Dashboard(){
  const [summary,setSummary]=useState<any>({}); const [signals,setSignals]=useState<any[]>([]); const [targets,setTargets]=useState<any[]>([]); const [flow,setFlow]=useState<any[]>([]); const [orders,setOrders]=useState<any[]>([]); const [icons,setIcons]=useState<Record<string,string>>({}); const [err,setErr]=useState('')
  async function load(){try{setErr(''); const [s,si,t,f,o]=await Promise.all([apiGet('/api/summary'),apiGet('/api/signals?limit=30'),apiGet('/api/targets'),apiGet('/api/flow?limit=30'),apiGet('/api/recent-orders?limit=3').catch(()=>[])]); setSummary(s); setSignals(si); setTargets(t); setFlow(f); setOrders(o)}catch(e:any){setErr(e.message)}}
  useEffect(()=>{load(); const id=setInterval(load,30000); return ()=>clearInterval(id)},[])
  useEffect(()=>{const symbols=Array.from(new Set([...signals.map(r=>r.coin),...targets.map(r=>r.coin),...flow.map(r=>r.coin),...orders.map((r:any)=>r.coin)].filter(Boolean).map(x=>String(x).toUpperCase()))); if(!symbols.length)return; apiGet('/api/token-icons?symbols='+encodeURIComponent(symbols.join(','))).then((r:any)=>setIcons(r.icons||{})).catch(()=>{})},[signals,targets,flow,orders])
  const longValue=signals.reduce((a,r)=>a+Number(r.value_long_usd||0),0); const shortValue=signals.reduce((a,r)=>a+Number(r.value_short_usd||0),0); const isLong=longValue>=shortValue
  const orderRows=orders.length?orders:flow.slice(0,3).map((r:any)=>({coin:r.coin,side:Number(r.net_value_flow_usd)>=0?'Long':'Short',wallet_label:'Top wallet',wallet:r.wallet,ts_ms:summary.latest_signal_ts_ms}))
  return <><Nav/><main className="dashboard-shell"><LineBackdrop variant="dashboard"/><section className="dashboard-top"><div className="dash-copy"><p className="eyebrow live">Live smart-wallet tape</p><h1>Market intelligence.<br/><em>Follow the best.</em></h1><p>Value-weighted positioning from qualified Hyperliquid wallets.<br/>Built to show what serious traders are leaning into.</p></div><div className="bias-block"><span>Positioning bias</span><button className={`bias-pill ${isLong?'long':'short'}`}><i/>{isLong?'LONG':'SHORT'}</button></div><aside className="orders-card"><h3>Most recent orders</h3>{orderRows.slice(0,3).map((o:any,i:number)=><div className="order-line" key={i}><TokenLogo coin={o.coin} icons={icons}/><b>{o.coin}</b><span className={String(o.side).toLowerCase().includes('short')||String(o.side).toLowerCase().includes('reduce')?'negative':'positive'}>{o.side}</span><em>{o.wallet_label||maskWallet(o.wallet||'')}</em><small>{ago(o.ts_ms)}</small></div>)}<button className="small-action">View all orders →</button></aside><aside className="market-card"><h3>Market overview</h3>{marketRows.map(([label,value,change])=><div className="market-line" key={label}><div><small>{label}</small><b>{value}</b></div><span className={change.startsWith('-')?'negative':'positive'}>{change}</span></div>)}<div className="market-source"><span>Source: CoinGecko</span><a>View more →</a></div></aside></section>{err&&<p className="risk-bar amber-risk">{err}</p>}<section className="kpi-grid"><article><i className="round-icon users"/><small>Qualified wallets</small><b>{summary.qualified_wallets||0}</b><span>ranked daily</span><Spark/></article><article><i className="round-icon wallet"/><small>Tracked account value</small><b>{money(summary.tracked_account_value_usd)}</b><span>latest snapshots</span><Spark/></article><article><i className="round-icon chart"/><small>Open position value</small><b>{money(summary.tracked_open_position_value_usd)}</b><span>{summary.open_positions||0} live positions</span><Spark/></article><article><i className="round-icon bolt"/><small>Assets with signals</small><b>{summary.assets_with_signals||0}</b><span>cross-asset breadth</span><Spark/></article><article><i className="round-icon clock"/><small>Signal refresh</small><b>{fmtTime(summary.latest_signal_ts_ms)}</b><span>UTC</span></article></section><section className="chart-grid"><article className="analytics-card allocation"><h3>Portfolio allocation</h3><AllocationDonut targets={targets}/><p>Hover segments for details</p></article><article className="analytics-card exposure"><div className="card-head"><h3>Long vs short exposure</h3><span><i/> Long <em/> Short</span></div><ExposureBars signals={signals} icons={icons}/></article></section><section className="table-grid"><article className="analytics-card table-panel"><div className="card-head"><h3>Asset signal board</h3><span>value-weighted, not wallet-count only</span></div><div className="scroll-table"><table><thead><tr><th>#</th><th>Asset</th><th>Signal</th><th>Confidence</th><th>Wallets</th><th>Value L/S</th><th>Net value</th><th>% total value</th></tr></thead><tbody>{signals.slice(0,6).map((r,i)=><tr key={r.coin}><td>{i+1}</td><td><span className="asset-name"><TokenLogo coin={r.coin} icons={icons}/><b>{r.coin}</b></span></td><td className={cls(r.signal)}>{Number(r.signal).toFixed(2)}</td><td><span className={`badge ${String(r.confidence).toLowerCase()}`}>{r.confidence}</span></td><td>{r.wallets_long} long / {r.wallets_short} short</td><td>{money(r.value_long_usd)} / {money(r.value_short_usd)}</td><td className={cls(r.net_value_usd)}>{money(r.net_value_usd)}</td><td>{pct(r.value_long_pct_total)} long / {pct(r.value_short_pct_total)} short</td></tr>)}</tbody></table></div><a className="panel-link">View full signal board →</a></article><article className="analytics-card table-panel"><div className="card-head"><h3>Recent buyer / seller pressure</h3><span>largest flow changes first</span></div><div className="scroll-table"><table><thead><tr><th>Asset</th><th>Net buyers</th><th>Bullish flow</th><th>Bearish flow</th><th>Net value flow</th><th>Read</th></tr></thead><tbody>{flow.slice(0,5).map(r=>{const read=flowRead(r.net_buyer_count); return <tr key={r.coin}><td><span className="asset-name"><TokenLogo coin={r.coin} icons={icons}/><b>{r.coin}</b></span></td><td className={cls(r.net_buyer_count)}>{r.net_buyer_count}</td><td>{money(r.bullish_flow_usd)}</td><td>{money(r.bearish_flow_usd)}</td><td className={cls(r.net_value_flow_usd)}>{money(r.net_value_flow_usd)}</td><td><span className={`badge ${read.toLowerCase()}`}>{read}</span></td></tr>})}</tbody></table></div><a className="panel-link">View full pressure tape →</a></article></section><p className="risk-bar green-risk dashboard-risk"><i>♢</i><span>Market intelligence only. Not financial advice. Crypto trading can result in loss.</span><em>● Data updates every 30s</em></p></main></>
}
