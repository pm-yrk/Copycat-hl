'use client'

import { useEffect, useMemo, useState } from 'react'

const STATIC_LOGOS: Record<string, string> = {
  BTC: 'https://cryptologos.cc/logos/bitcoin-btc-logo.svg?v=040',
  ETH: 'https://cryptologos.cc/logos/ethereum-eth-logo.svg?v=040',
  SOL: 'https://cryptologos.cc/logos/solana-sol-logo.svg?v=040',
  USDT: 'https://cryptologos.cc/logos/tether-usdt-logo.svg?v=040',
  DOGE: 'https://cryptologos.cc/logos/dogecoin-doge-logo.svg?v=040',
  AAVE: 'https://cryptologos.cc/logos/aave-aave-logo.svg?v=040',
  TRX: 'https://cryptologos.cc/logos/tron-trx-logo.svg?v=040',
  XRP: 'https://cryptologos.cc/logos/xrp-xrp-logo.svg?v=040',
  AVAX: 'https://cryptologos.cc/logos/avalanche-avax-logo.svg?v=040',
  BNB: 'https://cryptologos.cc/logos/bnb-bnb-logo.svg?v=040',
  LINK: 'https://cryptologos.cc/logos/chainlink-link-logo.svg?v=040',
  UNI: 'https://cryptologos.cc/logos/uniswap-uni-logo.svg?v=040',
  LTC: 'https://cryptologos.cc/logos/litecoin-ltc-logo.svg?v=040',
  DOT: 'https://cryptologos.cc/logos/polkadot-new-dot-logo.svg?v=040',
  FIL: 'https://cryptologos.cc/logos/filecoin-fil-logo.svg?v=040',
  ATOM: 'https://cryptologos.cc/logos/cosmos-atom-logo.svg?v=040',
  NEAR: 'https://cryptologos.cc/logos/near-protocol-near-logo.svg?v=040',
  ZEC: 'https://cryptologos.cc/logos/zcash-zec-logo.svg?v=040',
  ARB: 'https://cryptologos.cc/logos/arbitrum-arb-logo.svg?v=040',
  SUI: 'https://cryptologos.cc/logos/sui-sui-logo.svg?v=040',
  OP: 'https://cryptologos.cc/logos/optimism-ethereum-op-logo.svg?v=040',
  APE: 'https://cryptologos.cc/logos/apecoin-ape-ape-logo.svg?v=040',
  INJ: 'https://cryptologos.cc/logos/injective-inj-logo.svg?v=040',
  FET: 'https://cryptologos.cc/logos/artificial-superintelligence-alliance-fet-logo.svg?v=040',
}

const TOKEN_COLOURS: Record<string, string> = {
  HYPE: '#43e8d0', ETH: '#627eea', BTC: '#f7931a', SOL: '#14f195',
  ZEC: '#f4b728', NEAR: '#00ec97', AAVE: '#8b7dff', TRX: '#ff4b4b',
  XRP: '#4b9fff', USDC: '#2775ca', USDT: '#26a17b', PUMP: '#61c685',
  LIT: '#35d0b4', BNB: '#f3ba2f', XLM: '#44bdec',
}

const USDC_LOGO = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxMjggMTI4Jz48Y2lyY2xlIGN4PSc2NCcgY3k9JzY0JyByPSc2NCcgZmlsbD0nIzI3NzVDQScvPjxwYXRoIGQ9J000MiAzMGE0MiA0MiAwIDAgMCAwIDY4JyBmaWxsPSdub25lJyBzdHJva2U9JyNmZmYnIHN0cm9rZS13aWR0aD0nOCcgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJy8+PHBhdGggZD0nTTg2IDMwYTQyIDQyIDAgMCAxIDAgNjgnIGZpbGw9J25vbmUnIHN0cm9rZT0nI2ZmZicgc3Ryb2tlLXdpZHRoPSc4JyBzdHJva2UtbGluZWNhcD0ncm91bmQnLz48dGV4dCB4PSc2NCcgeT0nODQnIHRleHQtYW5jaG9yPSdtaWRkbGUnIGZvbnQtZmFtaWx5PSdBcmlhbCxIZWx2ZXRpY2Esc2Fucy1zZXJpZicgZm9udC1zaXplPSc1OCcgZm9udC13ZWlnaHQ9JzgwMCcgZmlsbD0nI2ZmZic+JDwvdGV4dD48L3N2Zz4='

export function canonicalPublicToken(symbol: string) {
  const clean = String(symbol || '').toUpperCase().trim()
  if (clean === 'USDC/CASH' || clean === 'USDCCASH' || clean === 'USDCASH' || clean === 'CASH') return 'USDC'
  return clean.replace(/[^A-Z0-9]/g, '')
}

export default function PublicTokenIcon({ symbol, className = '' }: { symbol: string; className?: string }) {
  const canonical = canonicalPublicToken(symbol)
  const [sourceIndex, setSourceIndex] = useState(0)
  const sources = useMemo(() => {
    if (!canonical || canonical === 'OTHER') return []
    if (canonical === 'USDC') return [USDC_LOGO]
    const lower = canonical.toLowerCase()
    return [
      STATIC_LOGOS[canonical],
      `https://assets.coincap.io/assets/icons/${lower}@2x.png`,
      `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/svg/color/${lower}.svg`,
      `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/${lower}.png`,
      `https://s3-symbol-logo.tradingview.com/crypto/XTVC${canonical}.svg`,
    ].filter(Boolean) as string[]
  }, [canonical])

  useEffect(() => setSourceIndex(0), [canonical])
  const source = sources[sourceIndex]
  const label = canonical === 'OTHER' ? 'Other assets' : `${canonical || symbol} logo`

  return <span
    className={`public-token-icon ${className}`}
    style={{ ['--public-token-colour' as any]: TOKEN_COLOURS[canonical] || '#35e8a7' }}
    aria-hidden="true"
    title={label}
  >
    {source
      ? <img src={source} alt="" loading="lazy" onError={() => setSourceIndex(index => index + 1)} />
      : <span>{canonical === 'OTHER' ? '•••' : (canonical || '?').slice(0, 2)}</span>}
  </span>
}
