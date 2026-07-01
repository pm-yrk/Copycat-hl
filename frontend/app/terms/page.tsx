import Link from 'next/link'

export const metadata = {
  title: 'Terms of Service | Copycat',
  description: 'Copycat legal information.',
}

export default function Page() {
  return (
    <main className="cc-legal-page">
      <section className="cc-legal-wrap">
        <Link className="cc-legal-back" href="/">← Back to Copycat</Link>
        <div className="cc-legal-kicker">Copycat legal</div>
        <h1>Terms of Service</h1>
        <p className="cc-legal-updated">Last updated: 30 June 2026</p>
      <h2>Use of Copycat</h2>
        <p>Copycat provides market-intelligence dashboards, wallet-scoring signals, public-chain observations, and related analytics for informational purposes only.</p>
        <p>By using Copycat, you agree that you are responsible for your own trading, investment, tax, legal, and financial decisions.</p>
      <h2>No financial advice</h2>
        <p>Copycat does not provide financial advice, investment advice, trading advice, brokerage services, portfolio management, custody, or execution services.</p>
        <p>Nothing on Copycat is a recommendation to buy, sell, hold, copy, or trade any asset, wallet, position, strategy, or market.</p>
      <h2>Data and availability</h2>
        <p>Copycat uses public and third-party data sources, local snapshots, and automated processing. Data may be delayed, incomplete, incorrect, interrupted, or unavailable.</p>
        <p>We may change, limit, suspend, or discontinue any feature, metric, ranking, data feed, or page at any time.</p>
      <h2>Wallet rankings</h2>
        <p>Copycat-ranked wallets are selected from Copycat’s locally indexed and scanned wallet universe. They are not presented as the most profitable wallets across all of Hyperliquid unless explicitly stated with supporting methodology.</p>
        <p>Historical performance, wallet behavior, and market signals do not guarantee future results.</p>
      <h2>Acceptable use</h2>
        <p>You agree not to misuse the service, interfere with the site, attempt unauthorized access, scrape at abusive scale, copy the product for resale, or use Copycat in a way that violates applicable law.</p>
        <p>All Copycat branding, design, copy, scoring logic, and original content belong to Copycat unless otherwise stated.</p>
      <h2>External services</h2>
        <p>Copycat may link to external explorers, protocols, wallets, exchanges, or data services for convenience. External services are controlled by third parties and have their own terms and policies.</p>
        <p>Copycat is not responsible for third-party sites, third-party content, or actions you take after leaving Copycat.</p>
      <h2>Limitation of liability</h2>
        <p>Copycat is provided as-is and as-available. To the fullest extent permitted by law, Copycat is not liable for losses, damages, missed opportunities, trading losses, data errors, outages, or reliance on any information shown on the site.</p>
        <p>Some jurisdictions do not allow certain limitations, so parts of this section may not apply to you.</p>
        <div className="cc-legal-note">These terms are a practical commercial starting point and should be reviewed by a qualified lawyer before heavy paid launch.</div>
      </section>
    </main>
  )
}
