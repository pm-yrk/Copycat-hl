import Link from 'next/link'
import PublicNav from '../../components/PublicNav'

export const metadata = {
  title: 'Risk Disclaimer | Copycat',
  description: 'Copycat legal information.',
}

export default function Page() {
  return (
    <div className="public-redesign-root">
      <PublicNav />
      <main className="cc-legal-page">
      <section className="cc-legal-wrap">
        <Link className="cc-legal-back" href="/">← Back to Copycat</Link>
        <div className="cc-legal-kicker">Market risk</div>
        <h1>Risk Disclaimer</h1>
        <p className="cc-legal-updated">Last updated: 30 June 2026</p>
      <h2>Crypto and perpetuals are risky</h2>
        <p>Cryptoassets, derivatives, perpetual futures, leverage, and wallet-following strategies are highly risky. Prices can move quickly and losses can be substantial.</p>
        <p>You can lose money, including more than expected when using leverage or complex trading products.</p>
      <h2>Copycat is informational only</h2>
        <p>Copycat shows market intelligence, wallet activity, scanner output, and ranked signals for research purposes only.</p>
        <p>Copycat does not tell you what to buy, sell, hold, copy, short, long, or trade.</p>
      <h2>Wallet data can be misleading</h2>
        <p>A wallet that looks smart may still lose money. A wallet’s public activity may not show its complete strategy, hedges, private positions, risk tolerance, or off-chain context.</p>
        <p>Copying wallets blindly can be dangerous because entries, exits, leverage, liquidity, funding, and timing may differ.</p>
      <h2>Rankings are not guarantees</h2>
        <p>Copycat-ranked wallets are selected by Copycat’s current scoring system from its locally indexed universe. Rankings may change and may be wrong.</p>
        <p>Past wallet activity, recent flow, conviction, exposure, or profitability signals do not guarantee future results.</p>
      <h2>Data may be wrong or delayed</h2>
        <p>Blockchain, exchange, market, and snapshot data may be delayed, incomplete, unavailable, duplicated, mislabelled, or incorrect.</p>
        <p>Always verify important information independently before making decisions.</p>
      <h2>Your responsibility</h2>
        <p>You are solely responsible for your own decisions, risk management, position sizing, tax obligations, and compliance with laws that apply to you.</p>
        <p>Do not trade with money you cannot afford to lose.</p>
        <div className="cc-legal-note">Copycat is market intelligence only. It is not a broker, exchange, advisor, custodian, or trading system.</div>
      </section>
      </main>
    </div>
  )
}
