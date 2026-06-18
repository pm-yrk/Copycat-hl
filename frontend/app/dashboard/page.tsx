'use client'

import { useEffect, useMemo, useState } from 'react'
import Nav from '../../components/Nav'
import { apiGet } from '../../lib/api'

function money(n: any) {
  return '$' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })
}
function compactMoney(n: any) {
  const v = Math.abs(Number(n || 0))
  const sign = Number(n || 0) < 0 ? '-' : ''
  if (v >= 1_000_000_000) return sign + '$' + (v / 1_000_000_000).toFixed(1) + 'b'
  if (v >= 1_000_000) return sign + '$' + (v / 1_000_000).toFixed(1) + 'm'
  if (v >= 1_000) return sign + '$' + (v / 1_000).toFixed(1) + 'k'
  return sign + '$' + v.toFixed(0)
}
function pct(n: any) {
  return (Number(n || 0) * 100).toFixed(1) + '%'
}
function cls(n: any) {
  return Number(n) >= 0 ? 'positive' : 'negative'
}
function readFlow(n: any) {
  return Number(n) > 3 ? 'Accumulation' : Number(n) < -3 ? 'Distribution' : 'Neutral'
}
function fmtTime(ms: any) {
  if (!ms) return 'Awaiting refresh'
  const d = new Date(Number(ms))
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
function ago(ms: any) {
  if (!ms) return 'latest'
  const diff = Math.max(0, Date.now() - Number(ms))
  const mins = Math.round(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  return `${hrs}h ago`
}
function maskWallet(w: string) {
  return w ? `Wallet ${w.slice(0, 4)}…${w.slice(-4)}` : 'Wallet'
}

const palette = ['#45E2D0', '#7C5CFF', '#40B8F6', '#FDB022', '#31D17C', '#F472B6', '#B3E635', '#FB7185']
const coinColors: Record<string, string> = {
  HYPE: '#52E7D6', ETH: '#627EEA', BTC: '#F7931A', SOL: '#14F195', ZEC: '#F4B728',
  NEAR: '#00EC97', MELANIA: '#D7A785', AAVE: '#8B7DFF', TRX: '#FF4B4B', XRP: '#4B9FFF',
  WLD: '#8B95A7', USDC: '#2775CA', CASH: '#8B95A7', 'USDC/CASH': '#2775CA', ARB: '#2D374B',
}

const logoMap: Record<string, string> = {
  BTC: 'https://cryptologos.cc/logos/bitcoin-btc-logo.svg?v=040',
  ETH: 'https://cryptologos.cc/logos/ethereum-eth-logo.svg?v=040',
  SOL: 'https://cryptologos.cc/logos/solana-sol-logo.svg?v=040',
  XRP: 'https://cryptologos.cc/logos/xrp-xrp-logo.svg?v=040',
  AAVE: 'https://cryptologos.cc/logos/aave-aave-logo.svg?v=040',
  NEAR: 'https://cryptologos.cc/logos/near-protocol-near-logo.svg?v=040',
  ZEC: 'https://cryptologos.cc/logos/zcash-zec-logo.svg?v=040',
  TRX: 'https://cryptologos.cc/logos/tron-trx-logo.svg?v=040',
  USDC: 'https://cryptologos.cc/logos/usd-coin-usdc-logo.svg?v=040',
  ARB: 'https://cryptologos.cc/logos/arbitrum-arb-logo.svg?v=040',
}

function TokenLogo({ coin }: { coin: string }) {
  const symbol = String(coin || '').toUpperCase()
  const [broken, setBroken] = useState(false)
  const url = logoMap[symbol]
  const bg = coinColors[symbol] || '#35f1cf'

  if (url && !broken) {
    return (
      <span className="token-logo token-logo-image" style={{ ['--coin' as any]: bg }}>
        <img src={url} alt={`${symbol} logo`} onError={() => setBroken(true)} />
      </span>
    )
  }

  return (
    <span className="token-logo" style={{ ['--coin' as any]: bg }}>
      {symbol.slice(0, 2)}
    </span>
  )
}

function Spark() {
  return (
    <svg viewBox="0 0 92 32" className="mini-spark" aria-hidden="true">
      <path d="M2 25 L15 22 L27 24 L39 14 L51 20 L62 9 L74 12 L90 7" />
    </svg>
  )
}

function WaveLines({ className = '' }: { className?: string }) {
  return (
    <div className={`wave-lines ${className}`} aria-hidden="true">
      <svg viewBox="0 0 1000 320" preserveAspectRatio="none">
        {Array.from({ length: 18 }).map((_, i) => {
          const start = 12 + i * 18
          const end = 860 - i * 12
          const c1 = 300 + i * 8
          const c2 = 720 - i * 6
          return (
            <path
              key={i}
              d={`M ${start} 300 C ${c1} ${110 - i * 3}, ${c2} ${20 + i * 4}, ${end} 26`}
            />
          )
        })}
      </svg>
    </div>
  )
}

type Segment = { coin: string; weight: number; color: string }
function polar(cx: number, cy: number, r: number, angle: number) {
  const a = ((angle - 90) * Math.PI) / 180
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
}
function donutPath(cx: number, cy: number, outer: number, inner: number, start: number, end: number) {
  const s1 = polar(cx, cy, outer, start), e1 = polar(cx, cy, outer, end), s2 = polar(cx, cy, inner, start), e2 = polar(cx, cy, inner, end)
  const large = end - start > 180 ? 1 : 0
  return `M ${s1.x} ${s1.y} A ${outer} ${outer} 0 ${large} 1 ${e1.x} ${e1.y} L ${e2.x} ${e2.y} A ${inner} ${inner} 0 ${large} 0 ${s2.x} ${s2.y} Z`
}
function AllocationDonut({ targets }: { targets: any[] }) {
  const parts: Segment[] = useMemo(() => {
    const clean = (targets || []).filter((t) => Number(t.target_weight) > 0).slice(0, 6)
    const total = clean.reduce((a, t) => a + Number(t.target_weight || 0), 0) || 1
    return clean.map((t, i) => ({ coin: t.coin, weight: Number(t.target_weight || 0) / total, color: palette[i % palette.length] }))
  }, [targets])

  let angle = 0
  if (!parts.length) return <div className="empty-chart">Targets will appear after the collector runs.</div>
  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 220 220" className="donut" role="img" aria-label="Portfolio target allocation donut">
        {parts.map((p) => {
          const start = angle
          angle += p.weight * 360
          return <path key={p.coin} d={donutPath(110, 110, 92, 58, start, angle - 0.8)} fill={p.color} className="donut-seg"><title>{p.coin} {(p.weight * 100).toFixed(1)}%</title></path>
        })}
        <circle cx="110" cy="110" r="52" className="donut-hole" />
        <text x="110" y="105" textAnchor="middle" className="donut-kicker">TARGETS</text>
        <text x="110" y="130" textAnchor="middle" className="donut-number">{parts.length}</text>
      </svg>
      <div className="legend">
        {parts.map((p) => (
          <div className="legend-row" key={p.coin}>
            <span style={{ background: p.color }} />
            <b>{p.coin}</b>
            <em>{(p.weight * 100).toFixed(1)}%</em>
          </div>
        ))}
      </div>
    </div>
  )
}
function ExposureBars({ signals }: { signals: any[] }) {
  const rows = (signals || []).slice(0, 8)
  const max = Math.max(1, ...rows.map((r) => Number(r.value_long_usd || 0) + Number(r.value_short_usd || 0)))
  if (!rows.length) return <div className="empty-chart">Exposure bars will appear after the collector runs.</div>
  return (
    <div className="bars-list">
      {rows.map((r) => {
        const l = Number(r.value_long_usd || 0), s = Number(r.value_short_usd || 0)
        const total = l + s || 1
        const longShare = Math.max(2, (l / total) * 100)
        const shortShare = Math.max(2, (s / total) * 100)
        return (
          <div className="bar-row" key={r.coin}>
            <div className="bar-label"><b>{r.coin}</b><span>{Number(r.signal).toFixed(2)}</span></div>
            <div className="bar-track" title={`${r.coin}: long ${money(l)} / short ${money(s)}`}>
              <div className="bar-combo" style={{ width: `${Math.max(8, ((l + s) / max) * 100)}%` }}>
                <i className="bar-long" style={{ width: `${longShare}%` }} />
                <i className="bar-short" style={{ width: `${shortShare}%` }} />
              </div>
            </div>
            <div className="bar-values"><span>{compactMoney(l)}</span><span>{compactMoney(s)}</span></div>
          </div>
        )
      })}
    </div>
  )
}

const marketRows = [
  { label: 'Total market cap', value: '$2.61T', change: '-0.76%' },
  { label: '24h volume', value: '$98.47B', change: '+3.21%' },
  { label: 'BTC dominance', value: '52.1%', change: '+0.35%' },
  { label: 'ETH dominance', value: '17.3%', change: '-0.12%' },
]

export default function Dashboard() {
  const [summary, setSummary] = useState<any>({})
  const [signals, setSignals] = useState<any[]>([])
  const [targets, setTargets] = useState<any[]>([])
  const [flow, setFlow] = useState<any[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const [err, setErr] = useState('')

  async function load() {
    try {
      setErr('')
      const [s, si, t, f, o] = await Promise.all([
        apiGet('/api/summary'),
        apiGet('/api/signals?limit=30'),
        apiGet('/api/targets'),
        apiGet('/api/flow?limit=30'),
        apiGet('/api/recent-orders?limit=3').catch(() => []),
      ])
      setSummary(s)
      setSignals(si)
      setTargets(t)
      setFlow(f)
      setOrders(o)
    } catch (e: any) {
      setErr(e.message)
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [])

  const longValue = signals.reduce((a, r) => a + Number(r.value_long_usd || 0), 0)
  const shortValue = signals.reduce((a, r) => a + Number(r.value_short_usd || 0), 0)
  const isLong = longValue >= shortValue
  const orderRows = orders.length
    ? orders
    : flow.slice(0, 3).map((r) => ({
        coin: r.coin,
        side: Number(r.net_value_flow_usd) >= 0 ? 'Long' : 'Short',
        wallet_label: 'Top wallet',
        ts_ms: summary.latest_signal_ts_ms,
        delta_value_usd: r.net_value_flow_usd,
      }))

  return (
    <>
      <Nav />
      <main className="page-shell dashboard-page">
        <WaveLines className="wave-top" />
        <WaveLines className="wave-bottom" />

        <section className="dashboard-layout">
          <div className="lead-panel">
            <p className="eyebrow live-dot">Live smart-wallet tape</p>
            <div className="hero-bias-row">
              <h1>Market intelligence.<br /><em>Follow the best.</em></h1>
              <div className="bias-wrap bias-wrap-inline">
                <span>Positioning bias</span>
                <button className={`bias-toggle ${isLong ? 'is-long' : 'is-short'}`}>
                  <i />
                  <b>{isLong ? 'LONG' : 'SHORT'}</b>
                </button>
              </div>
            </div>
            <p>Value-weighted positioning from qualified Hyperliquid wallets. Built to show what serious traders are leaning into.</p>
          </div>

          <div className="side-stack">
            <aside className="orders-card">
              <h3>Most recent orders</h3>
              {orderRows.map((o: any, i: number) => (
                <div className="order-row" key={`${o.coin}-${i}`}>
                  <TokenLogo coin={o.coin} />
                  <b>{o.coin}</b>
                  <span className={String(o.side).toLowerCase().includes('short') || String(o.side).toLowerCase().includes('reduce') ? 'negative' : 'positive'}>{o.side}</span>
                  <em className="wallet-label">{o.wallet_label || maskWallet(o.wallet)}</em>
                  <small>{ago(o.ts_ms)}</small>
                </div>
              ))}
              <button className="ghost-action small">View all orders →</button>
            </aside>

            <aside className="market-card">
              <h3>Market overview</h3>
              {marketRows.map((m) => (
                <div className="market-row" key={m.label}>
                  <div>
                    <small>{m.label}</small>
                    <b>{m.value}</b>
                  </div>
                  <span className={m.change.startsWith('-') ? 'negative' : 'positive'}>{m.change}</span>
                </div>
              ))}
              <div className="market-foot">
                <span>Source: CoinGecko</span>
                <a>View more →</a>
              </div>
            </aside>
          </div>
        </section>

        {err && <p className="notice gold">{err}</p>}

        <section className="metric-grid dashboard-metrics dashboard-metrics-polished">
          <div className="metric-card"><i className="ico users" /><small>Qualified wallets</small><b>{summary.qualified_wallets || 0}</b><span>ranked daily</span><Spark /></div>
          <div className="metric-card"><i className="ico wallet" /><small>Tracked account value</small><b className="tight-number">{money(summary.tracked_account_value_usd)}</b><span>latest snapshots</span><Spark /></div>
          <div className="metric-card"><i className="ico chart" /><small>Open position value</small><b className="tight-number">{money(summary.tracked_open_position_value_usd)}</b><span>{summary.open_positions || 0} live positions</span><Spark /></div>
          <div className="metric-card"><i className="ico bolt" /><small>Assets with signals</small><b>{summary.assets_with_signals || 0}</b><span>cross-asset breadth</span><Spark /></div>
          <div className="metric-card refresh"><i className="ico clock" /><small>Signal refresh</small><b className="tight-number">{fmtTime(summary.latest_signal_ts_ms)}</b><span>UTC</span></div>
        </section>

        <section className="dash-charts">
          <div className="chart-card">
            <div className="section-head"><div><p className="eyebrow">Portfolio allocation</p></div></div>
            <AllocationDonut targets={targets} />
          </div>
          <div className="chart-card">
            <div className="section-head"><div><p className="eyebrow">Long vs short exposure</p></div><div className="bar-key"><span className="key-long">Long</span><span className="key-short">Short</span></div></div>
            <ExposureBars signals={signals} />
          </div>
        </section>

        <section className="dash-tables">
          <div className="table-card">
            <div className="section-head"><div><p className="eyebrow">Asset signal board</p></div><span className="hint">value-weighted, not wallet-count only</span></div>
            <div className="table-scroll">
              <table>
                <thead><tr><th>#</th><th>Asset</th><th>Signal</th><th>Confidence</th><th>Wallets</th><th>Value L/S</th><th>Net value</th><th>% total value</th></tr></thead>
                <tbody>
                  {signals.slice(0, 8).map((r, i) => (
                    <tr key={r.coin}>
                      <td>{i + 1}</td>
                      <td><span className="asset-cell"><TokenLogo coin={r.coin} /><b>{r.coin}</b></span></td>
                      <td className={cls(r.signal)}>{Number(r.signal).toFixed(2)}</td>
                      <td><span className={`pill ${r.confidence === 'High' ? 'conf-high' : r.confidence === 'Medium' ? 'conf-medium' : ''}`}>{r.confidence}</span></td>
                      <td>{r.wallets_long} long / {r.wallets_short} short</td>
                      <td>{money(r.value_long_usd)} / {money(r.value_short_usd)}</td>
                      <td className={cls(r.net_value_usd)}>{money(r.net_value_usd)}</td>
                      <td>{pct(r.value_long_pct_total)} long / {pct(r.value_short_pct_total)} short</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <a className="table-link">View full signal board →</a>
          </div>

          <div className="table-card">
            <div className="section-head"><div><p className="eyebrow">Recent buyer / seller pressure</p></div><span className="hint">largest flow changes first</span></div>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Asset</th><th>Net buyers</th><th>Bullish flow</th><th>Bearish flow</th><th>Net value flow</th><th>Read</th></tr></thead>
                <tbody>
                  {flow.slice(0, 6).map((r) => {
                    const read = readFlow(r.net_buyer_count)
                    return (
                      <tr key={r.coin}>
                        <td><span className="asset-cell"><TokenLogo coin={r.coin} /><b>{r.coin}</b></span></td>
                        <td className={cls(r.net_buyer_count)}>{r.net_buyer_count}</td>
                        <td>{money(r.bullish_flow_usd)}</td>
                        <td>{money(r.bearish_flow_usd)}</td>
                        <td className={cls(r.net_value_flow_usd)}>{money(r.net_value_flow_usd)}</td>
                        <td><span className={`pill read-${read.toLowerCase()}`}>{read}</span></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <a className="table-link">View full pressure tape →</a>
          </div>
        </section>

        <p className="notice dashboard-notice dashboard-footer-note"><span>♢</span> <strong>Market intelligence only.</strong> <em>Not financial advice. Crypto trading can result in loss.</em> <span className="refresh-note">● Data updates every 30s</span></p>
      </main>
    </>
  )
}
