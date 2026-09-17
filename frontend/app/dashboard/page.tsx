'use client'

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import PublicNav from '../../components/PublicNav'
import { apiGet } from '../../lib/api'
import { assetHistory, loadPositionHistory, positionChartPath, type PositionFrame, type PositionSample } from '../../lib/position-history'
import PerformanceIndex from '../../components/PerformanceIndex'
import './dashboard-redesign.css'

const COPYCAT_FEED_POLL_MS = Number(process.env.NEXT_PUBLIC_DASHBOARD_FEED_POLL_MS || 60000)
const COPYCAT_TICK_POLL_MS = Number(process.env.NEXT_PUBLIC_DASHBOARD_TICK_POLL_MS || 15000)


function money(n: any) {
  return '$' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })
}
function useRollingNumber(value: any, durationMs = 850) {
  const target = Number(value || 0)
  const [display, setDisplay] = useState(target)
  const previous = useRef(target)
  useEffect(() => {
    const from = previous.current
    const to = Number(value || 0)
    previous.current = to
    if (!Number.isFinite(to) || Math.abs(to - from) < 1) {
      setDisplay(to)
      return
    }
    let frame = 0
    const started = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - started) / durationMs)
      const eased = 1 - Math.pow(1 - t, 3)
      setDisplay(from + (to - from) * eased)
      if (t < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs, value])
  return display
}
function RollingMoney({ value }: { value: any }) {
  const display = useRollingNumber(value)
  return <b className="cc-rolling-number">{money(display)}</b>
}
function RollingInteger({ value }: { value: any }) {
  const display = useRollingNumber(value, 650)
  return <b className="cc-rolling-number">{Math.round(Number(display || 0)).toLocaleString()}</b>
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

function displaySignalMagnitudePct(row: any) {
  return `${Math.round(Math.abs(displaySignalValue(row)) * 100)}%`
}
function displaySignalDirection(row: any) {
  const value = displaySignalValue(row)
  if (value > 0) return 'Long'
  if (value < 0) return 'Short'
  return 'Neutral'
}

function signalConvictionParts(row: any) {
  const strength = Math.abs(displaySignalValue(row))
  const net = Math.abs(Number(row?.net_value_usd || 0))
  const gross = Number(row?.value_long_usd || 0) + Number(row?.value_short_usd || 0)
  const wallets = Number(row?.wallets_long || 0) + Number(row?.wallets_short || 0)
  const confidenceRank: Record<string, number> = { high: 3, medium: 2, med: 2, low: 1, reserve: 0 }
  const confidence = confidenceRank[String(row?.confidence || '').toLowerCase()] ?? 0
  return { confidence, strength, wallets, net, gross }
}

function signalDirectionClass(row: any) {
  const direction = displaySignalDirection(row).toLowerCase()
  if (direction === 'long') return 'long'
  if (direction === 'short') return 'short'
  return 'neutral'
}

function cls(n: any) { return Number(n) >= 0 ? 'positive' : 'negative' }

function flowPressureScore(row: any) {
  const bullish = Math.abs(Number(row?.bullish_flow_usd || row?.bullish_value_flow_usd || 0))
  const bearish = Math.abs(Number(row?.bearish_flow_usd || row?.bearish_value_flow_usd || 0))
  const net = Math.abs(Number(row?.net_value_flow_usd || 0))
  const gross = bullish + bearish
  const netBuyerScore = Math.abs(Number(row?.net_buyer_count || 0)) * 1000
  // Most useful recent pressure = clear net value flow, with some credit for
  // heavy gross activity and several wallets leaning the same way.
  return net + gross * 0.25 + netBuyerScore
}

function flowRead(netValueFlowUsd: any) {
  const n = Number(netValueFlowUsd || 0)
  return n > 1000 ? 'Accumulation' : n < -1000 ? 'Distribution' : 'Neutral'
}

function flowInsightLabel(x: any) {
  const label = String(x?.label || '')
  if (/biggest accumulation/i.test(label)) return 'Recent accumulation'
  if (/biggest distribution/i.test(label)) return 'Recent distribution'
  return label
}

function shouldShowInsight(x: any) {
  const label = flowInsightLabel(x)
  const type = String(x?.type || '')
  return !/largest current exposure|gross leverage/i.test(label) && !/gross[_ -]?leverage|leverage/i.test(type)
}

function flowWindowText(summary: any) {
  const minutes = Number(summary?.signal_lookback_minutes || summary?.flow_lookback_minutes || 60)
  if (!Number.isFinite(minutes) || minutes <= 0) return 'recent order flow'
  if (minutes < 60) return `last ${Math.round(minutes)}m order flow`
  const hours = minutes / 60
  return hours === 1 ? 'last 60m order flow' : `last ${hours.toFixed(hours % 1 ? 1 : 0)}h order flow`
}
function flowIntensityText(flowRows: any[], openValue: any) {
  const open = Math.abs(Number(openValue || 0))
  const grossFlow = (flowRows || []).reduce((sum, row) => sum + Math.abs(Number(row.bullish_flow_usd || row.bullish_value_flow_usd || 0)) + Math.abs(Number(row.bearish_flow_usd || row.bearish_value_flow_usd || 0)), 0)
  if (!open || !Number.isFinite(open) || grossFlow <= 0) return 'Flow intensity: awaiting recent orders'
  const share = (grossFlow / open) * 100
  const label = share < 0.01 ? '<0.01%' : `${share.toFixed(share < 1 ? 2 : 1)}%`
  return `Flow intensity: ${label} of open exposure`
}
function largestCurrentExposure(signals: any[]) {
  const rows = [...(signals || [])]
    .map((row: any) => {
      const long = Number(row.value_long_usd || 0)
      const short = Number(row.value_short_usd || 0)
      const net = Number(row.net_value_usd || (long - short) || 0)
      return { coin: row.coin, net, value: Math.abs(net), direction: net >= 0 ? 'Long' : 'Short' }
    })
    .filter((row: any) => row.coin && Number.isFinite(row.value) && row.value > 0)
    .sort((a: any, b: any) => b.value - a.value)
  return rows[0] || null
}
function orderActionClass(side: any) {
  const s = String(side || '').toLowerCase()
  if (s.includes('open short') || s.includes('add short') || s.includes('reduce long') || s.includes('close long')) return 'negative'
  return 'positive'
}
function orderKey(o: any) {
  return [o.source || 'snapshot', o.wallet || '', o.coin || '', o.ts_ms || '', o.side || '', Math.round(Number(o.delta_value_usd || o.notional_usd || 0))].join(':')
}
function ago(ms: any) { const m = Math.max(0, Math.round((Date.now() - Number(ms || Date.now())) / 60000)); if (m < 1) return 'just now'; if (m < 60) return `${m}m ago`; return `${Math.round(m / 60)}h ago` }
function fmtTime(ms: any) {
  if (!ms) return 'Awaiting first refresh'
  return new Date(Number(ms)).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }).replace(',', '')
}
function maskWallet(w: string) {
  const wallet = String(w || '').trim()
  if (!wallet) return 'Wallet'
  if (wallet.length <= 14) return wallet
  return `${wallet.slice(0, 6)}...${wallet.slice(-4)}`
}
function hypurrscanAddressUrl(w: string) {
  const wallet = String(w || '').trim()
  return /^0x[a-fA-F0-9]{40}$/.test(wallet) ? `https://hypurrscan.io/address/${wallet}` : ''
}
function WalletExplorerLink({ wallet, label }: { wallet?: string; label?: string }) {
  const rawWallet = String(wallet || '').trim()
  const url = hypurrscanAddressUrl(rawWallet)
  const text = rawWallet ? maskWallet(rawWallet) : (String(label || '').trim() || 'Wallet')
  if (!url) return <em>{text}</em>
  return <em><a href={url} target="_blank" rel="noopener noreferrer" title="Open wallet on HypurrScan" style={{ color: 'inherit', textDecoration: 'none' }}>{text}</a></em>
}

function walletUniverseCaption(summary: any) {
  const indexed = Number(summary?.indexed_wallets || summary?.known_wallet_candidates || summary?.registry_wallets || 0)
  const analysed = Number(summary?.latest_scanner_candidate_wallets_scored || 0)
  if (indexed > 0 && analysed > 0) return `${indexed.toLocaleString()} indexed  |  ${analysed.toLocaleString()} fully analysed`
  if (indexed > 0) return `${indexed.toLocaleString()} wallets indexed locally`
  if (summary?.live_coverage_mode === 'local_snapshot') return 'local scanner universe'
  return 'ranked daily'
}
function footerUniverseCaption(summary: any) {
  const live = Number(summary?.live_wallets || summary?.tracked_active_wallets || 0)
  const indexed = Number(summary?.indexed_wallets || summary?.known_wallet_candidates || summary?.registry_wallets || 0)
  if (live && indexed) return `  |  ${live} live wallets  |  ${indexed} indexed`
  if (live) return `  |  ${live} live wallets`
  return ''
}


const USDC_LOGO_DATA_URI = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxMjggMTI4Jz48Y2lyY2xlIGN4PSc2NCcgY3k9JzY0JyByPSc2NCcgZmlsbD0nIzI3NzVDQScvPjxwYXRoIGQ9J000MiAzMGE0MiA0MiAwIDAgMCAwIDY4JyBmaWxsPSdub25lJyBzdHJva2U9JyNmZmYnIHN0cm9rZS13aWR0aD0nOCcgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJy8+PHBhdGggZD0nTTg2IDMwYTQyIDQyIDAgMCAxIDAgNjgnIGZpbGw9J25vbmUnIHN0cm9rZT0nI2ZmZicgc3Ryb2tlLXdpZHRoPSc4JyBzdHJva2UtbGluZWNhcD0ncm91bmQnLz48dGV4dCB4PSc2NCcgeT0nODQnIHRleHQtYW5jaG9yPSdtaWRkbGUnIGZvbnQtZmFtaWx5PSdBcmlhbCxIZWx2ZXRpY2Esc2Fucy1zZXJpZicgZm9udC1zaXplPSc1OCcgZm9udC13ZWlnaHQ9JzgwMCcgZmlsbD0nI2ZmZic+JDwvdGV4dD48L3N2Zz4='
const palette = ['#43E8D0', '#8057FF', '#44BDEC', '#FFB020', '#25D366', '#F35EA6', '#A6E22E', '#FF5B72', '#38BDF8', '#F97316']
const fallbackColours: Record<string, string> = { HYPE:'#43E8D0', ETH:'#627EEA', BTC:'#F7931A', SOL:'#14F195', ZEC:'#F4B728', NEAR:'#00EC97', AAVE:'#8B7DFF', TRX:'#FF4B4B', XRP:'#4B9FFF', USDC:'#2775CA', 'USDC/CASH':'#2775CA', MELANIA:'#D7A785', WLD:'#8492A6', PAXG:'#F0C419', PUMP:'#61C685', LIT:'#35D0B4', BNB:'#F3BA2F', XLM:'#44BDEC', PENGU:'#A0D7F8', SUI:'#6FBCF0', BCH:'#8DC351', UNI:'#FF007A', ALGO:'#CCD5DE', CASHCAT:'#43E8D0', WLFI:'#D4AF37' }
const staticLogoUrls: Record<string, string> = {
  BTC:'https://cryptologos.cc/logos/bitcoin-btc-logo.svg?v=040', ETH:'https://cryptologos.cc/logos/ethereum-eth-logo.svg?v=040', SOL:'https://cryptologos.cc/logos/solana-sol-logo.svg?v=040', USDC:'https://raw.githubusercontent.com/trustwallet/assets/master/blockchains/ethereum/assets/A0b86991c6218b36c1d19d4a2e9eb0ce3606eb48/logo.png', USDT:'https://cryptologos.cc/logos/tether-usdt-logo.svg?v=040', DOGE:'https://cryptologos.cc/logos/dogecoin-doge-logo.svg?v=040',
  AAVE:'https://cryptologos.cc/logos/aave-aave-logo.svg?v=040', TRX:'https://cryptologos.cc/logos/tron-trx-logo.svg?v=040', XRP:'https://cryptologos.cc/logos/xrp-xrp-logo.svg?v=040', AVAX:'https://cryptologos.cc/logos/avalanche-avax-logo.svg?v=040', BNB:'https://cryptologos.cc/logos/bnb-bnb-logo.svg?v=040', LINK:'https://cryptologos.cc/logos/chainlink-link-logo.svg?v=040', UNI:'https://cryptologos.cc/logos/uniswap-uni-logo.svg?v=040', LTC:'https://cryptologos.cc/logos/litecoin-ltc-logo.svg?v=040', DOT:'https://cryptologos.cc/logos/polkadot-new-dot-logo.svg?v=040', FIL:'https://cryptologos.cc/logos/filecoin-fil-logo.svg?v=040', ATOM:'https://cryptologos.cc/logos/cosmos-atom-logo.svg?v=040', NEAR:'https://cryptologos.cc/logos/near-protocol-near-logo.svg?v=040', ZEC:'https://cryptologos.cc/logos/zcash-zec-logo.svg?v=040', ARB:'https://cryptologos.cc/logos/arbitrum-arb-logo.svg?v=040', SUI:'https://cryptologos.cc/logos/sui-sui-logo.svg?v=040', OP:'https://cryptologos.cc/logos/optimism-ethereum-op-logo.svg?v=040', APE:'https://cryptologos.cc/logos/apecoin-ape-ape-logo.svg?v=040', INJ:'https://cryptologos.cc/logos/injective-inj-logo.svg?v=040', FET:'https://cryptologos.cc/logos/artificial-superintelligence-alliance-fet-logo.svg?v=040'
}
function canonicalToken(symbol: string) {
  const clean = String(symbol || '').toUpperCase().trim()
  if (clean === 'USDC/CASH' || clean === 'USDCCASH' || clean === 'USDCASH' || clean === 'CASH') return 'USDC'
  return clean.replace(/[^A-Z0-9]/g, '')
}

function tokenFullName(symbol: string) {
  const clean = canonicalToken(symbol)
  const names: Record<string, string> = { BTC: 'Bitcoin', ETH: 'Ethereum', HYPE: 'Hyperliquid', SOL: 'Solana', USDC: 'USD Coin', USDT: 'Tether', BNB: 'BNB', XRP: 'XRP', DOGE: 'Dogecoin', AVAX: 'Avalanche', LINK: 'Chainlink', AAVE: 'Aave', SUI: 'Sui', NEAR: 'NEAR Protocol', ZEC: 'Zcash', TRX: 'TRON', XLM: 'Stellar', DOT: 'Polkadot', LTC: 'Litecoin', UNI: 'Uniswap', ARB: 'Arbitrum', OP: 'Optimism', PAXG: 'PAX Gold' }
  return names[clean] || clean
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

function priceText(n: any) {
  const value = Number(n || 0)
  if (!value) return '—'
  if (value >= 1000) return '$' + value.toLocaleString(undefined, { maximumFractionDigits: 0 })
  if (value >= 1) return '$' + value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return '$' + value.toLocaleString(undefined, { maximumSignificantDigits: 4 })
}


function AssetName({ coin, details, row, compact = false, children }: { coin: any, details: Record<string, AssetDetail>, row?: any, compact?: boolean, children?: ReactNode }) {
  const [anchor, setAnchor] = useState<{ left: number, top: number } | null>(null)
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const symbol = displayToken(String(coin || ''))
  const canonical = canonicalToken(symbol)
  const meta = details[canonical] || details[symbol] || {}
  const longUsd = Number(row?.value_long_usd || meta?.value_long_usd || 0)
  const shortUsd = Number(row?.value_short_usd || meta?.value_short_usd || 0)
  const gross = Number(row?.gross_exposure_usd || row?.gross_value_usd || meta?.gross_exposure_usd || (longUsd + shortUsd) || 0)
  const markPrice = Number(row?.current_price || row?.mark_price || row?.price_usd || meta?.current_price || (meta as any)?.price_usd || 0)
  const tilt = String(meta?.tilt || row?.tilt || (longUsd || shortUsd ? (longUsd >= shortUsd ? 'Long' : 'Short') : '—'))
  const conviction = Number(meta?.conviction_pct || row?.conviction_pct || 0)
  const flowValue = Number(meta?.net_flow_usd || row?.net_value_flow_usd || row?.delta_value_usd || row?.notional_usd || 0)
  const place = (el: HTMLElement) => {
    const rect = el.getBoundingClientRect()
    const width = 288
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))
    const top = Math.max(12, Math.min(rect.bottom + 10, window.innerHeight - 240))
    setAnchor({ left, top })
  }
  const show = (e: any) => place(e.currentTarget as HTMLElement)
  const hide = () => setAnchor(null)
  const tooltip = anchor && mounted ? createPortal(<div className="cc-asset-tooltip-portal" style={{ left: anchor.left, top: anchor.top }}><strong>{meta?.name || tokenFullName(symbol)}</strong><em>{symbol} on Hyperliquid</em><dl><dt>Mark price</dt><dd>{priceText(markPrice)}</dd><dt>Tracked tilt</dt><dd className={tilt.toLowerCase().includes('short') ? 'negative' : tilt.toLowerCase().includes('long') ? 'positive' : ''}>{tilt}{conviction ? `  |  ${Math.round(conviction)}%` : ''}</dd><dt>Open exposure</dt><dd>{gross ? compactMoney(gross) : '—'}</dd>{meta?.max_leverage ? <><dt>Max leverage</dt><dd>{meta.max_leverage}x</dd></> : null}<dt>Wallets</dt><dd>{Number(meta?.wallets_long || row?.wallets_long || 0)} long / {Number(meta?.wallets_short || row?.wallets_short || 0)} short</dd><dt>Recent flow</dt><dd className={flowValue < 0 ? 'negative' : flowValue > 0 ? 'positive' : ''}>{flowValue ? compactMoney(flowValue) : '—'}</dd></dl></div>, document.body) : null
  return <span className="cc-asset-hover" tabIndex={0} onMouseEnter={show} onMouseMove={show} onMouseLeave={hide} onFocus={show} onBlur={hide} onClick={show} onKeyDown={(e) => { if (e.key === 'Escape') hide() }} aria-label={children ? `${symbol} asset details` : undefined}>{children || <b>{symbol}</b>}{tooltip}</span>
}

function tokenColour(symbol: string, index: number) {
  const raw = String(symbol || '').toUpperCase()
  return fallbackColours[raw] || fallbackColours[canonicalToken(raw)] || palette[index % palette.length]
}

type Segment = { coin: string; weight: number; color: string; originalWeight: number; direction?: string }

function AllocationDonut({ targets, signals, trackedValue, icons, assetDetails }: { targets: any[]; signals: any[]; trackedValue: number; icons: Record<string, string>; assetDetails: Record<string, AssetDetail> }) {
  const [hovered, setHovered] = useState<Segment | null>(null)
  const parts: Segment[] = useMemo(() => {
    let rows = [...(targets || [])]
      .map((t: any) => ({ coin: displayToken(t.coin), weight: Math.abs(Number(t.target_weight ?? t.index_weight ?? 0)), direction: String(t.direction || (Number(t.index_weight || 0) < 0 ? 'short' : 'long')).toLowerCase() }))
      .filter((r: any) => r.weight > 0 && canonicalToken(r.coin) !== 'USDC')
      .sort((a: any, b: any) => b.weight - a.weight)
    if (!rows.length) {
      rows = [...(signals || [])]
        .map((r: any) => ({ coin: displayToken(r.coin), weight: Math.abs(Number(r.net_value_usd || 0) || (Number(r.value_long_usd || 0) - Number(r.value_short_usd || 0))), direction: (Number(r.net_value_usd || 0) || (Number(r.value_long_usd || 0) - Number(r.value_short_usd || 0))) < 0 ? 'short' : 'long' }))
        .filter((r: any) => r.weight > 0 && canonicalToken(r.coin) !== 'USDC')
        .sort((a: any, b: any) => b.weight - a.weight)
    }
    let top = rows.slice(0, 12)
    const remaining = rows.slice(12).reduce((a: number, r: any) => a + r.weight, 0)
    if (remaining > 0) top = [...top, { coin: 'OTHER', weight: remaining, direction: 'mixed' }]
    const total = top.reduce((a: number, r: any) => a + r.weight, 0) || 1
    return top.map((t: any, i: number) => ({ coin: t.coin, direction: t.direction, originalWeight: Number(t.weight || 0) / total, weight: Number(t.weight || 0) / total, color: tokenColour(t.coin, i) }))
  }, [targets, signals])
  let angle = -90
  const path = (cx: number, cy: number, r1: number, r2: number, a0: number, a1: number) => {
    const p = (r: number, a: number) => { const rad = a * Math.PI / 180; return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) } }
    const s1 = p(r1, a0), e1 = p(r1, a1), s2 = p(r2, a1), e2 = p(r2, a0); const large = a1 - a0 > 180 ? 1 : 0
    return `M ${s1.x} ${s1.y} A ${r1} ${r1} 0 ${large} 1 ${e1.x} ${e1.y} L ${s2.x} ${s2.y} A ${r2} ${r2} 0 ${large} 0 ${e2.x} ${e2.y} Z`
  }
  if (!parts.length) return <div className="cc-empty-state">Targets will appear after refresh.</div>
  return <div className="cc-donut-layout"><div className="cc-donut-stage"><svg viewBox="0 0 220 220" className="cc-donut-svg" aria-label="Copycat Index allocation">{parts.map((p: any) => { const start = angle; angle += p.weight * 360; return <path key={`${p.coin}-${p.direction}`} d={path(110, 110, 92, 50, start, angle - 1)} fill={p.color} onMouseEnter={() => setHovered(p)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(p)} onBlur={() => setHovered(null)} tabIndex={0}><title>{p.direction === 'short' ? 'Short ' : p.direction === 'long' ? 'Long ' : ''}{displayToken(p.coin)}: {Math.round(p.originalWeight * 100)}%</title></path> })}<circle className="cc-donut-hole" cx="110" cy="110" r="50" /></svg><div className="cc-donut-tooltip">{hovered ? `${hovered.direction === 'short' ? 'Short ' : hovered.direction === 'long' ? 'Long ' : ''}${displayToken(hovered.coin)} ${Math.round(hovered.originalWeight * 100)}% index allocation` : 'USDC margin is excluded from this allocation.'}</div></div><div className="cc-donut-legend cc-scroll-y">{parts.map((p: any) => {
    const allocationPct = Math.round(p.originalWeight * 100)
    const allocationDirection = p.direction === 'short' ? 'short' : p.direction === 'long' ? 'long' : 'mixed'
    return <div className="cc-allocation-legend-row" key={`${p.coin}-${p.direction}`}><TokenLogo coin={p.coin} icons={icons} /><AssetName coin={p.coin} details={assetDetails} row={{ gross_exposure_usd: p.originalWeight * trackedValue, tilt: p.direction }} compact /><b className={`cc-allocation-legend-meta ${p.direction === 'short' ? 'negative' : p.direction === 'long' ? 'positive' : ''}`}>{allocationDirection} {allocationPct}%</b></div>
  })}</div></div>
}
function ExposureBars({ signals, icons, assetDetails }: { signals: any[], icons: Record<string, string>, assetDetails: Record<string, AssetDetail> }) {
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
      <div className="cc-ex-name"><TokenLogo coin={r.coin} icons={icons} /><AssetName coin={r.coin} details={assetDetails} row={r} /><span>{longSharePct(l, sh)}</span></div>
      <div className="cc-ex-track" aria-label={`${displayToken(r.coin)} ${Math.round(longPct)}% long, ${Math.round(shortPct)}% short`}><div><i style={{ width: `${longPct}%` }} /><em style={{ width: `${shortPct}%` }} /></div></div>
      <small>{compactMoney(l)}</small><small>{compactMoney(sh)}</small>
    </div>
  })}</div>
}


function grossLeverage(openValue: any, accountValue: any) {
  const account = Number(accountValue || 0)
  const open = Number(openValue || 0)
  if (!Number.isFinite(account) || !Number.isFinite(open) || account <= 0 || open <= 0) return null
  return open / account
}
function leverageRead(v: number | null) {
  if (!v || !Number.isFinite(v)) return ''
  if (v < 1) return 'Defensive'
  if (v < 2) return 'Moderate'
  if (v < 4) return 'Aggressive'
  return 'Very aggressive'
}
function leverageText(v: number | null) {
  if (!v || !Number.isFinite(v)) return ''
  return `Gross leverage: ${v.toFixed(1)}x  |  ${leverageRead(v)}`
}

function formatDirectionalSignal(row: any) {
  const value = displaySignalValue(row)
  const strength = Math.abs(Math.round(value * 100))
  if (strength === 0) return 'Neutral'
  return `${strength}% ${value >= 0 ? 'Bullish' : 'Bearish'}`
}
function formatInsightDetail(x: any) {
  if (x?.type === 'top_signal') return formatDirectionalSignal(x?.row)
  return String(x?.detail || '').replace(/Signal\s+(-?\d+(?:\.\d+)?)/i, (_, raw) => {
    const value = Number(raw)
    const strength = Math.abs(Math.round(value * 100))
    if (!strength) return 'Neutral'
    return `${strength}% ${value >= 0 ? 'Bullish' : 'Bearish'}`
  })
}
function latestAllocationTs(targets: any[], signals: any[], summary: any) {
  const times = [
    ...(targets || []).map((t: any) => Number(t.ts_ms || t.created_at_ms || t.updated_at_ms || 0)),
    Number(summary?.latest_signal_ts_ms || 0),
    Number(summary?.latest_position_ts_ms || 0),
    ...(signals || []).slice(0, 20).map((r: any) => Number(r.ts_ms || 0)),
  ].filter((n) => Number.isFinite(n) && n > 0)
  return times.length ? Math.max(...times) : 0
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
function alignPressureWithSignals(signalRows: any[], flowRows: any[]) {
  const exactFlow = new Map<string, any>()
  const canonicalFlow = new Map<string, any>()
  for (const row of flowRows || []) {
    const coin = String(row?.coin || '').trim()
    if (!coin) continue
    exactFlow.set(coin.toUpperCase(), row)
    canonicalFlow.set(canonicalToken(coin), row)
  }
  return (signalRows || [])
    .filter((row: any) => {
      const coin = String(row?.coin || '').trim()
      const longValue = Math.abs(Number(row?.value_long_usd || 0))
      const shortValue = Math.abs(Number(row?.value_short_usd || 0))
      return Boolean(coin) && longValue + shortValue > 0
    })
    .map((row: any) => {
      const coin = String(row?.coin || '').trim()
      const recent = exactFlow.get(coin.toUpperCase()) || canonicalFlow.get(canonicalToken(coin)) || {}
      const bullish = Number(recent?.bullish_flow_usd || recent?.bullish_value_flow_usd || 0)
      const bearish = Number(recent?.bearish_flow_usd || recent?.bearish_value_flow_usd || 0)
      return {
        ...row,
        bullish_flow_usd: bullish,
        bearish_flow_usd: bearish,
        net_value_flow_usd: Number(recent?.net_value_flow_usd ?? (bullish - bearish)),
        net_buyer_count: Number(recent?.net_buyer_count || 0),
      }
    })
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
  if (key === 'pressure') return flowPressureScore(row)
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
    if (sort.key === 'conviction') {
      const av = signalConvictionParts(a)
      const bv = signalConvictionParts(b)
      const byConfidence = av.confidence - bv.confidence
      if (byConfidence !== 0) return byConfidence * dir
      const byStrength = av.strength - bv.strength
      if (Math.abs(byStrength) > 0.000001) return byStrength * dir
      const byWallets = av.wallets - bv.wallets
      if (byWallets !== 0) return byWallets * dir
      const byNet = av.net - bv.net
      if (Math.abs(byNet) > 0.01) return byNet * dir
      return (av.gross - bv.gross) * dir
    }
    const av = sorterValue(a, sort.key), bv = sorterValue(b, sort.key)
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
    return String(av).localeCompare(String(bv)) * dir
  })
}
function SortTh({ label, sortKey, sort, setSort }: { label: string, sortKey: string, sort: SortState, setSort: (s: SortState) => void }) {
  return <th><button className="cc-sort-head" onClick={() => setSort(nextSort(sort, sortKey))}>{label}<span>{sortArrow(sort, sortKey)}</span></button></th>
}

// COPYCAT_MARKET_NARRATIVE_CARD_V2_START
type MarketNarrativeStory = {
  source?: string
  badge?: string
  title?: string
  url?: string
  published_at_ms?: number
  sentiment?: 'bullish' | 'bearish' | 'neutral' | string
}

const MARKET_NARRATIVE_SOURCE_LOGOS: Record<string, string> = {
  'CoinDesk': 'https://www.coindesk.com/favicon.ico',
  'Cointelegraph': 'https://cointelegraph.com/favicon.ico',
  'Decrypt': 'https://decrypt.co/favicon.ico',
  'CryptoSlate': 'https://cryptoslate.com/favicon.ico',
  'SEC': 'https://www.sec.gov/favicon.ico',
  'Federal Reserve': 'https://www.federalreserve.gov/favicon.ico',
  'CFTC': 'https://www.cftc.gov/favicon.ico',
  'ECB': 'https://www.ecb.europa.eu/favicon.ico',
  'BIS': 'https://www.bis.org/favicon.ico',
  'FCA': 'https://www.fca.org.uk/favicon.ico',
  'Ethereum Foundation': 'https://blog.ethereum.org/favicon.ico',
  'Kraken': 'https://www.kraken.com/favicon.ico',

  'Aave Governance': 'https://aave.com/favicon.ico',
  'Uniswap Governance': 'https://uniswap.org/favicon.ico',
  'Arbitrum Governance': 'https://arbitrum.io/favicon.ico',
  'Optimism Governance': 'https://www.optimism.io/favicon.ico',
  'Lido Research': 'https://lido.fi/favicon.ico',
  'Coinbase Status': 'https://status.coinbase.com/favicon.ico',
  'Kraken Status': 'https://status.kraken.com/favicon.ico',
  'Solana Status': 'https://status.solana.com/favicon.ico',
}

// COPYCAT_SOURCE_LOGOS_V3_START
const COPYCAT_SOURCE_LOGO_DOMAINS: Array<[string, string]> = [
  ['coindesk', 'coindesk.com'],
  ['cointelegraph', 'cointelegraph.com'],
  ['decrypt', 'decrypt.co'],
  ['cryptoslate', 'cryptoslate.com'],
  ['aave governance', 'governance.aave.com'],
  ['uniswap governance', 'gov.uniswap.org'],
  ['arbitrum governance', 'forum.arbitrum.foundation'],
  ['optimism governance', 'gov.optimism.io'],
  ['lido research', 'research.lido.fi'],
  ['lido governance', 'snapshot.org'],
  ['coinbase status', 'status.coinbase.com'],
  ['coinbase', 'coinbase.com'],
  ['kraken status', 'status.kraken.com'],
  ['kraken', 'kraken.com'],
  ['solana status', 'status.solana.com'],
  ['solana', 'solana.com'],
  ['ethereum foundation', 'ethereum.org'],
  ['federal reserve', 'federalreserve.gov'],
  ['u.s. bureau of labor statistics', 'bls.gov'],
  ['bureau of labor statistics', 'bls.gov'],
  ['sec', 'sec.gov'],
  ['cftc', 'cftc.gov'],
  ['ecb', 'ecb.europa.eu'],
  ['bis', 'bis.org'],
  ['fca', 'fca.org.uk'],
  ['ens governance', 'ens.domains'],
  ['balancer governance', 'balancer.fi'],
  ['safe governance', 'safe.global'],
  ['stargate governance', 'stargate.finance'],
  ['frax governance', 'frax.finance'],
  ['curve governance', 'curve.finance'],
  ['compound governance', 'compound.finance'],
  ['rocket pool governance', 'rocketpool.net'],
  ['sushi governance', 'sushi.com'],
  ['pancakeswap governance', 'pancakeswap.finance'],
  ['apecoin governance', 'apecoin.com'],
  ['gitcoin governance', 'gitcoin.co'],
  ['hop governance', 'hop.exchange'],
]

function copycatSourceLogoDomain(source: string) {
  const normalised = String(source || '').trim().toLowerCase()
  const match = COPYCAT_SOURCE_LOGO_DOMAINS.find(([needle]) => normalised.includes(needle))
  return match?.[1] || ''
}

function copycatSourceLogoCandidates(source: string) {
  const domain = copycatSourceLogoDomain(source)
  if (!domain) return [] as string[]
  return [
    `https://${domain}/favicon.ico`,
    `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`,
  ]
}

function CopycatSourceMark({
  source,
  badge,
  variant,
}: {
  source: string
  badge: string
  variant: 'market' | 'catalyst'
}) {
  const candidates = copycatSourceLogoCandidates(source)
  const [candidateIndex, setCandidateIndex] = useState(0)
  const logoUrl = candidates[candidateIndex] || ''
  const shellClass = variant === 'catalyst'
    ? 'cc-catalyst-source-logo-shell'
    : 'cc-market-news-logo-shell'
  const imageClass = variant === 'catalyst'
    ? 'cc-catalyst-source-logo'
    : 'cc-market-news-logo'
  const fallbackClass = variant === 'catalyst'
    ? 'cc-catalyst-badge'
    : 'cc-market-news-badge'

  if (!logoUrl) {
    return <span className={fallbackClass} aria-hidden>{badge}</span>
  }

  return <span className={shellClass} aria-hidden>
    <img
      src={logoUrl}
      alt=""
      className={imageClass}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setCandidateIndex((current) => current + 1)}
    />
  </span>
}
// COPYCAT_SOURCE_LOGOS_V3_END

function marketNarrativeAge(value: any) {
  const timestamp = Number(value || 0)
  if (!timestamp) return 'recently'
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function MarketNarrativeSourceMark({ source, badge }: { source: string; badge: string }) {
  const logoUrl = MARKET_NARRATIVE_SOURCE_LOGOS[source] || ''
  const [failed, setFailed] = useState(false)

  if (!logoUrl || failed) {
    return <span className="cc-market-news-badge" aria-hidden>{badge}</span>
  }

  return <span className="cc-market-news-logo-shell" aria-hidden>
    <img
      src={logoUrl}
      alt=""
      className="cc-market-news-logo"
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  </span>
}

function contextCheckedNewsSentiment(story: MarketNarrativeStory) {
  const supplied = String(story?.sentiment || 'neutral').toLowerCase()
  const title = String(story?.title || '').toLowerCase()

  const bearishContext = [
    /\b(?:cannot|can't|fails?|failed|struggles?)\s+(?:to\s+)?(?:break|clear|hold|reclaim)\b/i,
    /\b(?:roadblock|resistance|rejection|sell-?off|liquidations?|outage|exploit|breach)\b/i,
    /\bchok(?:e|ed|es|ing)\b.*\brall(?:y|ies)\b/i,
    /\b(?:dump(?:s|ed|ing)?|plunge(?:s|d)?|slide(?:s|d)?|drop(?:s|ped)?|crash(?:es|ed)?)\b/i,
    /\b(?:hack(?:ed|s|ing)?|withdrawals? paused|delayed sends|delayed receives)\b/i,
  ]
  if (bearishContext.some((pattern) => pattern.test(title))) return 'bearish'

  const bullishContext = [
    /\b(?:breaks?|broke) above\b/i,
    /\b(?:clears?|cleared) resistance\b/i,
    /\b(?:reclaims?|reclaimed|back above)\b/i,
    /\b(?:surges?|surged|rallies|rallied|accumulat(?:es|ed|ing)|inflows?|buying)\b/i,
  ]
  if (bullishContext.some((pattern) => pattern.test(title))) return 'bullish'

  return supplied === 'bullish' || supplied === 'bearish' ? supplied : 'neutral'
}

function MarketNarrativeCard({ narrative }: { narrative?: any }) {
  const stories: MarketNarrativeStory[] = Array.isArray(narrative?.stories)
    ? narrative.stories.slice(0, 5)
    : []

  if (!stories.length) return null

  return <section className="cc-card cc-market-narrative-card" aria-labelledby="cc-market-narrative-title">
    <div className="cc-market-narrative-head">
      <div>
        <p className="eyebrow live">Live market context</p>
        <h3 id="cc-market-narrative-title">News</h3>
      </div>
      <span suppressHydrationWarning>Updated {marketNarrativeAge(narrative?.updated_at_ms)}</span>
    </div>
    <div className="cc-market-news-list">
      {stories.map((story, index) => {
        const sentiment = contextCheckedNewsSentiment(story)
        const source = String(story?.source || 'Source')
        const badge = String(story?.badge || source.slice(0, 2)).slice(0, 4).toUpperCase()
        return <a
          className="cc-market-news-row"
          href={String(story?.url || '#')}
          target="_blank"
          rel="noopener noreferrer"
          key={`${story?.url || story?.title || index}-${index}`}
          title={String(story?.title || '')}
        >
          <CopycatSourceMark source={source} badge={badge} variant="market" />
          <span className="cc-market-news-source">{source}</span>
          <span className="cc-market-news-title">{story?.title || 'Market update'}</span>
          <span className={`cc-market-news-sentiment ${sentiment}`}>{sentiment}</span>
        </a>
      })}
    </div>
    <small className="cc-market-narrative-note">Context-checked headline lean; informational only. Headlines link to the original publishers.</small>
  </section>
}
// COPYCAT_MARKET_NARRATIVE_CARD_V2_END

// COPYCAT_CATALYST_WATCH_V1_START
type CatalystWatchEvent = {
  source?: string
  badge?: string
  asset?: string
  title?: string
  url?: string
  event_at_ms?: number
  impact?: 'HIGH' | 'MEDIUM' | 'LOW' | string
}

function catalystWatchDate(value: any) {
  const timestamp = Number(value || 0)
  if (!timestamp) return 'TBC'
  try {
    return new Intl.DateTimeFormat(undefined, {
      day: '2-digit',
      month: 'short',
      timeZone: 'UTC',
    }).format(new Date(timestamp)).toUpperCase()
  } catch {
    return 'TBC'
  }
}

function CatalystWatchCard({ watch }: { watch?: any }) {
  const events: CatalystWatchEvent[] = Array.isArray(watch?.events)
    ? watch.events.slice(0, 3)
    : []

  return <section className="cc-card cc-catalyst-watch-card" aria-labelledby="cc-catalyst-watch-title">
    <div className="cc-catalyst-watch-head">
      <div>
        <p className="eyebrow live">Crypto-first events</p>
        <h3 id="cc-catalyst-watch-title">Upcoming Events</h3>
      </div>
      <span suppressHydrationWarning>{watch?.updated_at_ms ? `Updated ${marketNarrativeAge(watch.updated_at_ms)}` : 'Official sources'}</span>
    </div>
    <div className="cc-catalyst-list">
      {events.length ? events.map((event, index) => {
        const impact = String(event?.impact || 'MEDIUM').toLowerCase()
        const badge = String(event?.badge || event?.asset || 'EVENT').slice(0, 5).toUpperCase()
        return <a
          className="cc-catalyst-row"
          href={String(event?.url || '#')}
          target="_blank"
          rel="noopener noreferrer"
          key={`${event?.url || event?.title || index}-${index}`}
          title={`${event?.source || 'Official source'} — ${event?.title || 'Upcoming event'}`}
        >
          <time dateTime={new Date(Number(event?.event_at_ms || 0)).toISOString()}>
            {catalystWatchDate(event?.event_at_ms)}
          </time>
          <CopycatSourceMark source={String(event?.source || event?.asset || "")} badge={badge} variant="catalyst" />
          <span className="cc-catalyst-title">{event?.title || 'Upcoming market event'}</span>
          <span className={`cc-catalyst-impact ${impact}`}>{impact}</span>
        </a>
      }) : <div className="cc-catalyst-empty">Collecting verified upcoming dates…</div>}
    </div>
    <small className="cc-catalyst-note">{watch?.note || 'Crypto-first official dates; maximum one macro event.'}</small>
  </section>
}
// COPYCAT_CATALYST_WATCH_V1_END




function SignalFlowMap({ rows, icons, details }: { rows: any[]; icons: Record<string, string>; details: Record<string, AssetDetail> }) {
  const plotRef = useRef<HTMLDivElement>(null)
  const [plotSize, setPlotSize] = useState({ width: 500, height: 310 })
  useEffect(() => {
    const node = plotRef.current
    if (!node) return
    const observer = new ResizeObserver(([entry]) => setPlotSize({ width: entry.contentRect.width, height: entry.contentRect.height }))
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  const candidates = [...(rows || [])]
    .filter((row: any) => row?.coin)
    .sort((a: any, b: any) => {
      const aGross = Number(a?.value_long_usd || 0) + Number(a?.value_short_usd || 0)
      const bGross = Number(b?.value_long_usd || 0) + Number(b?.value_short_usd || 0)
      const flowDifference = flowPressureScore(b) - flowPressureScore(a)
      return flowDifference || (bGross - aGross)
    })
    .slice(0, 6)
  const maxFlow = Math.max(1, ...candidates.map((row: any) => Math.abs(Number(row?.net_value_flow_usd || 0))))
  const maxGross = Math.max(1, ...candidates.map((row: any) => Number(row?.value_long_usd || 0) + Number(row?.value_short_usd || 0)))
  const placed: Array<{ left: number; top: number; size: number }> = []
  const bubbleLayout = candidates.map((row: any, index: number) => {
    const signal = Math.max(-1, Math.min(1, displaySignalValue(row)))
    const flowValue = Number(row?.net_value_flow_usd || 0)
    const gross = Number(row?.value_long_usd || 0) + Number(row?.value_short_usd || 0)
    const flowStrength = flowValue ? Math.sign(flowValue) * (Math.log1p(Math.abs(flowValue)) / Math.log1p(maxFlow)) : 0
    const baseLeft = 50 + signal * 38
    const baseTop = flowValue ? 50 - flowStrength * 36 : 50 + ((index % 3) - 1) * 9
    const size = 32 + Math.sqrt(Math.max(0, gross) / maxGross) * 34
    const xBounds: [number, number] = signal < -.02 ? [10, 46] : signal > .02 ? [54, 90] : [45, 55]
    const yBounds: [number, number] = flowValue < 0 ? [54, 88] : flowValue > 0 ? [12, 46] : [43, 57]
    const clamp = (value: number, bounds: [number, number]) => Math.max(bounds[0], Math.min(bounds[1], value))
    const offsets = [[0, 0], [12, 0], [-12, 0], [0, -18], [0, 18], [12, -18], [-12, 18], [12, 18], [-12, -18], [22, 0], [-22, 0], [22, -18], [-22, 18], [0, -30], [0, 30]]
    let best = { left: clamp(baseLeft, xBounds), top: clamp(baseTop, yBounds), score: -Infinity }
    for (const [offsetX, offsetY] of offsets) {
      const left = clamp(baseLeft + offsetX, xBounds)
      const top = clamp(baseTop + offsetY, yBounds)
      const score = placed.length ? Math.min(...placed.map((prior) => {
        const distance = Math.hypot((left - prior.left) * plotSize.width / 100, (top - prior.top) * plotSize.height / 100)
        return distance - ((size + prior.size) / 2 + 14)
      })) : 999
      if (score > best.score) best = { left, top, score }
      if (score >= 0) break
    }
    placed.push({ left: best.left, top: best.top, size })
    return { row, index, signal, flowValue, gross, size, left: best.left, top: best.top }
  })

  return <section className="cc-card cc-signal-flow-card">
    <div className="cc-panel-title cc-signal-flow-head">
      <div>
        <h3>Signal × Flow</h3>
        <span>Where top wallets are positioned vs what they are doing now</span>
      </div>
      <span className="cc-bubble-key">Bubble size = tracked exposure <i aria-hidden>i</i></span>
    </div>
    <div className="cc-signal-flow-stage">
      <div ref={plotRef} className="cc-signal-flow-plot" role="img" aria-label="Asset signal and recent flow map">
        <i className="cc-signal-flow-axis-x" aria-hidden />
        <i className="cc-signal-flow-axis-y" aria-hidden />
        <span className="cc-axis-title y-positive">Buying now</span>
        <span className="cc-axis-title y-negative">Selling now</span>
        <span className="cc-axis-title x-negative">Short positioning</span>
        <span className="cc-axis-title x-neutral">Neutral</span>
        <span className="cc-axis-title x-positive">Long positioning</span>
        <span className="cc-quadrant-note q-tl"><b>↻</b> Shorts being covered<br/>possible reversal</span>
        <span className="cc-quadrant-note q-tr"><b>↗</b> Bullish continuation</span>
        <span className="cc-quadrant-note q-bl"><b>↘</b> Bearish continuation</span>
        <span className="cc-quadrant-note q-br"><b>↘</b> Longs reducing<br/>possible weakness</span>
        {[-100, -50, 0, 50, 100].map((tick) => <span className="cc-axis-tick x" style={{ left: `${50 + tick * .39}%` }} key={`x-${tick}`}>{tick}%</span>)}
        {[100, 50, 0, -50, -100].map((tick) => <span className="cc-axis-tick y" style={{ top: `${50 - tick * .37}%` }} key={`y-${tick}`}>{tick}%</span>)}
        {bubbleLayout.map(({ row, index, signal, flowValue, size, left, top }) => {
          return <span
            key={String(row.coin)}
            className={`cc-flow-bubble ${signal < 0 ? 'negative' : 'positive'} ${left > 72 || (left > 28 && index % 2 === 1) ? 'label-left' : ''}`}
            data-coin={displayToken(row.coin)}
            
            style={{ left: `${left}%`, top: `${top}%`, ['--bubble-size' as any]: `${size}px`, ['--bubble-colour' as any]: tokenColour(row.coin, index) }}
          >
            <span className="cc-flow-bubble-core"><AssetName coin={row.coin} details={details} row={row}><TokenLogo coin={row.coin} icons={icons} /></AssetName></span>
            <b>{displayToken(row.coin)}</b>
          </span>
        })}
      </div>
    </div>
  </section>
}

function PositioningChanges({ rows, icons, details, windowLabel }: { rows: any[]; icons: Record<string, string>; details: Record<string, AssetDetail>; windowLabel: string }) {
  const leaders = [...(rows || [])]
    .filter((row: any) => row?.coin)
    .sort((a: any, b: any) => Math.abs(Number(b?.net_value_flow_usd || 0)) - Math.abs(Number(a?.net_value_flow_usd || 0)))
    .slice(0, 5)

  return <section className="cc-card cc-positioning-card">
    <div className="cc-panel-title"><h3>Positioning Changes</h3><span>{windowLabel}</span></div>
    <div className="cc-positioning-list">
      {leaders.length ? leaders.map((row: any) => {
        const netFlow = Number(row?.net_value_flow_usd || 0)
        const buyers = Number(row?.net_buyer_count || 0)
        return <div className="cc-positioning-row" key={String(row.coin)}>
          <span className="cc-asset-cell"><TokenLogo coin={row.coin} icons={icons} /><AssetName coin={row.coin} details={details} row={row} /></span>
          <span>{flowRead(netFlow)} · {Math.abs(buyers)} net {buyers >= 0 ? 'buyers' : 'sellers'}</span>
          <b className={cls(netFlow)}>{compactMoney(netFlow)}</b>
        </div>
      }) : <p className="cc-catalyst-empty">Collecting the latest positioning changes…</p>}
    </div>
  </section>
}

type QuickChartWindow = '24H' | '7D' | '30D'
type PriceCandle = { ts_ms: number; price: number }

function quickChartWindowMs(windowKey: QuickChartWindow) {
  if (windowKey === '7D') return 7 * 24 * 60 * 60 * 1000
  if (windowKey === '30D') return 30 * 24 * 60 * 60 * 1000
  return 24 * 60 * 60 * 1000
}

function quickChartInterval(windowKey: QuickChartWindow) {
  if (windowKey === '30D') return '4h'
  if (windowKey === '7D') return '1h'
  return '15m'
}

function chartPath(points: Array<{ ts_ms: number; position?: number; price?: number }>, key: 'position' | 'price', minimum: number, span: number, start: number, end: number) {
  return points.map((row, index) => {
    const x = ((row.ts_ms - start) / Math.max(1, end - start)) * 760
    const y = 250 - ((Number(row[key]) - minimum) / span) * 250
    const continuous = index > 0 && (key !== 'position' || row.ts_ms - points[index - 1].ts_ms <= 10 * 60000)
    return `${continuous ? 'L' : 'M'} ${x.toFixed(2)} ${y.toFixed(2)}`
  }).join(' ')
}

function chartTimeLabel(timestamp: number, windowKey: QuickChartWindow) {
  const date = new Date(timestamp)
  if (windowKey === '24H') return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return date.toLocaleDateString([], { day: '2-digit', month: 'short' })
}

function PricePositioningChart({ icons, signals, details }: { icons: Record<string, string>; signals: any[]; details: Record<string, AssetDetail> }) {
  const [windowKey, setWindowKey] = useState<QuickChartWindow>('24H')
  const [asset, setAsset] = useState('BTC')
  const [liveCandles, setLiveCandles] = useState<PriceCandle[]>([])
  const [priceLoading, setPriceLoading] = useState(false)
  const [history, setHistory] = useState<PositionFrame[]>([])
  const [historyState, setHistoryState] = useState<'loading' | 'ready' | 'unavailable'>('loading')
  const [refresh, setRefresh] = useState(0)

  const assetOptions = useMemo(() => {
    const seen = new Set<string>()
    return [...(signals || [])]
      .filter((row: any) => row?.coin && Number(row?.value_long_usd || 0) + Number(row?.value_short_usd || 0) > 0)
      .sort((a: any, b: any) => (Number(b?.value_long_usd || 0) + Number(b?.value_short_usd || 0)) - (Number(a?.value_long_usd || 0) + Number(a?.value_short_usd || 0)))
      .filter((row: any) => {
        const key = canonicalToken(String(row.coin))
        if (!key || seen.has(key)) return false
        seen.add(key)
        return true
      })
      .map((row: any) => String(row.coin))
  }, [signals])

  useEffect(() => {
    if (!assetOptions.length) return
    if (!assetOptions.some((coin) => canonicalToken(coin) === canonicalToken(asset))) {
      const preferred = assetOptions.find((coin) => canonicalToken(coin) === 'BTC') || assetOptions[0]
      setAsset(preferred)
    }
  }, [assetOptions, asset])

  useEffect(() => {
    let alive = true
    const controller = new AbortController()
    const load = async () => {
      try {
        const frames = await loadPositionHistory(quickChartWindowMs(windowKey), controller.signal)
        if (alive) { setHistory(frames); setHistoryState('ready') }
      } catch { if (alive) setHistoryState('unavailable') }
    }
    setHistoryState('loading')
    load()
    const timer = window.setInterval(() => { load(); setRefresh((value) => value + 1) }, COPYCAT_FEED_POLL_MS)
    return () => { alive = false; controller.abort(); window.clearInterval(timer) }
  }, [windowKey])

  useEffect(() => {
    if (!asset) return
    let alive = true
    const controller = new AbortController()
    const now = Date.now()
    setPriceLoading(true)
    setLiveCandles([])
    fetch('https://api.hyperliquid.xyz/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'candleSnapshot',
        req: { coin: asset, interval: quickChartInterval(windowKey), startTime: now - quickChartWindowMs(windowKey), endTime: now },
      }),
      signal: controller.signal,
    })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('price history unavailable')))
      .then((rows: any[]) => {
        if (!alive) return
        const candles = (Array.isArray(rows) ? rows : [])
          .map((row: any) => ({ ts_ms: Number(row?.t || row?.T || row?.ts_ms || 0), price: Number(row?.c || row?.close || 0) }))
          .filter((row: PriceCandle) => row.ts_ms > 0 && row.price > 0)
          .sort((a: PriceCandle, b: PriceCandle) => a.ts_ms - b.ts_ms)
        setLiveCandles(candles)
      })
      .catch(() => { if (alive) setLiveCandles([]) })
      .finally(() => { if (alive) setPriceLoading(false) })
    return () => { alive = false; controller.abort() }
  }, [asset, windowKey, refresh])

  const selectedSignal = useMemo(() => (signals || []).find((row: any) => canonicalToken(String(row?.coin || '')) === canonicalToken(asset)) || null, [signals, asset])
  const currentNet = Number(selectedSignal?.net_value_usd ?? (Number(selectedSignal?.value_long_usd || 0) - Number(selectedSignal?.value_short_usd || 0)))
  const observedAt = Number(selectedSignal?.ts_ms || 0)
  const requestedEnd = Date.now()
  const requestedStart = requestedEnd - quickChartWindowMs(windowKey)
  const recorded = assetHistory(history, asset, requestedStart, requestedEnd)
  const positions = new Map(recorded.map((point) => [point.ts_ms, point]))
  const currentPrice = Number(selectedSignal?.price_usd || details?.[canonicalToken(asset)]?.current_price || 0)
  if (observedAt >= requestedStart && observedAt <= requestedEnd && Number.isFinite(currentNet)) {
    positions.set(observedAt, { ts_ms: observedAt, position: currentNet, ...(currentPrice > 0 ? { price: currentPrice } : {}) })
  }
  const positionPoints: PositionSample[] = [...positions.values()].sort((a, b) => a.ts_ms - b.ts_ms)
  const firstRecorded = positionPoints[0]?.ts_ms
  const lastRecorded = positionPoints[positionPoints.length - 1]?.ts_ms
  const hasHistory = positionPoints.length >= 2 && lastRecorded > firstRecorded
  // Until the archive fills the selected window, show the real shared interval
  // at a readable scale, explicitly labelled as partial coverage.
  const chartStart = hasHistory ? Math.max(requestedStart, firstRecorded) : requestedStart
  const chartEnd = hasHistory ? lastRecorded : requestedEnd
  const partialHistory = hasHistory && chartStart > requestedStart + 10 * 60000
  const archivedPrices = positionPoints.filter((point) => point.price && point.price > 0).map((point) => ({ ts_ms: point.ts_ms, price: point.price! }))
  const prices = new Map(liveCandles.filter((point) => point.ts_ms >= chartStart && point.ts_ms <= chartEnd).map((point) => [point.ts_ms, point]))
  for (const point of archivedPrices) prices.set(point.ts_ms, point)
  const points = [...prices.values()].sort((a, b) => a.ts_ms - b.ts_ms)
  const positionValues = positionPoints.map((row) => row.position).filter(Number.isFinite)
  const priceValues = points.map((row) => row.price).filter(Number.isFinite)
  const positionRawMin = positionValues.length ? Math.min(...positionValues) : -1
  const positionRawMax = positionValues.length ? Math.max(...positionValues) : 1
  const positionPadding = Math.max(1, Math.abs(positionRawMax - positionRawMin) * .14, Math.abs(currentNet) * .035)
  const positionMin = positionRawMin - positionPadding
  const positionMax = positionRawMax + positionPadding
  const priceRawMin = priceValues.length ? Math.min(...priceValues) : 0
  const priceRawMax = priceValues.length ? Math.max(...priceValues) : 1
  const pricePadding = Math.max(.000001, (priceRawMax - priceRawMin) * .1)
  const priceMin = Math.max(0, priceRawMin - pricePadding)
  const priceMax = priceRawMax + pricePadding
  const positionPath = positionChartPath(positionPoints, positionMin, positionMax - positionMin, chartStart, chartEnd)
  const pricePath = chartPath(points, 'price', priceMin, Math.max(.000001, priceMax - priceMin), chartStart, chartEnd)

  const first = points[0]
  const last = points[points.length - 1]
  const positionMove = positionPoints.length >= 2 ? positionPoints[positionPoints.length - 1].position - positionPoints[0].position : 0
  const priceMove = first?.price ? ((Number(last?.price || 0) / Number(first.price)) - 1) * 100 : 0
  const divergence = hasHistory && !partialHistory && points.length >= 2 && first.ts_ms <= chartStart + 60000 && Math.abs(positionMove) > Math.max(1, Math.abs(currentNet) * .01) && Math.abs(priceMove) >= .15 && Math.sign(positionMove) !== Math.sign(priceMove)
  const timeTicks = [0, .25, .5, .75, 1].map((ratio) => chartStart + (chartEnd - chartStart) * ratio)
  const coverageLabel = hasHistory ? `${partialHistory ? 'Available history' : 'Recorded history'}: ${new Date(chartStart).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} – ${new Date(chartEnd).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}${partialHistory ? ` · ${windowKey} still building` : ''}` : historyState === 'loading' ? 'Loading recorded wallet positions…' : historyState === 'unavailable' ? 'Position archive temporarily unavailable · latest observed position shown' : 'Recording wallet positions automatically · first observation shown'

  return <section className="cc-card cc-price-positioning-card">
    <div className="cc-panel-title cc-price-chart-head">
      <div className="cc-price-title-group"><h3>Price vs Smart-Wallet Positioning</h3><label className="cc-asset-select">
        <TokenLogo coin={asset} icons={icons} />
        <select value={asset} onChange={(event) => setAsset(event.target.value)} aria-label="Select asset">
          {assetOptions.map((coin) => <option value={coin} key={coin}>{displayToken(coin)}</option>)}
        </select>
      </label></div>
      <div className="cc-chart-window-tabs" aria-label="Chart timeframe">
        {(['24H', '7D', '30D'] as QuickChartWindow[]).map((key) => <button type="button" className={windowKey === key ? 'active' : ''} onClick={() => setWindowKey(key)} key={key}>{key}</button>)}
      </div>
    </div>
    <div className="cc-price-control-row">
      
      {divergence ? <div className="cc-divergence-callout"><b>Divergence detected</b><span>{positionMove > 0 ? 'Top wallets building longs' : 'Top wallets reducing exposure'} while price {priceMove >= 0 ? 'rises' : 'falls'}</span></div> : <span className="cc-chart-observation">{coverageLabel}</span>}
    </div>
    <div className="cc-chart-legend">
      <span><i className="model" />Top 50 wallet net position <b className={cls(currentNet)}>{compactMoney(currentNet)}</b></span>
      <span><i className="price" />{displayToken(asset)} price <b>{points.length ? priceText(points[points.length - 1]?.price) : '—'}</b></span>
    </div>
    <div className="cc-price-chart-frame">
      <div className="cc-y-axis cc-y-axis-left"><span>{positionPoints.length ? compactMoney(positionMax) : '—'}</span><span>{positionPoints.length ? compactMoney((positionMax + positionMin) / 2) : '—'}</span><span>{positionPoints.length ? compactMoney(positionMin) : '—'}</span></div>
      <div className="cc-y-axis-title left">Net position (USD)</div>
      <div className="cc-price-line-chart">
        {points.length >= 2 || positionPoints.length ? <svg viewBox="0 0 760 250" preserveAspectRatio="none" role="img" aria-label={'Recorded top 50 wallet net position and ' + displayToken(asset) + ' price. ' + coverageLabel}>
          <defs>
            <linearGradient id="ccPositionArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#36e8aa" stopOpacity=".2" /><stop offset="1" stopColor="#36e8aa" stopOpacity="0" /></linearGradient>
          </defs>
          {positionPoints.length >= 2 ? <path className="cc-model-line" d={positionPath} /> : null}
          {points.length >= 2 ? <path className="cc-price-line" d={pricePath} /> : null}
          {positionPoints.map((point) => <circle key={point.ts_ms} className="cc-position-observation-dot" cx={Math.max(3, Math.min(757, (point.ts_ms - chartStart) / Math.max(1, chartEnd - chartStart) * 760))} cy={250 - (point.position - positionMin) / Math.max(1, positionMax - positionMin) * 250} r={positionPoints.length < 3 ? 3 : 1.5}><title>{new Date(point.ts_ms).toLocaleString()}: {money(point.position)}</title></circle>)}
        </svg> : <div className="cc-chart-empty">{priceLoading ? 'Loading ' + displayToken(asset) + ' price history…' : 'Price history is not available for ' + displayToken(asset) + ' yet.'}</div>}
      </div>
      <div className="cc-y-axis cc-y-axis-right"><span>{priceText(priceMax)}</span><span>{priceText((priceMax + priceMin) / 2)}</span><span>{priceText(priceMin)}</span></div>
      <div className="cc-y-axis-title right">Price (USD)</div>
    </div>
    {timeTicks.length ? <div className="cc-chart-time-axis">{timeTicks.map((timestamp, index) => <span key={String(timestamp) + '-' + index}>{chartTimeLabel(timestamp, windowKey)}</span>)}</div> : null}
  </section>
}
export default function Dashboard() {
  const [summary, setSummary] = useState<any>({})
  const [signals, setSignals] = useState<any[]>([])
  const [targets, setTargets] = useState<any[]>([])
  const [flow, setFlow] = useState<any[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const [stagedOrders, setStagedOrders] = useState<any[]>([])
  const [insights, setInsights] = useState<any[]>([])
  const [audit, setAudit] = useState<any>(null)
  const [showAllOrders, setShowAllOrders] = useState(false)
  const [icons, setIcons] = useState<Record<string, string>>({})
  const [assetDetails, setAssetDetails] = useState<Record<string, AssetDetail>>({})
  const [err, setErr] = useState('')
  const [signalSort, setSignalSort] = useState<SortState>({ key: 'conviction', dir: 'desc' })
  const [flowSortState, setFlowSortState] = useState<SortState>({ key: 'pressure', dir: 'desc' })

  const fullInFlight = useRef(false)
  const tickInFlight = useRef(false)
  const failureCount = useRef(0)
  const hasLoaded = useRef(false)
  const stagedOrderKeys = useRef<Set<string>>(new Set())
  const orderStageTimers = useRef<number[]>([])
  const ordersInitialised = useRef(false)

  function applyLiveTick(feed: any) {
    if (feed.summary) setSummary((prev: any) => ({ ...prev, ...feed.summary }))
    if (Array.isArray(feed.orders)) setOrders(feed.orders)
  }

  const [marketNarrative, setMarketNarrative] = useState<any>(null)
  const [catalystWatch, setCatalystWatch] = useState<any>(null)
  async function loadFull() {
    // The full payload contains the large tables and chart inputs. It should
    // load on first paint and then refresh in the background, not every second.
    if (fullInFlight.current) return
    fullInFlight.current = true
    try {
      const feed = await apiGet('/api/dashboard-feed', { timeoutMs: 20000 })
      failureCount.current = 0
      hasLoaded.current = true
      setErr('')
      setSummary(feed.summary || {})
      setSignals(feed.signals || [])
      setTargets(feed.targets || [])
      setFlow(feed.flow || [])
      setOrders(feed.orders || [])
      setInsights(feed.insights || [])
      setAudit(feed.audit || null)
      setMarketNarrative(feed.market_narrative || null)
      setCatalystWatch(feed.catalyst_watch || null)
    } catch (e: any) {
      failureCount.current += 1
      if (!hasLoaded.current && failureCount.current >= 3) {
        setErr('Live data connection interrupted. Retrying…')
      }
    } finally {
      fullInFlight.current = false
    }
  }

  async function loadTick() {
    // Tiny 1s update: most recent orders + headline live numbers only.
    if (tickInFlight.current) return
    tickInFlight.current = true
    try {
      const tick = await apiGet('/api/dashboard-tick', { timeoutMs: 6000 })
      failureCount.current = 0
      hasLoaded.current = true
      setErr('')
      applyLiveTick(tick)
    } catch (e: any) {
      failureCount.current += 1
      if (!hasLoaded.current && failureCount.current >= 3) {
        setErr('Live data connection interrupted. Retrying…')
      }
    } finally {
      tickInFlight.current = false
    }
  }

  useEffect(() => {
    window.history.scrollRestoration = 'manual'
    window.scrollTo(0, 0)
    // Paint the live tape/headline values first, then hydrate the heavier
    // tables. This prevents the whole dashboard feeling blocked by the full
    // feed, token icons, or the performance chart.
    loadTick()
    const bootTimer = window.setTimeout(loadFull, 80)
    const tickId = setInterval(loadTick, COPYCAT_TICK_POLL_MS)
    const fullId = setInterval(loadFull, 10000)
    return () => { clearTimeout(bootTimer); clearInterval(tickId); clearInterval(fullId) }
  }, [])

  const symbolKey = useMemo(() => Array.from(new Set([...signals.map(r => r.coin), ...targets.map(r => r.coin), ...flow.map(r => r.coin), ...orders.map((r: any) => r.coin)].filter(Boolean).map(x => canonicalToken(String(x).toUpperCase())))).sort().join(','), [signals, targets, flow, orders])
  useEffect(() => {
    if (!symbolKey) return
    const cacheKey = 'copycat-token-icons:' + symbolKey
    try {
      const cached = localStorage.getItem(cacheKey)
      if (cached) setIcons(JSON.parse(cached))
    } catch {}
    const visibleSymbols = symbolKey
    const timer = window.setTimeout(() => {
      apiGet('/api/token-icons?limit=250&symbols=' + encodeURIComponent(visibleSymbols), { timeoutMs: 3500 }).then((r: any) => {
        const nextIcons = r.icons || {}
        setIcons(nextIcons)
        try { localStorage.setItem(cacheKey, JSON.stringify(nextIcons)) } catch {}
      }).catch(() => {})
    }, 1200)
    return () => clearTimeout(timer)
  }, [symbolKey])

  useEffect(() => {
    if (!symbolKey) return
    const cacheKey = 'copycat-asset-details:' + symbolKey
    try {
      const cached = localStorage.getItem(cacheKey)
      if (cached) setAssetDetails(JSON.parse(cached))
    } catch {}
    apiGet('/api/data/v1/public/asset-details?symbols=' + encodeURIComponent(symbolKey)).then((r: any) => {
      const next = r.assets || {}
      setAssetDetails(next)
      try { localStorage.setItem(cacheKey, JSON.stringify(next)) } catch {}
    }).catch(() => {})
  }, [symbolKey])

  const mergedAssetDetails = useMemo(() => {
    const out: Record<string, AssetDetail> = {}
    Object.entries(assetDetails || {}).forEach(([key, value]) => {
      const canonical = canonicalToken(key)
      if (canonical) out[canonical] = { ...(value || {}), coin: canonical }
    })

    const absorb = (row: any) => {
      const canonical = canonicalToken(row?.coin || '')
      if (!canonical) return
      const prev = out[canonical] || { coin: canonical, name: tokenFullName(canonical) }
      const longUsd = Number(row?.value_long_usd || prev.value_long_usd || 0)
      const shortUsd = Number(row?.value_short_usd || prev.value_short_usd || 0)
      const gross = Number(row?.gross_exposure_usd || row?.gross_value_usd || (longUsd + shortUsd) || prev.gross_exposure_usd || 0)
      const signalStrength = row?.signal !== undefined ? Math.abs(Number(displaySignalValue(row)) * 100) : 0
      out[canonical] = {
        ...prev,
        coin: canonical,
        name: row?.name || prev.name || tokenFullName(canonical),
        current_price: Number(row?.current_price || row?.mark_price || row?.price_usd || prev.current_price || (prev as any).price_usd || 0) || undefined,
        max_leverage: Number(row?.max_leverage || prev.max_leverage || 0) || undefined,
        tilt: prev.tilt || row?.tilt || (longUsd || shortUsd ? (longUsd >= shortUsd ? 'Long' : 'Short') : undefined),
        conviction_pct: Number(prev.conviction_pct || row?.conviction_pct || signalStrength || 0) || undefined,
        wallets_long: Number(row?.wallets_long ?? prev.wallets_long ?? 0),
        wallets_short: Number(row?.wallets_short ?? prev.wallets_short ?? 0),
        gross_exposure_usd: gross || prev.gross_exposure_usd,
        net_flow_usd: Number(row?.net_value_flow_usd || row?.net_flow_usd || prev.net_flow_usd || 0) || undefined,
        value_long_usd: longUsd || prev.value_long_usd,
        value_short_usd: shortUsd || prev.value_short_usd,
      }
    }

    ;[...(signals || []), ...(flow || []), ...(targets || []), ...(orders || [])].forEach(absorb)
    return out
  }, [assetDetails, signals, flow, targets, orders])

  const longValue = signals.reduce((a, r) => a + Number(r.value_long_usd || 0), 0)
  const shortValue = signals.reduce((a, r) => a + Number(r.value_short_usd || 0), 0)
  const isLong = longValue >= shortValue
  const dataHealthy = summary.data_quality_status === 'healthy'
  const claimReady = Boolean(summary.top_claim_ready)
  const indexedWallets = Number(summary.indexed_wallets || summary.known_wallet_candidates || summary.registry_wallets || summary.owned_wallets_indexed || summary.scanner_candidate_wallets_scored || 0)
  const suppliedRankingScope = String(summary.claim_label || summary.ranking_scope_label || '').trim()
  const rankingScope = indexedWallets > 0
    ? `Top ${summary.qualified_wallets || 0} Copycat-ranked wallets from ${indexedWallets.toLocaleString()} locally indexed Hyperliquid candidates`
    : suppliedRankingScope && !/\b0 indexed wallets\b/i.test(suppliedRankingScope)
      ? suppliedRankingScope
      : `Top ${summary.qualified_wallets || 0} Copycat-ranked wallets from our locally indexed Hyperliquid candidate universe`
  const liveCoverageText = `${summary.live_wallets || 0}/${summary.qualified_wallets || 0} live wallets`
  const auditStatus = audit?.status || 'checking'
  const grossLeverageValue = grossLeverage(summary.tracked_open_position_value_usd, summary.tracked_account_value_usd)
  const orderRows = orders.length ? orders : flow.slice(0, 12).map((r: any) => ({ coin: r.coin, side: Number(r.net_value_flow_usd) >= 0 ? 'Long' : 'Short', wallet_label: 'Wallet 0x1A…7F3B', wallet: r.wallet, ts_ms: summary.latest_signal_ts_ms }))
  const orderSignature = useMemo(() => orderRows.slice(0, 50).map(orderKey).join('|'), [orderRows])
  useEffect(() => {
    orderStageTimers.current.forEach((timer) => window.clearTimeout(timer))
    orderStageTimers.current = []
    const next = orderRows.slice(0, 50)
    const nextKeys = new Set(next.map(orderKey))
    const orderIndex = new Map<string, number>(next.map((o, i) => [orderKey(o), i] as [string, number]))

    // First paint must show the latest tape immediately. The satisfying
    // brick/stack animation is only for genuinely new fills after the page
    // is already live, not for replaying old orders from several minutes ago.
    if (!ordersInitialised.current) {
      ordersInitialised.current = true
      stagedOrderKeys.current = new Set(next.map(orderKey))
      setStagedOrders(next)
      return
    }

    setStagedOrders((prev) => {
      const kept = prev
        .filter((o) => nextKeys.has(orderKey(o)))
        .sort((a, b) => (orderIndex.get(orderKey(a)) ?? 9999) - (orderIndex.get(orderKey(b)) ?? 9999))
      stagedOrderKeys.current = new Set(kept.map(orderKey))
      return kept
    })
    const incoming = next.filter((o) => !stagedOrderKeys.current.has(orderKey(o))).reverse()
    incoming.forEach((order, i) => {
      const timer = window.setTimeout(() => {
        const key = orderKey(order)
        stagedOrderKeys.current.add(key)
        setStagedOrders((prev) => [order, ...prev.filter((p) => orderKey(p) !== key)]
          .filter((p) => nextKeys.has(orderKey(p)))
          .sort((a, b) => (orderIndex.get(orderKey(a)) ?? 9999) - (orderIndex.get(orderKey(b)) ?? 9999))
          .slice(0, 50))
      }, i * 420)
      orderStageTimers.current.push(timer)
    })
    return () => orderStageTimers.current.forEach((timer) => window.clearTimeout(timer))
  }, [orderSignature])
  const visibleOrders = showAllOrders ? stagedOrders : stagedOrders.slice(0, 3)
  const sortedSignals = sortedRows(signals, signalSort)
  const alignedFlow = useMemo(() => alignPressureWithSignals(signals, flow), [signals, flow])
  const sortedFlow = sortedRows(alignedFlow, flowSortState)
  const topCurrentExposure = useMemo(() => largestCurrentExposure(signals), [signals])
  const flowContextText = `${flowWindowText(summary)}  |  ${flowIntensityText(flow, summary.tracked_open_position_value_usd)}`

  const topConviction = [...signals].sort((a: any, b: any) => {
    const av = signalConvictionParts(a)
    const bv = signalConvictionParts(b)
    return (bv.confidence - av.confidence) || (bv.strength - av.strength) || (bv.wallets - av.wallets) || (bv.net - av.net) || (bv.gross - av.gross)
  })[0] || null
  const topFlow = [...alignedFlow].sort((a: any, b: any) => Math.abs(Number(b?.net_value_flow_usd || 0)) - Math.abs(Number(a?.net_value_flow_usd || 0)) || flowPressureScore(b) - flowPressureScore(a))[0] || null
  const openGross = longValue + shortValue
  const longShare = openGross > 0 ? (longValue / openGross) * 100 : 0
  return <div className="cc-dashboard-page">
    <PublicNav />
    <main className="cc-dashboard-shell">
      {err && <p className="notice gold">{err}</p>}

      <section className="cc-market-pulse" aria-label="Market pulse">
        <article>
          <span className="cc-pulse-label">Positioning bias</span>
          <div className="cc-pulse-main"><strong className={`cc-pulse-bias ${isLong ? 'positive' : 'negative'}`}><i aria-hidden />{isLong ? 'LONG' : 'SHORT'}</strong></div>
          <span className="cc-pulse-meta">{Math.round(longShare)}% long · {Math.round(100 - longShare)}% short · {compactMoney(longValue - shortValue)} net</span>
        </article>
        <article>
          <span className="cc-pulse-label">Largest exposure</span>
          {topCurrentExposure ? <><div className="cc-pulse-main"><TokenLogo coin={topCurrentExposure.coin} icons={icons} /><strong>{displayToken(topCurrentExposure.coin)} {topCurrentExposure.direction}</strong></div><span className="cc-pulse-meta">{compactMoney(topCurrentExposure.value)} current net exposure</span></> : <span className="cc-pulse-meta">Awaiting live exposure</span>}
        </article>
        <article>
          <span className="cc-pulse-label">Top conviction</span>
          {topConviction ? <><div className="cc-pulse-main"><TokenLogo coin={topConviction.coin} icons={icons} /><strong className={cls(displaySignalValue(topConviction))}>{displaySignalMagnitudePct(topConviction)} {displaySignalDirection(topConviction)}</strong></div><span className="cc-pulse-meta">{displayToken(topConviction.coin)} · {topConviction.wallets_long || 0} long / {topConviction.wallets_short || 0} short</span></> : <span className="cc-pulse-meta">Awaiting live signals</span>}
        </article>
        <article>
          <span className="cc-pulse-label">{flowWindowText(summary)}</span>
          {topFlow ? <><div className="cc-pulse-main"><TokenLogo coin={topFlow.coin} icons={icons} /><strong className={cls(topFlow.net_value_flow_usd)}>{flowRead(topFlow.net_value_flow_usd)}</strong></div><span className="cc-pulse-meta">{displayToken(topFlow.coin)} · {compactMoney(topFlow.net_value_flow_usd)} net flow</span></> : <span className="cc-pulse-meta">Awaiting recent flow</span>}
        </article>
        <article className="cc-pulse-orders">
          <span className="cc-pulse-label">Most recent orders</span>
          <div className="cc-order-list">
            {visibleOrders.slice(0, 3).map((o: any) => <div className="cc-order-line" key={orderKey(o)}><TokenLogo coin={o.coin} icons={icons} /><AssetName coin={o.coin} details={mergedAssetDetails} row={o} compact /><span className={orderActionClass(o.side)}>{o.side}</span><WalletExplorerLink wallet={o.wallet} label={o.wallet_label} /><small suppressHydrationWarning>{ago(o.ts_ms)}</small></div>)}
          </div>
        </article>
      </section>

      <section className="cc-kpi-grid cc-kpi-grid-tight">
        <article><small>Copycat-ranked wallets</small><RollingInteger value={summary.qualified_wallets || 0} /><span>{walletUniverseCaption(summary)}</span></article>
        <article className="cc-tracked-value-card"><small>Tracked wallet value</small><RollingMoney value={summary.tracked_total_wallet_value_usd ?? summary.tracked_account_value_usd} /><span>{Number(summary.wallets_with_complete_total_value || 0)}/{Number(summary.selected_wallet_count || summary.live_wallets || 50)} fully valued · same live cohort as API</span>{summary.tracked_account_value_usd ? <em>Perp equity: {money(summary.tracked_account_value_usd)}</em> : null}</article>
        <article className="cc-open-position-card"><small>Open position value</small><RollingMoney value={summary.tracked_open_position_value_usd} /><span>{summary.open_positions || 0} live positions</span>{grossLeverageValue ? <em>{leverageText(grossLeverageValue)}</em> : null}</article>
        <article><small>Assets with signals</small><RollingInteger value={summary.assets_with_signals || signals.length || 0} /><span>{summary.markets_monitored ? `${summary.markets_monitored} price markets available` : 'cross-asset breadth'}</span></article>
      </section>

      <section className="cc-dashboard-primary-grid">
        <SignalFlowMap rows={alignedFlow} icons={icons} details={mergedAssetDetails} />
        <div className="cc-card cc-allocation-card"><div className="cc-card-title-row"><h3>Portfolio allocation</h3><span>Rebalanced {fmtTime(latestAllocationTs(targets, signals, summary))} UTC</span></div><AllocationDonut targets={targets} signals={signals} trackedValue={Number(summary.tracked_account_value_usd || 0)} icons={icons} assetDetails={mergedAssetDetails} /></div>
        <div className="cc-card cc-exposure-card"><div className="cc-panel-title"><h3>Long vs short exposure</h3><span><i />Long <em />Short</span></div><ExposureBars signals={signals} icons={icons} assetDetails={mergedAssetDetails} /></div>
        <PositioningChanges rows={alignedFlow} icons={icons} details={mergedAssetDetails} windowLabel={flowWindowText(summary)} />
      </section>

      <section className="cc-card cc-table-card cc-signal-board-card">
        <div className="cc-panel-title"><h3>Asset Signal Board</h3><span>Clearest long/short conviction first</span></div>
        <div className="cc-scroll-table cc-scroll-y">
          <table className="cc-signal-table">
            <thead><tr><th>#</th><th className="cc-mobile-asset-logo-head" aria-label="Asset logo" /><SortTh label="Asset" sortKey="asset" sort={signalSort} setSort={setSignalSort} /><SortTh label="Signal" sortKey="conviction" sort={signalSort} setSort={setSignalSort} /><SortTh label="Confidence" sortKey="confidence" sort={signalSort} setSort={setSignalSort} /><SortTh label="Wallets" sortKey="wallets" sort={signalSort} setSort={setSignalSort} /><SortTh label="Wallet value L/S" sortKey="value_ls" sort={signalSort} setSort={setSignalSort} /><SortTh label="Net value" sortKey="net_value_usd" sort={signalSort} setSort={setSignalSort} /><SortTh label="% total value" sortKey="pct_total" sort={signalSort} setSort={setSignalSort} /></tr></thead>
            <tbody>{sortedSignals.map((r, i) => <tr key={`${r.coin}-${i}`}><td>{i + 1}</td><td className="cc-mobile-asset-logo-cell" aria-hidden="true"><TokenLogo coin={r.coin} icons={icons} /></td><td><span className="cc-asset-cell"><TokenLogo coin={r.coin} icons={icons} /><AssetName coin={r.coin} details={mergedAssetDetails} row={r} /></span></td><td className={cls(displaySignalValue(r))}><span className={`cc-signal-pill ${signalDirectionClass(r)}`}>{displaySignalMagnitudePct(r)} {displaySignalDirection(r)}</span></td><td><span className={`cc-confidence ${String(r.confidence).toLowerCase()}`}>{r.confidence}</span></td><td>{r.wallets_long} long / {r.wallets_short} short</td><td>{money(r.value_long_usd)} / {money(r.value_short_usd)}</td><td className={cls(r.net_value_usd)}>{money(r.net_value_usd)}</td><td>{pct(r.value_long_pct_total)} long / {pct(r.value_short_pct_total)} short</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      <section className="cc-dashboard-trading-grid">
        <PricePositioningChart icons={icons} signals={signals} details={mergedAssetDetails} />
      </section>

      <section className="cc-dashboard-context-row">
        <MarketNarrativeCard narrative={marketNarrative} />
        <CatalystWatchCard watch={catalystWatch} />
      </section>

      <section className="cc-dashboard-performance-row">
        <div className="cc-index-compact-wrapper"><PerformanceIndex variant="dashboard" /></div>
        <div className="cc-card cc-table-card cc-pressure-card">
          <div className="cc-panel-title"><h3>Recent Buyer / Seller Pressure</h3><span>{flowContextText}</span></div>
          <div className="cc-scroll-table cc-scroll-y">
            <table className="cc-flow-table">
              <thead><tr><th className="cc-mobile-asset-logo-head" aria-label="Asset logo" /><SortTh label="Asset" sortKey="asset" sort={flowSortState} setSort={setFlowSortState} /><SortTh label="Long exposure" sortKey="value_long_usd" sort={flowSortState} setSort={setFlowSortState} /><SortTh label="Short exposure" sortKey="value_short_usd" sort={flowSortState} setSort={setFlowSortState} /><SortTh label="Buy flow" sortKey="bullish" sort={flowSortState} setSort={setFlowSortState} /><SortTh label="Sell flow" sortKey="bearish" sort={flowSortState} setSort={setFlowSortState} /><SortTh label="Net flow" sortKey="net_value_flow_usd" sort={flowSortState} setSort={setFlowSortState} /></tr></thead>
              <tbody>{sortedFlow.map((r, i) => <tr key={`${r.coin}-${i}`}><td className="cc-mobile-asset-logo-cell" aria-hidden="true"><TokenLogo coin={r.coin} icons={icons} /></td><td><span className="cc-asset-cell"><TokenLogo coin={r.coin} icons={icons} /><AssetName coin={r.coin} details={mergedAssetDetails} row={r} /></span></td><td className="positive">{money(r.value_long_usd)}</td><td className="negative">{money(r.value_short_usd)}</td><td>{money(r.bullish_flow_usd)}</td><td>{money(r.bearish_flow_usd)}</td><td className={cls(r.net_value_flow_usd)}>{money(r.net_value_flow_usd)}</td></tr>)}</tbody>
            </table>
          </div>
        </div>
      </section>

      <footer className="cc-warning-banner"><span className="cc-shield" aria-hidden><svg viewBox="0 0 24 24"><path d="M12 3l7 3v5.2c0 4.5-2.7 8.4-7 9.8-4.3-1.4-7-5.3-7-9.8V6l7-3z"/><path d="M9.2 12.1l1.7 1.7 3.9-4.1"/></svg></span><div className="cc-footer-main"><strong>Market intelligence only.</strong><em>Not financial advice. {rankingScope}. {claimReady ? 'Broad-index threshold met.' : 'Not claiming all-Hyperliquid top 50 yet.'}</em><small>Live coverage: {liveCoverageText} · {summary.snapshot_wallets || 0} fallback · Sync: <b className={`cc-audit-${summary.data_quality_status === 'healthy' ? 'pass' : 'checking'}`}>{summary.data_quality_status === 'healthy' ? 'live' : 'checking'}</b> · {summary.data_quality_message || 'Waiting for live feed'}</small></div><div className={`cc-footer-meta ${dataHealthy ? 'healthy' : 'checking'}`}><span className="cc-footer-quality"><span className="cc-pulse-dot" /><b>{dataHealthy ? (claimReady ? 'Live data and ranking verified' : 'Live feed healthy') : 'Data quality checking'}</b></span><small>Signal refresh: {fmtTime(summary.latest_signal_ts_ms)} UTC · {summary.live_state_active ? `Live state: ${fmtTime(summary.latest_live_state_ts_ms)} UTC` : 'Snapshot mode'} · Snapshot/cache refresh</small></div><nav className="cc-legal-links" aria-label="Legal links" style={{ flexBasis: '100%', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'flex-start', gap: 6, margin: '4px 0 0 41px', padding: 0, fontSize: 11, lineHeight: 1.25, color: 'rgba(247,251,255,.62)' }}><span style={{ color: 'rgba(247,251,255,.42)' }}>Legal:</span><a href="/terms" style={{ color: 'inherit', textDecoration: 'none', fontSize: 11 }}>Terms</a><span aria-hidden="true" style={{ color: 'rgba(247,251,255,.42)' }}> · </span><a href="/privacy" style={{ color: 'inherit', textDecoration: 'none', fontSize: 11 }}>Privacy</a><span aria-hidden="true" style={{ color: 'rgba(247,251,255,.42)' }}> · </span><a href="/risk-disclaimer" style={{ color: 'inherit', textDecoration: 'none', fontSize: 11 }}>Risk disclaimer</a><span aria-hidden="true" style={{ color: 'rgba(247,251,255,.42)' }}> · </span><a href="/external-links" style={{ color: 'inherit', textDecoration: 'none', fontSize: 11 }}>External links</a></nav></footer>
    </main>
  </div>

}


