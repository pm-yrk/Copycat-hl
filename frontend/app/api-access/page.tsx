"use client"

import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import { apiGet } from '../../lib/api'

type Status = Record<string, any>

function compact(n: any) {
  const value = Number(n || 0)
  if (!Number.isFinite(value)) return '0'
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 })
}
function money(n: any) {
  const value = Number(n || 0)
  if (!Number.isFinite(value)) return '$0'
  if (Math.abs(value) >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}b`
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}m`
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}k`
  return `$${value.toFixed(0)}`
}
function freshness(ts: any) {
  const n = Number(ts || 0)
  if (!n) return 'Awaiting first sync'
  const mins = Math.max(0, Math.round((Date.now() - n) / 60000))
  if (mins < 1) return 'Updated just now'
  if (mins < 60) return `Updated ${mins}m ago`
  return `Updated ${Math.round(mins / 60)}h ago`
}
function walletAddress(r: any) {
  return String(r?.wallet || r?.address || r?.user || r?.account || r?.owner || r?.wallet_address || '').trim()
}
function rowWallet(r: any) {
  const wallet = walletAddress(r)
  if (/^0x[a-fA-F0-9]{40}$/.test(wallet)) return `${wallet.slice(0, 8)}...${wallet.slice(-6)}`
  return 'Wallet'
}
function WalletLink({ row }: { row: any }) {
  const wallet = walletAddress(row)
  const label = rowWallet(row)
  if (!/^0x[a-fA-F0-9]{40}$/.test(wallet)) return <span>{label}</span>
  return <a className="cc-api-wallet-link" href={`https://hypurrscan.io/address/${wallet}`} target="_blank" rel="noreferrer noopener" title={`Open ${wallet} on Hypurrscan`}>{label}</a>
}
function walletTotalValue(r: any) {
  const raw = r?.total_wallet_value_usd
  if (raw === null || raw === undefined || raw === '') return 'Unavailable'
  const rendered = money(raw)
  const status = String(r?.total_value_status || '').toLowerCase()
  return ['partial', 'estimated', 'stale'].includes(status) ? `~${rendered}` : rendered
}
function walletTotalValueTitle(r: any) {
  const status = String(r?.total_value_status || 'unknown')
  const mode = String(r?.account_mode || 'unknown')
  const updated = r?.total_value_updated_at_ms ? freshness(r.total_value_updated_at_ms) : 'Update time unavailable'
  const unpriced = Array.isArray(r?.unpriced_spot_tokens) && r.unpriced_spot_tokens.length ? `; unpriced: ${r.unpriced_spot_tokens.join(', ')}` : ''
  return `Total wallet value; status ${status}; mode ${mode}; ${updated}${unpriced}`
}
function signed(value: any) {
  const n = Number(value || 0)
  if (!Number.isFinite(n)) return '$0'
  return `${n < 0 ? '-' : ''}${money(Math.abs(n))}`
}
function biasLabel(r: any) {
  const label = String(r?.signal_label || r?.tilt || r?.direction || '')
  if (label) return label
  const net = Number(r?.net_value_usd || r?.net_flow_usd || r?.net_value_flow_usd || 0)
  if (net > 0) return 'Long bias'
  if (net < 0) return 'Short bias'
  return 'Neutral'
}
function biasClass(x: any) {
  if (typeof x === 'number') return x < 0 ? 'negative' : 'positive'
  return String(x || '').toLowerCase().includes('short') || Number(x || 0) < 0 ? 'negative' : 'positive'
}
function snapshotBase() {
  const configured = (process.env.NEXT_PUBLIC_SNAPSHOT_BASE_URL || '').replace(/\/+$/, '')
  if (configured) return configured
  if (typeof window !== 'undefined') return `${window.location.origin}/copycat-data`
  return '/copycat-data'
}
function actionClass(side: any) {
  const s = String(side || '').toLowerCase()
  if (s.includes('short') || s.includes('close long') || s.includes('reduce long')) return 'negative'
  return 'positive'
}


type AssetDetail = {
  coin?: string
  name?: string
  current_price?: number
  max_leverage?: number
  tilt?: string
  conviction_pct?: number
  confidence?: string
  wallets_long?: number
  wallets_short?: number
  gross_exposure_usd?: number
  net_flow_usd?: number
  value_long_usd?: number
  value_short_usd?: number
}
function tokenFullName(symbol: string) {
  const clean = canonicalToken(symbol)
  const names: Record<string, string> = { BTC: 'Bitcoin', ETH: 'Ethereum', HYPE: 'Hyperliquid', SOL: 'Solana', USDC: 'USD Coin', USDT: 'Tether', BNB: 'BNB', XRP: 'XRP', DOGE: 'Dogecoin', AVAX: 'Avalanche', LINK: 'Chainlink', AAVE: 'Aave', SUI: 'Sui', NEAR: 'NEAR Protocol', ZEC: 'Zcash', TRX: 'TRON', XLM: 'Stellar', DOT: 'Polkadot', LTC: 'Litecoin', UNI: 'Uniswap', ARB: 'Arbitrum', OP: 'Optimism', PAXG: 'PAX Gold' }
  return names[clean] || clean
}
function priceText(n: any) {
  const value = Number(n || 0)
  if (!value) return '—'
  if (value >= 1000) return '$' + value.toLocaleString(undefined, { maximumFractionDigits: 0 })
  if (value >= 1) return '$' + value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return '$' + value.toLocaleString(undefined, { maximumSignificantDigits: 4 })
}
function AssetName({ coin, details, row }: { coin: any, details: Record<string, AssetDetail>, row?: any }) {
  const [anchor, setAnchor] = useState<{ left: number, top: number } | null>(null)
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const symbol = displayToken(String(coin || ''))
  const canonical = canonicalToken(symbol)
  const meta = details[canonical] || details[symbol] || {}
  const longUsd = Number(row?.value_long_usd || meta?.value_long_usd || 0)
  const shortUsd = Number(row?.value_short_usd || meta?.value_short_usd || 0)
  const gross = Number(row?.gross_exposure_usd || row?.gross_value_usd || meta?.gross_exposure_usd || (longUsd + shortUsd) || row?.notional_usd || row?.value_usd || 0)
  const tilt = String(meta?.tilt || row?.tilt || row?.signal_label || row?.direction || (longUsd || shortUsd ? (longUsd >= shortUsd ? 'Long' : 'Short') : '—'))
  const conviction = Number(meta?.conviction_pct || row?.conviction_pct || 0)
  const flowValue = Number(meta?.net_flow_usd || row?.net_value_flow_usd || row?.net_value_usd || row?.delta_value_usd || row?.notional_usd || 0)
  const place = (el: HTMLElement) => {
    const rect = el.getBoundingClientRect()
    const width = 288
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))
    const top = Math.max(12, Math.min(rect.bottom + 10, window.innerHeight - 240))
    setAnchor({ left, top })
  }
  const show = (e: any) => place(e.currentTarget as HTMLElement)
  const hide = () => setAnchor(null)
  const tooltip = anchor && mounted ? createPortal(<div className="cc-asset-tooltip-portal" style={{ left: anchor.left, top: anchor.top }}><strong>{meta?.name || tokenFullName(symbol)}</strong><em>{symbol} on Hyperliquid</em><dl><dt>Mark price</dt><dd>{priceText(meta?.current_price)}</dd><dt>Tracked tilt</dt><dd className={tilt.toLowerCase().includes('short') ? 'negative' : tilt.toLowerCase().includes('long') ? 'positive' : ''}>{tilt}{conviction ? ` · ${Math.round(conviction)}%` : ''}</dd><dt>Open exposure</dt><dd>{gross ? money(gross) : '—'}</dd>{meta?.max_leverage ? <><dt>Max leverage</dt><dd>{meta.max_leverage}x</dd></> : null}<dt>Wallets</dt><dd>{Number(meta?.wallets_long || row?.wallets_long || 0)} long / {Number(meta?.wallets_short || row?.wallets_short || 0)} short</dd><dt>Recent flow</dt><dd className={flowValue < 0 ? 'negative' : flowValue > 0 ? 'positive' : ''}>{flowValue ? signed(flowValue) : '—'}</dd></dl></div>, document.body) : null
  return <span className="cc-asset-hover" tabIndex={0} onMouseEnter={show} onMouseMove={show} onMouseLeave={hide} onFocus={show} onBlur={hide}><b>{symbol}</b>{tooltip}</span>
}

const USDC_LOGO_DATA_URI = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxMjggMTI4Jz48Y2lyY2xlIGN4PSc2NCcgY3k9JzY0JyByPSc2NCcgZmlsbD0nIzI3NzVDQScvPjxwYXRoIGQ9J000MiAzMGE0MiA0MiAwIDAgMCAwIDY4JyBmaWxsPSdub25lJyBzdHJva2U9JyNmZmYnIHN0cm9rZS13aWR0aD0nOCcgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJy8+PHBhdGggZD0nTTg2IDMwYTQyIDQyIDAgMCAxIDAgNjgnIGZpbGw9J25vbmUnIHN0cm9rZT0nI2ZmZicgc3Ryb2tlLXdpZHRoPSc4JyBzdHJva2UtbGluZWNhcD0ncm91bmQnLz48dGV4dCB4PSc2NCcgeT0nODQnIHRleHQtYW5jaG9yPSdtaWRkbGUnIGZvbnQtZmFtaWx5PSdBcmlhbCxIZWx2ZXRpY2Esc2Fucy1zZXJpZicgZm9udC1zaXplPSc1OCcgZm9udC13ZWlnaHQ9JzgwMCcgZmlsbD0nI2ZmZic+JDwvdGV4dD48L3N2Zz4='
const fallbackColours: Record<string, string> = { HYPE:'#43E8D0', ETH:'#627EEA', BTC:'#F7931A', SOL:'#14F195', ZEC:'#F4B728', NEAR:'#00EC97', AAVE:'#8B7DFF', TRX:'#FF4B4B', XRP:'#4B9FFF', USDC:'#2775CA', 'USDC/CASH':'#2775CA', MELANIA:'#D7A785', PUMP:'#61C685', LIT:'#35D0B4', BNB:'#F3BA2F', XLM:'#44BDEC', PENGU:'#A0D7F8', LTC:'#345D9D', SUI:'#4CA3FF', AVAX:'#E84142' }
const staticLogoUrls: Record<string, string> = {
  BTC:'https://cryptologos.cc/logos/bitcoin-btc-logo.svg?v=040', ETH:'https://cryptologos.cc/logos/ethereum-eth-logo.svg?v=040', SOL:'https://cryptologos.cc/logos/solana-sol-logo.svg?v=040', USDC:'https://raw.githubusercontent.com/trustwallet/assets/master/blockchains/ethereum/assets/0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48/logo.png', USDT:'https://cryptologos.cc/logos/tether-usdt-logo.svg?v=040', DOGE:'https://cryptologos.cc/logos/dogecoin-doge-logo.svg?v=040',
  AAVE:'https://cryptologos.cc/logos/aave-aave-logo.svg?v=040', TRX:'https://cryptologos.cc/logos/tron-trx-logo.svg?v=040', XRP:'https://cryptologos.cc/logos/xrp-xrp-logo.svg?v=040', AVAX:'https://cryptologos.cc/logos/avalanche-avax-logo.svg?v=040', BNB:'https://cryptologos.cc/logos/bnb-bnb-logo.svg?v=040', LINK:'https://cryptologos.cc/logos/chainlink-link-logo.svg?v=040', UNI:'https://cryptologos.cc/logos/uniswap-uni-logo.svg?v=040', LTC:'https://cryptologos.cc/logos/litecoin-ltc-logo.svg?v=040', DOT:'https://cryptologos.cc/logos/polkadot-new-dot-logo.svg?v=040', NEAR:'https://cryptologos.cc/logos/near-protocol-near-logo.svg?v=040', ZEC:'https://cryptologos.cc/logos/zcash-zec-logo.svg?v=040', ARB:'https://cryptologos.cc/logos/arbitrum-arb-logo.svg?v=040', SUI:'https://cryptologos.cc/logos/sui-sui-logo.svg?v=040', OP:'https://cryptologos.cc/logos/optimism-ethereum-op-logo.svg?v=040'
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
function AssetCell({ coin, icons, details, row }: { coin: any, icons: Record<string, string>, details: Record<string, AssetDetail>, row?: any }) {
  const symbol = displayToken(String(coin || '—'))
  return <span className="cc-api-asset-cell"><TokenLogo coin={symbol} icons={icons} /><AssetName coin={symbol} details={details} row={row} /></span>
}

export default function ApiAccessPage() {
  const [status, setStatus] = useState<Status>({})
  const [leaderboard, setLeaderboard] = useState<any[]>([])
  const [tokens, setTokens] = useState<any[]>([])
  const [coverage, setCoverage] = useState<any>({})
  const [orders, setOrders] = useState<any[]>([])
  const [baseUrl, setBaseUrl] = useState('/copycat-data')
  const [icons, setIcons] = useState<Record<string, string>>({})
  const [assetDetails, setAssetDetails] = useState<Record<string, AssetDetail>>({})

  useEffect(() => {
    let cancelled = false
    setBaseUrl(snapshotBase())
    async function load() {
      try {
        const [s, l, t, c, feed] = await Promise.all([
          apiGet('/api/data/v1/status').catch(() => ({})),
          apiGet('/api/data/v1/public/leaderboard-preview?limit=50').catch(() => ({})),
          apiGet('/api/data/v1/public/token-screener-preview?limit=30').catch(() => ({})),
          apiGet('/api/data/v1/public/coverage-preview').catch(() => ({})),
          apiGet('/api/dashboard-feed').catch(() => ({})),
        ])
        if (!cancelled) {
          setStatus(s || {})
          setLeaderboard(l?.rows || l?.data || [])
          setTokens(t?.rows || t?.data || [])
          setCoverage(c || {})
          setOrders(feed?.orders || feed?.recent_orders || [])
        }
      } catch {}
    }
    load()
    const id = window.setInterval(load, 60000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [])

  const scanned = Number(status.scanner_candidate_wallets_scored ?? coverage.scanner_candidate_wallets_scored ?? coverage.candidate_wallets_scored ?? 0)
  const selected = Number(status.selected_wallet_count ?? coverage.selected_wallet_count ?? coverage.wallets_configured ?? 50)
  const updatedAt = status.updated_at_ms || coverage.updated_at_ms
  const topClaimReady = Boolean(status.top_claim_ready || coverage.top_claim_ready)
  const claim = useMemo(() => topClaimReady
    ? `Copycat is publishing ranked Hyperliquid wallet intelligence from ${compact(scanned)} locally indexed candidates.`
    : `Copycat is publishing ranked Hyperliquid wallet intelligence from ${compact(scanned)} locally indexed candidates. This is not yet an all-Hyperliquid top-50 profit claim.`, [topClaimReady, scanned])

  const symbolKey = useMemo(() => Array.from(new Set([
    ...tokens.map((r: any) => r.coin),
    ...orders.map((r: any) => r.coin || r.asset),
  ].filter(Boolean).map(x => canonicalToken(String(x).toUpperCase())))).sort().join(','), [tokens, orders])

  useEffect(() => {
    if (!symbolKey) return
    const cacheKey = 'copycat-api-token-icons:' + symbolKey
    try {
      const cached = localStorage.getItem(cacheKey)
      if (cached) setIcons(JSON.parse(cached))
    } catch {}
    const visibleSymbols = symbolKey.split(',').slice(0, 80).join(',')
    const timer = window.setTimeout(() => {
      apiGet('/api/token-icons?limit=80&symbols=' + encodeURIComponent(visibleSymbols), { timeoutMs: 3500 }).then((r: any) => {
        const nextIcons = r.icons || {}
        setIcons(nextIcons)
        try { localStorage.setItem(cacheKey, JSON.stringify(nextIcons)) } catch {}
      }).catch(() => {})
      apiGet('/api/data/v1/public/asset-details?symbols=' + encodeURIComponent(visibleSymbols), { timeoutMs: 3500 }).then((r: any) => {
        setAssetDetails(r.assets || r.details || {})
      }).catch(() => {})
    }, 800)
    return () => clearTimeout(timer)
  }, [symbolKey])

  const endpoints = [
    ['Dashboard feed', `${baseUrl}/dashboard-feed.json`, 'Dashboard-ready aggregate snapshot.'],
    ['Performance index', `${baseUrl}/performance-index.json`, 'Live model index and benchmarks.'],
    ['Ranked wallets', `${baseUrl}/api/leaderboard-preview.json`, 'Live cohort with total wallet value, perp equity and exposure.'],
    ['Token screener', `${baseUrl}/api/token-screener-preview.json`, 'Market-level positioning snapshot.'],
    ['Coverage status', `${baseUrl}/api/coverage-preview.json`, 'Freshness and coverage checks.'],
    ['Ranking audit', `${baseUrl}/api/ranking-audit.json`, 'Quality checks for the public snapshot.'],
  ]
  const pipeline = [
    ['Hyperliquid', 'public wallet + market state'],
    ['Local scanner', `${compact(scanned)} candidates assessed`],
    ['Ranking layer', 'activity, size + exposure checks'],
    ['Top selection', `${compact(selected)} tracked wallets`],
    ['Snapshot publisher', 'compact JSON refreshes'],
    ['Copycat API', 'dashboard, preview + audit files'],
  ]

  return <><Nav/><main className="cc-dashboard-shell cc-api-intel-page"><LineBackdrop variant="dashboard" />
    <section className="cc-api-intel-hero cc-card">
      <div className="cc-api-hero-copy">
        <p className="eyebrow live">Copycat Data Intelligence</p>
        <h1>Live Hyperliquid wallet intelligence.</h1>
        <p>Ranked wallet selections, market-level positioning, recent tracked-wallet flow and public snapshot endpoints powering Copycat.</p>
        <div className="action-row"><a className="primary-btn" href="/dashboard">Open dashboard <span>→</span></a><a className="outline-btn" href="#snapshot-endpoints">View endpoints</a></div>
      </div>
    </section>

    <section className="cc-api-pipeline cc-card">
      <div className="cc-api-pipeline-copy">
        <p className="eyebrow live">How the data is built</p>
        <h2>From Hyperliquid wallets to Copycat signals.</h2>
        <p>The flow below shows the data path before it becomes a dashboard signal or public API snapshot.</p>
      </div>
      <div className="cc-api-flow-chain" aria-label="Copycat data pipeline">
        {pipeline.map((step, index) => <div className="cc-api-flow-node" key={step[0]}>
          <div className="cc-api-flow-step"><b>{step[0]}</b><span>{step[1]}</span></div>
          {index < pipeline.length - 1 ? <i className="cc-api-flow-arrow" aria-hidden /> : null}
        </div>)}
      </div>
    </section>

    <section className="cc-api-nansen-grid">
      <article className="cc-card cc-api-data-card cc-api-leaderboard-card">
        <header><div><p className="eyebrow live">Live wallet cohort</p><h2>Live wallet selection</h2></div><span>live</span></header>
        <div className="cc-api-table-wrap"><table><thead><tr><th>#</th><th>Wallet</th><th>Total value</th><th>Perp equity</th><th>Exposure</th></tr></thead><tbody>{leaderboard.slice(0, 50).map((r:any, i:number) => <tr key={r.wallet || i}><td>{r.rank || i + 1}</td><td><WalletLink row={r} /></td><td title={walletTotalValueTitle(r)}>{walletTotalValue(r)}</td><td>{money(r.perp_account_value_usd ?? r.account_value_usd)}</td><td><span className="cc-mini-bar"><i style={{width: `${Math.max(8, Math.min(100, Number(r.open_position_value_usd || 0) / Math.max(1, Number(leaderboard[0]?.open_position_value_usd || 1)) * 100))}%`}} />{money(r.open_position_value_usd)}</span></td></tr>)}</tbody></table></div>
      </article>

      <article className="cc-card cc-api-data-card cc-api-market-card">
        <header><div><p className="eyebrow live">Token screener</p><h2>Markets the selection is leaning into</h2></div><span>top conviction</span></header>
        <div className="cc-api-table-wrap"><table><thead><tr><th>Asset</th><th>Tilt</th><th>Wallets</th><th>Exposure</th><th>Net</th></tr></thead><tbody>{tokens.slice(0, 24).map((r:any, i:number) => { const label = biasLabel(r); return <tr key={r.coin || i}><td><AssetCell coin={r.coin} icons={icons} details={assetDetails} row={r} /></td><td className={biasClass(label)}>{label}</td><td>{compact(r.wallets_long)}L / {compact(r.wallets_short)}S</td><td>{money(r.gross_value_usd || r.gross_exposure_usd)}</td><td className={biasClass(r.net_value_usd)}>{signed(r.net_value_usd)}</td></tr> })}</tbody></table></div>
      </article>
    </section>

    <section id="recent-activity" className="cc-card cc-api-data-card cc-api-activity-card">
      <header><div><p className="eyebrow live">Live tracked-wallet tape</p><h2>Recent tracked-wallet activity</h2></div><span>{freshness(updatedAt)}</span></header>
      <div className="cc-api-table-wrap"><table><thead><tr><th>Wallet</th><th>Action</th><th>Asset</th><th>Value</th><th>Time</th></tr></thead><tbody>{orders.slice(0, 24).map((r:any, i:number) => <tr key={`${r.wallet || 'wallet'}-${r.ts_ms || i}`}><td><WalletLink row={r} /></td><td className={actionClass(r.side || r.action)}>{r.side || r.action || 'Order'}</td><td><AssetCell coin={r.coin || r.asset} icons={icons} details={assetDetails} row={r} /></td><td>{money(r.delta_value_usd || r.position_value_usd || r.value_usd || r.notional_usd)}</td><td>{freshness(r.ts_ms)}</td></tr>)}</tbody></table></div>
    </section>

    <section id="snapshot-endpoints" className="cc-card cc-api-endpoints-pro">
      <div className="cc-api-endpoints-copy"><p className="eyebrow live">Snapshot endpoints</p><h2>Public read-only data files</h2><p>Clean JSON previews for the dashboard, market screens, leaderboard samples, coverage checks and audit status.</p></div>
      <div className="cc-api-endpoint-grid">
        {endpoints.map(([title, url, description]) => <code key={title}><b>{title}</b><span>GET {url}</span><em>{description}</em></code>)}
      </div>
    </section>

    <footer className="cc-warning-banner cc-api-warning"><span className="cc-shield" aria-hidden>♢</span><div className="cc-footer-main"><strong>Market intelligence only.</strong><em>{claim} Not financial advice. Public snapshots are read-only and may be delayed, cached or temporarily stale.</em></div><div className="cc-footer-status"><span className="cc-quality-dot" /> Data quality snapshot · {freshness(updatedAt)}</div></footer>
  </main></>
}
