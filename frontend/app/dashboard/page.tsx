'use client'

import { useEffect, useMemo, useState } from 'react'
import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import { apiGet } from '../../lib/api'

function money(n: any) {
  return '$' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })
}
function compactMoney(n: any) {
  const num = Number(n || 0)
  const v = Math.abs(num)
  const sign = num < 0 ? '-' : ''
  if (v >= 1_000_000_000) return `${sign}$${(v / 1_000_000_000).toFixed(1)}b`
  if (v >= 1_000_000) return `${sign}$${(v / 1_000_000).toFixed(1)}m`
  if (v >= 1_000) return `${sign}$${(v / 1_000).toFixed(1)}k`
  return `${sign}$${v.toFixed(0)}`
}
function pct(n: any) { return (Number(n || 0) * 100).toFixed(1) + '%' }
function cls(n: any) { return Number(n) >= 0 ? 'positive' : 'negative' }
function flowRead(n: any) { return Number(n) > 3 ? 'Accumulation' : Number(n) < -3 ? 'Distribution' : 'Neutral' }
function ago(ms: any) { const m = Math.max(0, Math.round((Date.now() - Number(ms || Date.now())) / 60000)); if (m < 1) return 'just now'; if (m < 60) return `${m}m ago`; return `${Math.round(m / 60)}h ago` }
function fmtTime(ms: any) {
  if (!ms) return 'Awaiting first refresh'
  return new Date(Number(ms)).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }).replace(',', '')
}
function maskWallet(w: string) { return w ? `Wallet ${w.slice(0, 4)}…${w.slice(-4)}` : 'Wallet 0x…' }

const palette = ['#43E8D0', '#8057FF', '#44BDEC', '#FFB020', '#25D366', '#F35EA6', '#A6E22E', '#FF5B72', '#38BDF8', '#F97316']
const fallbackColours: Record<string, string> = { HYPE:'#43E8D0', ETH:'#627EEA', BTC:'#F7931A', SOL:'#14F195', ZEC:'#F4B728', NEAR:'#00EC97', AAVE:'#8B7DFF', TRX:'#FF4B4B', XRP:'#4B9FFF', USDC:'#2775CA', 'USDC/CASH':'#2775CA', MELANIA:'#D7A785', WLD:'#8492A6' }
const staticLogoUrls: Record<string, string> = {
  BTC:'https://cryptologos.cc/logos/bitcoin-btc-logo.svg?v=040', ETH:'https://cryptologos.cc/logos/ethereum-eth-logo.svg?v=040', SOL:'https://cryptologos.cc/logos/solana-sol-logo.svg?v=040', USDC:'https://cryptologos.cc/logos/usd-coin-usdc-logo.svg?v=040', USDT:'https://cryptologos.cc/logos/tether-usdt-logo.svg?v=040', DOGE:'https://cryptologos.cc/logos/dogecoin-doge-logo.svg?v=040',
  AAVE:'https://cryptologos.cc/logos/aave-aave-logo.svg?v=040', TRX:'https://cryptologos.cc/logos/tron-trx-logo.svg?v=040', XRP:'https://cryptologos.cc/logos/xrp-xrp-logo.svg?v=040', AVAX:'https://cryptologos.cc/logos/avalanche-avax-logo.svg?v=040', BNB:'https://cryptologos.cc/logos/bnb-bnb-logo.svg?v=040', LINK:'https://cryptologos.cc/logos/chainlink-link-logo.svg?v=040', UNI:'https://cryptologos.cc/logos/uniswap-uni-logo.svg?v=040', LTC:'https://cryptologos.cc/logos/litecoin-ltc-logo.svg?v=040', DOT:'https://cryptologos.cc/logos/polkadot-new-dot-logo.svg?v=040', FIL:'https://cryptologos.cc/logos/filecoin-fil-logo.svg?v=040', ATOM:'https://cryptologos.cc/logos/cosmos-atom-logo.svg?v=040', NEAR:'https://cryptologos.cc/logos/near-protocol-near-logo.svg?v=040', ZEC:'https://cryptologos.cc/logos/zcash-zec-logo.svg?v=040', ARB:'https://cryptologos.cc/logos/arbitrum-arb-logo.svg?v=040', SUI:'https://cryptologos.cc/logos/sui-sui-logo.svg?v=040', OP:'https://cryptologos.cc/logos/optimism-ethereum-op-logo.svg?v=040', APE:'https://cryptologos.cc/logos/apecoin-ape-ape-logo.svg?v=040', INJ:'https://cryptologos.cc/logos/injective-inj-logo.svg?v=040', FET:'https://cryptologos.cc/logos/artificial-superintelligence-alliance-fet-logo.svg?v=040'
}
function iconSources(symbol: string, apiUrl?: string) {
  const clean = String(symbol || '').toUpperCase().replace(/[^A-Z0-9]/g, '')
  const lower = clean.toLowerCase()
  return [apiUrl, staticLogoUrls[clean], `https://assets.coincap.io/assets/icons/${lower}@2x.png`, `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/svg/color/${lower}.svg`, `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/${lower}.png`, `https://s3-symbol-logo.tradingview.com/crypto/XTVC${clean}.svg`].filter(Boolean) as string[]
}
function TokenLogo({ coin, icons }: { coin: string, icons: Record<string, string> }) {
  const symbol = String(coin || '').toUpperCase()
  const [sourceIndex, setSourceIndex] = useState(0)
  const color = fallbackColours[symbol] || '#35f1cf'
  const sources = iconSources(symbol, icons[symbol])
  useEffect(() => setSourceIndex(0), [symbol, icons[symbol]])
  const src = sources[sourceIndex]
  return <span className="cc-token-logo" style={{ ['--coin' as any]: color }}>
    {src ? <img src={src} alt={`${symbol} logo`} onError={() => setSourceIndex(i => i + 1)} /> : <span className="cc-token-fallback"><i /><b>{symbol.slice(0, 2)}</b></span>}
  </span>
}

type Segment = { coin: string; weight: number; color: string; originalWeight: number }
function AllocationDonut({ targets }: { targets: any[] }) {
  const [hovered, setHovered] = useState<Segment | null>(null)
  const parts: Segment[] = useMemo(() => {
    const clean = (targets || []).filter(t => Number(t.target_weight) > 0).slice(0, 10)
    const total = clean.reduce((a, t) => a + Number(t.target_weight || 0), 0) || 1
    return clean.map((t, i) => ({ coin: t.coin, originalWeight: Number(t.target_weight || 0), weight: Number(t.target_weight || 0) / total, color: palette[i % palette.length] }))
  }, [targets])
  let angle = -90
  const path = (cx: number, cy: number, r1: number, r2: number, a0: number, a1: number) => {
    const p = (r: number, a: number) => { const rad = a * Math.PI / 180; return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) } }
    const s1 = p(r1, a0), e1 = p(r1, a1), s2 = p(r2, a1), e2 = p(r2, a0); const large = a1 - a0 > 180 ? 1 : 0
    return `M ${s1.x} ${s1.y} A ${r1} ${r1} 0 ${large} 1 ${e1.x} ${e1.y} L ${s2.x} ${s2.y} A ${r2} ${r2} 0 ${large} 0 ${e2.x} ${e2.y} Z`
  }
  if (!parts.length) return <div className="cc-empty-state">Targets will appear after refresh.</div>
  return <div className="cc-donut-layout">
    <div className="cc-donut-stage">
      <svg viewBox="0 0 220 220" className="cc-donut-svg" aria-label="Portfolio target allocation">
        {parts.map(p => { const start = angle; angle += p.weight * 360; return <path key={p.coin} d={path(110, 110, 92, 58, start, angle - 1)} fill={p.color} onMouseEnter={() => setHovered(p)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(p)} onBlur={() => setHovered(null)} tabIndex={0}><title>{p.coin}: {(p.originalWeight * 100).toFixed(1)}%</title></path> })}
        <circle cx="110" cy="110" r="52" />
        <text x="110" y="106" textAnchor="middle">TARGETS</text>
        <text x="110" y="132" textAnchor="middle">{parts.length}</text>
      </svg>
      <div className="cc-donut-tooltip">{hovered ? `${hovered.coin} ${(hovered.originalWeight * 100).toFixed(1)}% target` : 'Hover a segment for details'}</div>
    </div>
    <div className="cc-donut-legend">{parts.map(p => <div key={p.coin}><i style={{ background: p.color }} /><b>{p.coin}</b><span>{(p.originalWeight * 100).toFixed(1)}%</span></div>)}</div>
  </div>
}
function ExposureBars({ signals, icons }: { signals: any[], icons: Record<string, string> }) {
  const rows = (signals || []).slice(0, 8); const max = Math.max(1, ...rows.map(r => Number(r.value_long_usd || 0) + Number(r.value_short_usd || 0)))
  if (!rows.length) return <div className="cc-empty-state">Exposure appears after refresh.</div>
  return <div className="cc-exposure-list">{rows.map(r => { const l = Number(r.value_long_usd || 0), s = Number(r.value_short_usd || 0); const total = l + s || 1; return <div className="cc-ex-row" key={r.coin}><div className="cc-ex-name"><TokenLogo coin={r.coin} icons={icons} /><b>{r.coin}</b><span>{Number(r.signal).toFixed(2)}</span></div><div className="cc-ex-track"><div style={{ width: `${Math.max(7, ((l + s) / max) * 100)}%` }}><i style={{ width: `${(l / total) * 100}%` }} /><em style={{ width: `${(s / total) * 100}%` }} /></div></div><small>{compactMoney(l)}</small><small>{compactMoney(s)}</small></div> })}</div>
}

export default function Dashboard() {
  const [summary, setSummary] = useState<any>({})
  const [signals, setSignals] = useState<any[]>([])
  const [targets, setTargets] = useState<any[]>([])
  const [flow, setFlow] = useState<any[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const [icons, setIcons] = useState<Record<string, string>>({})
  const [err, setErr] = useState('')

  async function load() {
    try {
      setErr('')
      const [s, si, t, f, o] = await Promise.all([apiGet('/api/summary'), apiGet('/api/signals?limit=40'), apiGet('/api/targets'), apiGet('/api/flow?limit=40'), apiGet('/api/recent-orders?limit=3').catch(() => [])])
      setSummary(s); setSignals(si); setTargets(t); setFlow(f); setOrders(o)
    } catch (e: any) { setErr(e.message) }
  }

  useEffect(() => { window.history.scrollRestoration = 'manual'; window.scrollTo(0, 0); load(); const id = setInterval(load, 30000); return () => clearInterval(id) }, [])
  useEffect(() => {
    const symbols = Array.from(new Set([...signals.map(r => r.coin), ...targets.map(r => r.coin), ...flow.map(r => r.coin), ...orders.map((r: any) => r.coin)].filter(Boolean).map(x => String(x).toUpperCase())))
    if (!symbols.length) return
    apiGet('/api/token-icons?symbols=' + encodeURIComponent(symbols.join(','))).then((r: any) => setIcons(r.icons || {})).catch(() => {})
  }, [signals, targets, flow, orders])

  const longValue = signals.reduce((a, r) => a + Number(r.value_long_usd || 0), 0)
  const shortValue = signals.reduce((a, r) => a + Number(r.value_short_usd || 0), 0)
  const isLong = longValue >= shortValue
  const orderRows = orders.length ? orders : flow.slice(0, 3).map((r: any) => ({ coin: r.coin, side: Number(r.net_value_flow_usd) >= 0 ? 'Long' : 'Short', wallet_label: 'Wallet 0x1A…7F3B', wallet: r.wallet, ts_ms: summary.latest_signal_ts_ms }))

  return <><Nav /><main className="cc-dashboard-shell"><LineBackdrop variant="dashboard" />
    <section className="cc-dashboard-top">
      <div className="cc-dashboard-copy">
        <p className="eyebrow live">Live smart-wallet tape</p>
        <h1>Market intelligence.<br /><em>Follow the best.</em></h1>
        <p>Value-weighted positioning from qualified Hyperliquid wallets.<br />Built to show what serious traders are leaning into.</p>
      </div>
      <div className="cc-bias-block"><span>Positioning bias</span><button className={`cc-bias-toggle ${isLong ? 'is-long' : 'is-short'}`}><i /><b>{isLong ? 'LONG' : 'SHORT'}</b></button></div>
      <aside className="cc-orders-card">
        <h3>Most recent orders</h3>
        {orderRows.map((o: any, i: number) => <div className="cc-order-line" key={`${o.coin}-${i}`}><TokenLogo coin={o.coin} icons={icons} /><b>{o.coin}</b><span className={String(o.side).toLowerCase().includes('short') || String(o.side).toLowerCase().includes('reduce') ? 'negative' : 'positive'}>{o.side}</span><em>{o.wallet_label || maskWallet(o.wallet)}</em><small>{ago(o.ts_ms)}</small></div>)}
        <button className="cc-small-action">View all orders →</button>
      </aside>
    </section>

    {err && <p className="notice gold">{err}</p>}

    <section className="cc-kpi-grid">
      <article><small>Qualified wallets</small><b>{summary.qualified_wallets || 0}</b><span>ranked daily</span></article>
      <article><small>Tracked account value</small><b>{money(summary.tracked_account_value_usd)}</b><span>latest snapshots</span></article>
      <article><small>Open position value</small><b>{money(summary.tracked_open_position_value_usd)}</b><span>{summary.open_positions || 0} live positions</span></article>
      <article><small>Assets with signals</small><b>{summary.assets_with_signals || 0}</b><span>cross-asset breadth</span></article>
    </section>

    <section className="cc-chart-grid">
      <div className="cc-card cc-allocation-card"><h3>Portfolio allocation</h3><AllocationDonut targets={targets} /></div>
      <div className="cc-card cc-exposure-card"><div className="cc-panel-title"><h3>Long vs short exposure</h3><span><i />Long <em />Short</span></div><ExposureBars signals={signals} icons={icons} /></div>
    </section>

    <section className="cc-table-grid">
      <div className="cc-card cc-table-card"><div className="cc-panel-title"><h3>Asset signal board</h3><span>value-weighted, not wallet-count only</span></div><div className="cc-scroll-table"><table><thead><tr><th>#</th><th>Asset</th><th>Signal</th><th>Confidence</th><th>Wallets</th><th>Value L/S</th><th>Net value</th><th>% total value</th></tr></thead><tbody>{signals.slice(0, 10).map((r, i) => <tr key={r.coin}><td>{i + 1}</td><td><span className="cc-asset-cell"><TokenLogo coin={r.coin} icons={icons} /><b>{r.coin}</b></span></td><td className={cls(r.signal)}>{Number(r.signal).toFixed(2)}</td><td><span className={`cc-confidence ${String(r.confidence).toLowerCase()}`}>{r.confidence}</span></td><td>{r.wallets_long} long / {r.wallets_short} short</td><td>{money(r.value_long_usd)} / {money(r.value_short_usd)}</td><td className={cls(r.net_value_usd)}>{money(r.net_value_usd)}</td><td>{pct(r.value_long_pct_total)} long / {pct(r.value_short_pct_total)} short</td></tr>)}</tbody></table></div></div>
      <div className="cc-card cc-table-card"><div className="cc-panel-title"><h3>Recent buyer / seller pressure</h3><span>largest flow changes first</span></div><div className="cc-scroll-table"><table><thead><tr><th>Asset</th><th>Net buyers</th><th>Bullish flow</th><th>Bearish flow</th><th>Net value flow</th><th>Read</th></tr></thead><tbody>{flow.slice(0, 8).map((r) => { const read = flowRead(r.net_buyer_count); return <tr key={r.coin}><td><span className="cc-asset-cell"><TokenLogo coin={r.coin} icons={icons} /><b>{r.coin}</b></span></td><td className={cls(r.net_buyer_count)}>{r.net_buyer_count}</td><td>{money(r.bullish_flow_usd)}</td><td>{money(r.bearish_flow_usd)}</td><td className={cls(r.net_value_flow_usd)}>{money(r.net_value_flow_usd)}</td><td><span className={`cc-read ${read.toLowerCase()}`}>{read}</span></td></tr> })}</tbody></table></div></div>
    </section>

    <footer className="cc-warning-banner"><span className="cc-shield">♜</span><strong>Market intelligence only.</strong><em>Not financial advice. Crypto trading can result in loss.</em><small>Signal refresh: {fmtTime(summary.latest_signal_ts_ms)} UTC · Data updates every 30s</small></footer>
  </main></>
}
