'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
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
function pct(n: any) { return Math.round(Number(n || 0) * 100) + '%' }
function uiPct(n: any, digits = 0) {
  const num = Number(n || 0) * 100
  return `${num.toFixed(digits)}%`
}
function signalPct(n: any) {
  return `${Math.round(Number(n || 0) * 100)}%`
}
function longSharePct(longUsd: any, shortUsd: any) {
  const l = Number(longUsd || 0)
  const sh = Number(shortUsd || 0)
  const total = l + sh
  if (total <= 0) return '0%'
  const share = (l / total) * 100
  return `${Math.round(share)}%`
}
function displaySignalValue(row: any) {
  // Customer-facing signal = value-weighted directional majority.
  // If an asset is mostly long, show the long share. If mostly short, show the
  // short share as a negative number. This keeps the signal board, at-a-glance
  // card, and long/short exposure bars mathematically aligned.
  const l = Number(row?.value_long_usd || 0)
  const sh = Number(row?.value_short_usd || 0)
  const total = l + sh
  if (total <= 0) return Number(row?.signal || 0)
  return l >= sh ? l / total : -(sh / total)
}
function displaySignalPct(row: any) {
  const v = displaySignalValue(row) * 100
  return `${Math.round(v)}%`
}
function cls(n: any) { return Number(n) >= 0 ? 'positive' : 'negative' }
function flowRead(netValueFlowUsd: any) {
  const n = Number(netValueFlowUsd || 0)
  return n > 1000 ? 'Accumulation' : n < -1000 ? 'Distribution' : 'Neutral'
}
function orderActionClass(side: any) {
  const s = String(side || '').toLowerCase()
  if (s.includes('open short') || s.includes('add short') || s.includes('reduce long') || s.includes('close long')) return 'negative'
  return 'positive'
}
function ago(ms: any) { const m = Math.max(0, Math.round((Date.now() - Number(ms || Date.now())) / 60000)); if (m < 1) return 'just now'; if (m < 60) return `${m}m ago`; return `${Math.round(m / 60)}h ago` }
function fmtTime(ms: any) {
  if (!ms) return 'Awaiting first refresh'
  return new Date(Number(ms)).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }).replace(',', '')
}
function maskWallet(w: string) { return w ? `Wallet ${w.slice(0, 4)}…${w.slice(-4)}` : 'Wallet 0x…' }

const USDC_LOGO_DATA_URI = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxMjggMTI4Jz48Y2lyY2xlIGN4PSc2NCcgY3k9JzY0JyByPSc2NCcgZmlsbD0nIzI3NzVDQScvPjxwYXRoIGQ9J000MiAzMGE0MiA0MiAwIDAgMCAwIDY4JyBmaWxsPSdub25lJyBzdHJva2U9JyNmZmYnIHN0cm9rZS13aWR0aD0nOCcgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJy8+PHBhdGggZD0nTTg2IDMwYTQyIDQyIDAgMCAxIDAgNjgnIGZpbGw9J25vbmUnIHN0cm9rZT0nI2ZmZicgc3Ryb2tlLXdpZHRoPSc4JyBzdHJva2UtbGluZWNhcD0ncm91bmQnLz48dGV4dCB4PSc2NCcgeT0nODQnIHRleHQtYW5jaG9yPSdtaWRkbGUnIGZvbnQtZmFtaWx5PSdBcmlhbCxIZWx2ZXRpY2Esc2Fucy1zZXJpZicgZm9udC1zaXplPSc1OCcgZm9udC13ZWlnaHQ9JzgwMCcgZmlsbD0nI2ZmZic+JDwvdGV4dD48L3N2Zz4='
const palette = ['#43E8D0', '#8057FF', '#44BDEC', '#FFB020', '#25D366', '#F35EA6', '#A6E22E', '#FF5B72', '#38BDF8', '#F97316']
const fallbackColours: Record<string, string> = { HYPE:'#43E8D0', ETH:'#627EEA', BTC:'#F7931A', SOL:'#14F195', ZEC:'#F4B728', NEAR:'#00EC97', AAVE:'#8B7DFF', TRX:'#FF4B4B', XRP:'#4B9FFF', USDC:'#2775CA', 'USDC/CASH':'#2775CA', MELANIA:'#D7A785', WLD:'#8492A6', PAXG:'#F0C419', PUMP:'#61C685', LIT:'#35D0B4', BNB:'#F3BA2F', XLM:'#44BDEC', PENGU:'#A0D7F8' }
const staticLogoUrls: Record<string, string> = {
  BTC:'https://cryptologos.cc/logos/bitcoin-btc-logo.svg?v=040', ETH:'https://cryptologos.cc/logos/ethereum-eth-logo.svg?v=040', SOL:'https://cryptologos.cc/logos/solana-sol-logo.svg?v=040', USDC:'https://raw.githubusercontent.com/trustwallet/assets/master/blockchains/ethereum/assets/A0b86991c6218b36c1d19d4a2e9eb0ce3606eb48/logo.png', USDT:'https://cryptologos.cc/logos/tether-usdt-logo.svg?v=040', DOGE:'https://cryptologos.cc/logos/dogecoin-doge-logo.svg?v=040',
  AAVE:'https://cryptologos.cc/logos/aave-aave-logo.svg?v=040', TRX:'https://cryptologos.cc/logos/tron-trx-logo.svg?v=040', XRP:'https://cryptologos.cc/logos/xrp-xrp-logo.svg?v=040', AVAX:'https://cryptologos.cc/logos/avalanche-avax-logo.svg?v=040', BNB:'https://cryptologos.cc/logos/bnb-bnb-logo.svg?v=040', LINK:'https://cryptologos.cc/logos/chainlink-link-logo.svg?v=040', UNI:'https://cryptologos.cc/logos/uniswap-uni-logo.svg?v=040', LTC:'https://cryptologos.cc/logos/litecoin-ltc-logo.svg?v=040', DOT:'https://cryptologos.cc/logos/polkadot-new-dot-logo.svg?v=040', FIL:'https://cryptologos.cc/logos/filecoin-fil-logo.svg?v=040', ATOM:'https://cryptologos.cc/logos/cosmos-atom-logo.svg?v=040', NEAR:'https://cryptologos.cc/logos/near-protocol-near-logo.svg?v=040', ZEC:'https://cryptologos.cc/logos/zcash-zec-logo.svg?v=040', ARB:'https://cryptologos.cc/logos/arbitrum-arb-logo.svg?v=040', SUI:'https://cryptologos.cc/logos/sui-sui-logo.svg?v=040', OP:'https://cryptologos.cc/logos/optimism-ethereum-op-logo.svg?v=040', APE:'https://cryptologos.cc/logos/apecoin-ape-ape-logo.svg?v=040', INJ:'https://cryptologos.cc/logos/injective-inj-logo.svg?v=040', FET:'https://cryptologos.cc/logos/artificial-superintelligence-alliance-fet-logo.svg?v=040'
}
function canonicalToken(symbol: string) {
  const clean = String(symbol || '').toUpperCase().trim()
  if (clean === 'USDC/CASH' || clean === 'USDCCASH' || clean === 'USDCASH' || clean === 'CASH') return 'USDC'
  return clean.replace(/[^A-Z0-9]/g, '')
}
function displayToken(symbol: string) {
  const clean = String(symbol || '').toUpperCase().trim()
  return canonicalToken(clean) === 'USDC' ? 'USDC' : clean
}
function iconSources(symbol: string, apiUrl?: string) {
  const clean = canonicalToken(symbol)
  const lower = clean.toLowerCase()
  if (clean === 'USDC') return [USDC_LOGO_DATA_URI]
  const preferred = [apiUrl, staticLogoUrls[clean]]
  return [...preferred, `https://assets.coincap.io/assets/icons/${lower}@2x.png`, `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/svg/color/${lower}.svg`, `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/${lower}.png`, `https://s3-symbol-logo.tradingview.com/crypto/XTVC${clean}.svg`].filter(Boolean) as string[]
}
function TokenLogo({ coin, icons }: { coin: string, icons: Record<string, string> }) {
  const symbol = String(coin || '').toUpperCase()
  const canonical = canonicalToken(symbol)
  const [sourceIndex, setSourceIndex] = useState(0)
  const color = fallbackColours[symbol] || fallbackColours[canonical] || '#35f1cf'
  const sources = iconSources(canonical, icons[symbol] || icons[canonical])
  useEffect(() => setSourceIndex(0), [symbol, canonical, icons[symbol], icons[canonical]])
  const src = sources[sourceIndex]
  const label = displayToken(symbol)
  return <span className={`cc-token-logo ${canonical === 'USDC' ? 'is-usdc' : ''}`} style={{ ['--coin' as any]: color }}>
    {src ? <img src={src} alt={`${label} logo`} onError={() => setSourceIndex(i => i + 1)} /> : <span className="cc-token-fallback"><i /><b>{label.slice(0, 2)}</b></span>}
  </span>
}

function tokenColour(symbol: string, index: number) {
  const raw = String(symbol || '').toUpperCase()
  return fallbackColours[raw] || fallbackColours[canonicalToken(raw)] || palette[index % palette.length]
}

type Segment = { coin: string; weight: number; color: string; originalWeight: number }

function AllocationDonut({ targets, signals, trackedValue, icons }: { targets: any[]; signals: any[]; trackedValue: number; icons: Record<string, string> }) {
  const [hovered, setHovered] = useState<Segment | null>(null)
  const parts: Segment[] = useMemo(() => {
    // Prefer a broad live allocation index from the current signal board rather
    // than the smaller model target list. This shows what the selected wallet
    // cohort is actually long/holding at a glance. Cash is inferred from
    // tracked account value when long exposure is below account value.
    const longRows = [...(signals || [])]
      .map((r: any) => ({ coin: r.coin, value: Math.max(0, Number(r.value_long_usd || 0)) }))
      .filter((r: any) => r.value > 0 && canonicalToken(r.coin) !== 'USDC')
      .sort((a: any, b: any) => b.value - a.value)
    const totalLong = longRows.reduce((a: number, r: any) => a + r.value, 0)
    const accountValue = Math.max(0, Number(trackedValue || 0))
    const cashValue = Math.max(0, accountValue - totalLong)
    const rows = [
      ...(cashValue > 0 ? [{ coin: 'USDC', value: cashValue }] : []),
      ...longRows,
    ]
    let top = rows.slice(0, 10)
    const shown = top.reduce((a: number, r: any) => a + r.value, 0)
    const remaining = rows.slice(10).reduce((a: number, r: any) => a + r.value, 0)
    if (remaining > 0) top = [...top, { coin: 'OTHER', value: remaining }]
    if (!top.length && (targets || []).length) {
      top = (targets || []).filter(t => Number(t.target_weight) > 0).slice(0, 10).map((t: any) => ({ coin: t.coin, value: Number(t.target_weight || 0) }))
    }
    const total = top.reduce((a: number, r: any) => a + r.value, 0) || 1
    return top.map((t: any, i: number) => ({ coin: t.coin, originalWeight: Number(t.value || 0) / total, weight: Number(t.value || 0) / total, color: tokenColour(t.coin, i) }))
  }, [targets, signals, trackedValue])
  let angle = -90
  const path = (cx: number, cy: number, r1: number, r2: number, a0: number, a1: number) => {
    const p = (r: number, a: number) => { const rad = a * Math.PI / 180; return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) } }
    const s1 = p(r1, a0), e1 = p(r1, a1), s2 = p(r2, a1), e2 = p(r2, a0); const large = a1 - a0 > 180 ? 1 : 0
    return `M ${s1.x} ${s1.y} A ${r1} ${r1} 0 ${large} 1 ${e1.x} ${e1.y} L ${s2.x} ${s2.y} A ${r2} ${r2} 0 ${large} 0 ${e2.x} ${e2.y} Z`
  }
  if (!parts.length) return <div className="cc-empty-state">Targets will appear after refresh.</div>
  return <div className="cc-donut-layout">
    <div className="cc-donut-stage">
      <svg viewBox="0 0 220 220" className="cc-donut-svg" aria-label="Portfolio allocation index">
        {parts.map(p => { const start = angle; angle += p.weight * 360; return <path key={p.coin} d={path(110, 110, 92, 50, start, angle - 1)} fill={p.color} onMouseEnter={() => setHovered(p)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(p)} onBlur={() => setHovered(null)} tabIndex={0}><title>{displayToken(p.coin)}: {Math.round(p.originalWeight * 100)}%</title></path> })}
        <circle className="cc-donut-hole" cx="110" cy="110" r="50" />
      </svg>
      <div className="cc-donut-tooltip">{hovered ? `${displayToken(hovered.coin)} ${Math.round(hovered.originalWeight * 100)}% allocation` : 'Hover a segment for details'}</div>
    </div>
    <div className="cc-donut-legend cc-scroll-y">{parts.map(p => <div key={p.coin}><TokenLogo coin={p.coin} icons={icons} /><b>{displayToken(p.coin)}</b><span>{Math.round(p.originalWeight * 100)}%</span></div>)}</div>
    <p className="cc-allocation-description">Value-weighted index of what the current top 50 wallet cohort is long or holding.</p>
  </div>
}
function ExposureBars({ signals, icons }: { signals: any[], icons: Record<string, string> }) {
  const rows = useMemo(() => ([...(signals || [])]
    .filter(r => Number(r.value_long_usd || 0) + Number(r.value_short_usd || 0) > 0)
    .sort((a, b) => (Number(b.value_long_usd || 0) + Number(b.value_short_usd || 0)) - (Number(a.value_long_usd || 0) + Number(a.value_short_usd || 0)))
  ), [signals])
  if (!rows.length) return <div className="cc-empty-state">Exposure appears after refresh.</div>
  return <div className="cc-exposure-list cc-scroll-y">{rows.map(r => {
    const l = Number(r.value_long_usd || 0), sh = Number(r.value_short_usd || 0)
    const total = l + sh
    const longPct = total > 0 ? (l / total) * 100 : 0
    const shortPct = Math.max(0, 100 - longPct)
    return <div className="cc-ex-row" key={r.coin}>
      <div className="cc-ex-name"><TokenLogo coin={r.coin} icons={icons} /><b title={displayToken(r.coin)}>{displayToken(r.coin)}</b><span>{longSharePct(l, sh)}</span></div>
      <div className="cc-ex-track" aria-label={`${displayToken(r.coin)} ${Math.round(longPct)}% long, ${Math.round(shortPct)}% short`}><div><i style={{ width: `${longPct}%` }} /><em style={{ width: `${shortPct}%` }} /></div></div>
      <small>{compactMoney(l)}</small><small>{compactMoney(sh)}</small>
    </div>
  })}</div>
}

function formatInsightDetail(x: any) {
  if (x?.type === 'top_signal') {
    const confidence = x?.row?.confidence || x?.detail?.split('·')?.[1]?.trim() || ''
    return `Signal ${displaySignalPct(x?.row)}${confidence ? ` · ${confidence}` : ''}`
  }
  return String(x?.detail || '').replace(/Signal\s+(-?\d+(?:\.\d+)?)/i, (_, raw) => `Signal ${signalPct(Number(raw))}`)
}

type SortDir = 'asc' | 'desc'
type SortState = { key: string, dir: SortDir }

function nextSort(current: SortState, key: string): SortState {
  if (current.key !== key) return { key, dir: 'desc' }
  return { key, dir: current.dir === 'desc' ? 'asc' : 'desc' }
}
function sortArrow(current: SortState, key: string) {
  if (current.key !== key) return '↕'
  return current.dir === 'desc' ? '↓' : '↑'
}
function sorterValue(row: any, key: string) {
  if (key === 'wallets') return Number(row.wallets_long || 0) + Number(row.wallets_short || 0)
  if (key === 'value_ls') return Number(row.value_long_usd || 0) + Number(row.value_short_usd || 0)
  if (key === 'pct_total') return Number(row.value_long_pct_total || 0) + Number(row.value_short_pct_total || 0)
  if (key === 'asset') return String(row.coin || '').toUpperCase()
  if (key === 'signal') return displaySignalValue(row)
  if (key === 'confidence') {
    const rank: Record<string, number> = { high: 3, medium: 2, med: 2, low: 1, reserve: 0 }
    return rank[String(row.confidence || '').toLowerCase()] ?? -1
  }
  if (key === 'read') {
    const rank: Record<string, number> = { Accumulation: 2, Neutral: 1, Distribution: 0 }
    return rank[flowRead(row.net_value_flow_usd)] ?? 0
  }
  if (key === 'bullish') return Number(row.bullish_flow_usd || 0)
  if (key === 'bearish') return Number(row.bearish_flow_usd || 0)
  if (key === 'net_buyers') return Number(row.net_buyer_count || 0)
  const v = row[key]
  const n = Number(v)
  return Number.isFinite(n) && String(v ?? '').trim() !== '' ? n : String(v ?? '').toUpperCase()
}
function sortedRows(rows: any[], sort: SortState) {
  const dir = sort.dir === 'desc' ? -1 : 1
  return [...(rows || [])].sort((a, b) => {
    const av = sorterValue(a, sort.key), bv = sorterValue(b, sort.key)
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
    return String(av).localeCompare(String(bv)) * dir
  })
}
function SortTh({ label, sortKey, sort, setSort }: { label: string, sortKey: string, sort: SortState, setSort: (s: SortState) => void }) {
  return <th><button className="cc-sort-head" onClick={() => setSort(nextSort(sort, sortKey))}>{label}<span>{sortArrow(sort, sortKey)}</span></button></th>
}

export default function Dashboard() {
  const [summary, setSummary] = useState<any>({})
  const [signals, setSignals] = useState<any[]>([])
  const [targets, setTargets] = useState<any[]>([])
  const [flow, setFlow] = useState<any[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const [insights, setInsights] = useState<any[]>([])
  const [showAllOrders, setShowAllOrders] = useState(false)
  const [icons, setIcons] = useState<Record<string, string>>({})
  const [err, setErr] = useState('')
  const [signalSort, setSignalSort] = useState<SortState>({ key: 'signal', dir: 'desc' })
  const [flowSortState, setFlowSortState] = useState<SortState>({ key: 'net_value_flow_usd', dir: 'desc' })

  const inFlight = useRef(false)
  const failureCount = useRef(0)
  const hasLoaded = useRef(false)

  async function load() {
    // One browser tab should never stack multiple refreshes. When a mobile tab
    // and desktop tab are open together, this prevents request pile-ups that
    // can make Render/Supabase briefly refuse connections and show "Failed to fetch".
    if (inFlight.current) return
    inFlight.current = true
    try {
      const feed = await apiGet('/api/dashboard-feed')
      failureCount.current = 0
      hasLoaded.current = true
      setErr('')
      setSummary(feed.summary || {})
      setSignals(feed.signals || [])
      setTargets(feed.targets || [])
      setFlow(feed.flow || [])
      setOrders(feed.orders || [])
      setInsights(feed.insights || [])
    } catch (e: any) {
      failureCount.current += 1
      // Keep the last good dashboard on screen during transient network blips.
      // Only show an error if the page has never loaded successfully.
      if (!hasLoaded.current && failureCount.current >= 3) {
        setErr('Live data connection interrupted. Retrying…')
      }
    } finally {
      inFlight.current = false
    }
  }

  useEffect(() => { window.history.scrollRestoration = 'manual'; window.scrollTo(0, 0); load(); const id = setInterval(load, 1000); return () => clearInterval(id) }, [])

  const symbolKey = useMemo(() => Array.from(new Set([...signals.map(r => r.coin), ...targets.map(r => r.coin), ...flow.map(r => r.coin), ...orders.map((r: any) => r.coin)].filter(Boolean).map(x => canonicalToken(String(x).toUpperCase())))).sort().join(','), [signals, targets, flow, orders])
  useEffect(() => {
    if (!symbolKey) return
    const cacheKey = 'copycat-token-icons:' + symbolKey
    try {
      const cached = localStorage.getItem(cacheKey)
      if (cached) setIcons(JSON.parse(cached))
    } catch {}
    apiGet('/api/token-icons?symbols=' + encodeURIComponent(symbolKey)).then((r: any) => {
      const nextIcons = r.icons || {}
      setIcons(nextIcons)
      try { localStorage.setItem(cacheKey, JSON.stringify(nextIcons)) } catch {}
    }).catch(() => {})
  }, [symbolKey])

  const longValue = signals.reduce((a, r) => a + Number(r.value_long_usd || 0), 0)
  const shortValue = signals.reduce((a, r) => a + Number(r.value_short_usd || 0), 0)
  const isLong = longValue >= shortValue
  const dataHealthy = summary.data_quality_status === 'healthy'
  const orderRows = orders.length ? orders : flow.slice(0, 12).map((r: any) => ({ coin: r.coin, side: Number(r.net_value_flow_usd) >= 0 ? 'Long' : 'Short', wallet_label: 'Wallet 0x1A…7F3B', wallet: r.wallet, ts_ms: summary.latest_signal_ts_ms }))
  const visibleOrders = showAllOrders ? orderRows : orderRows.slice(0, 3)
  const sortedSignals = sortedRows(signals, signalSort)
  const sortedFlow = sortedRows(flow, flowSortState)

  return <><Nav /><main className="cc-dashboard-shell"><LineBackdrop variant="dashboard" />
    <section className="cc-dashboard-top">
      <div className="cc-dashboard-copy">
        <p className="eyebrow live">Live smart-wallet tape</p>
        <h1>Market intelligence.<br /><em>Follow the best.</em></h1>
        <p>Value-weighted positioning from qualified Hyperliquid wallets.<br />Built to show what serious traders are leaning into.</p>
      </div>
      <div className="cc-bias-block"><span>Positioning bias</span><button className={`cc-bias-toggle ${isLong ? 'is-long' : 'is-short'}`}><i aria-hidden /><b>{isLong ? 'LONG' : 'SHORT'}</b></button></div>
      <aside className="cc-top-rail">
        <div className={`cc-orders-card ${showAllOrders ? 'expanded' : ''}`}>
          <h3>Most recent orders</h3>
          <div className="cc-order-list">
            {visibleOrders.map((o: any, i: number) => <div className="cc-order-line" key={`${o.coin}-${i}-${o.wallet || ''}-${o.ts_ms || ''}`}><TokenLogo coin={o.coin} icons={icons} /><b>{displayToken(o.coin)}</b><span className={orderActionClass(o.side)}>{o.side}</span><em>{o.wallet_label || maskWallet(o.wallet)}</em><small>{ago(o.ts_ms)}</small></div>)}
          </div>
          <button className="cc-small-action" onClick={() => setShowAllOrders(v => !v)}>{showAllOrders ? 'Show latest 3 ↑' : 'View all orders →'}</button>
        </div>
        <div className="cc-insights-card">
          <h3>At a glance</h3>
          {(insights || []).slice(0, 5).map((x: any) => <div className="cc-insight-line" key={`${x.type}-${x.coin}`}>
            <span>{x.label}</span><b>{x.coin || '—'}</b><em>{formatInsightDetail(x)}</em>
          </div>)}
        </div>
      </aside>
    </section>

    {err && <p className="notice gold">{err}</p>}

    <section className="cc-kpi-grid">
      <article><small>Qualified wallets</small><b>{summary.qualified_wallets || 0}</b><span>ranked daily</span></article>
      <article className="cc-tracked-value-card"><small>Tracked account value</small><b>{money(summary.tracked_account_value_usd)}</b><span>latest snapshots</span>{summary.largest_account_value_usd ? <em>Largest account: {money(summary.largest_account_value_usd)}</em> : null}</article>
      <article><small>Open position value</small><b>{money(summary.tracked_open_position_value_usd)}</b><span>{summary.open_positions || 0} live positions</span></article>
      <article><small>Assets with signals</small><b>{summary.assets_with_signals || 0}</b><span>cross-asset breadth</span></article>
    </section>

    <section className="cc-chart-grid">
      <div className="cc-card cc-allocation-card"><h3>Portfolio allocation</h3><AllocationDonut targets={targets} signals={signals} trackedValue={Number(summary.tracked_account_value_usd || 0)} icons={icons} /></div>
      <div className="cc-card cc-exposure-card"><div className="cc-panel-title"><h3>Long vs short exposure</h3><span><i />Long <em />Short</span></div><ExposureBars signals={signals} icons={icons} /></div>
    </section>

    <section className="cc-table-grid">
      <div className="cc-card cc-table-card">
        <div className="cc-panel-title"><h3>Asset signal board</h3><span>value-weighted, not wallet-count only</span></div>
        <div className="cc-scroll-table cc-scroll-y">
          <table className="cc-signal-table">
            <thead><tr><th>#</th><SortTh label="Asset" sortKey="asset" sort={signalSort} setSort={setSignalSort} /><SortTh label="Signal" sortKey="signal" sort={signalSort} setSort={setSignalSort} /><SortTh label="Confidence" sortKey="confidence" sort={signalSort} setSort={setSignalSort} /><SortTh label="Wallets" sortKey="wallets" sort={signalSort} setSort={setSignalSort} /><SortTh label="Value L/S" sortKey="value_ls" sort={signalSort} setSort={setSignalSort} /><SortTh label="Net value" sortKey="net_value_usd" sort={signalSort} setSort={setSignalSort} /><SortTh label="% total value" sortKey="pct_total" sort={signalSort} setSort={setSignalSort} /></tr></thead>
            <tbody>{sortedSignals.map((r, i) => <tr key={`${r.coin}-${i}`}><td>{i + 1}</td><td><span className="cc-asset-cell"><TokenLogo coin={r.coin} icons={icons} /><b>{displayToken(r.coin)}</b></span></td><td className={cls(displaySignalValue(r))}>{displaySignalPct(r)}</td><td><span className={`cc-confidence ${String(r.confidence).toLowerCase()}`}>{r.confidence}</span></td><td>{r.wallets_long} long / {r.wallets_short} short</td><td>{money(r.value_long_usd)} / {money(r.value_short_usd)}</td><td className={cls(r.net_value_usd)}>{money(r.net_value_usd)}</td><td>{pct(r.value_long_pct_total)} long / {pct(r.value_short_pct_total)} short</td></tr>)}</tbody>
          </table>
        </div>
      </div>
      <div className="cc-card cc-table-card">
        <div className="cc-panel-title"><h3>Recent buyer / seller pressure</h3><span>largest flow changes first</span></div>
        <div className="cc-scroll-table cc-scroll-y">
          <table className="cc-flow-table">
            <thead><tr><SortTh label="Asset" sortKey="asset" sort={flowSortState} setSort={setFlowSortState} /><SortTh label="Net buyers" sortKey="net_buyers" sort={flowSortState} setSort={setFlowSortState} /><SortTh label="Bullish flow" sortKey="bullish" sort={flowSortState} setSort={setFlowSortState} /><SortTh label="Bearish flow" sortKey="bearish" sort={flowSortState} setSort={setFlowSortState} /><SortTh label="Net value flow" sortKey="net_value_flow_usd" sort={flowSortState} setSort={setFlowSortState} /><SortTh label="Read" sortKey="read" sort={flowSortState} setSort={setFlowSortState} /></tr></thead>
            <tbody>{sortedFlow.map((r, i) => { const read = flowRead(r.net_value_flow_usd); return <tr key={`${r.coin}-${i}`}><td><span className="cc-asset-cell"><TokenLogo coin={r.coin} icons={icons} /><b>{displayToken(r.coin)}</b></span></td><td className={cls(r.net_buyer_count)}>{r.net_buyer_count}</td><td>{money(r.bullish_flow_usd)}</td><td>{money(r.bearish_flow_usd)}</td><td className={cls(r.net_value_flow_usd)}>{money(r.net_value_flow_usd)}</td><td><span className={`cc-read ${read.toLowerCase()}`}>{read}</span></td></tr> })}</tbody>
          </table>
        </div>
      </div>
    </section>

    <footer className="cc-warning-banner"><span className="cc-shield" aria-hidden><svg viewBox="0 0 24 24"><path d="M12 3l7 3v5.2c0 4.5-2.7 8.4-7 9.8-4.3-1.4-7-5.3-7-9.8V6l7-3z"/><path d="M9.2 12.1l1.7 1.7 3.9-4.1"/></svg></span><strong>Market intelligence only.</strong><em>Not financial advice. Crypto trading can result in loss.</em><div className={`cc-footer-meta ${dataHealthy ? 'healthy' : 'checking'}`}><span className="cc-footer-quality"><span className="cc-pulse-dot" /><b>{dataHealthy ? 'Data quality healthy' : 'Data quality checking'}</b></span><small>Signal refresh: {fmtTime(summary.latest_signal_ts_ms)} UTC · Page checks every 1s</small></div></footer>
  </main></>
}
