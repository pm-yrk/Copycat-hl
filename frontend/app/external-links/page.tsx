import Link from 'next/link'
import PublicNav from '../../components/PublicNav'

export const metadata = {
  title: 'External Links Notice | Copycat',
  description: 'Copycat legal information.',
}

export default function Page() {
  return (
    <div className="public-redesign-root">
      <PublicNav />
      <main className="cc-legal-page">
      <section className="cc-legal-wrap">
        <Link className="cc-legal-back" href="/">← Back to Copycat</Link>
        <div className="cc-legal-kicker">Third-party links</div>
        <h1>External Links Notice</h1>
        <p className="cc-legal-updated">Last updated: 30 June 2026</p>
      <h2>Why we link out</h2>
        <p>Copycat may provide links to third-party block explorers, market pages, wallet pages, token pages, documentation, or infrastructure providers for convenience.</p>
        <p>These links help users verify public information or inspect activity outside the Copycat dashboard.</p>
      <h2>No affiliation or endorsement</h2>
        <p>External links do not mean Copycat is affiliated with, sponsored by, endorsed by, or partnered with the linked service.</p>
        <p>Names, logos, protocols, tokens, explorers, exchanges, and brands belong to their respective owners.</p>
      <h2>HypurrScan links</h2>
        <p>Copycat may link wallet labels to HypurrScan address pages so users can inspect public Hyperliquid wallet activity in an external explorer.</p>
        <p>Copycat does not control HypurrScan, does not speak for HypurrScan, and does not imply any affiliation with HypurrScan.</p>
      <h2>External sites have their own rules</h2>
        <p>Third-party sites may have their own terms, privacy policies, fees, risks, data practices, outages, or errors.</p>
        <p>When you leave Copycat, your use of the external site is governed by that third party’s rules.</p>
      <h2>No scraping or embedding promise</h2>
        <p>Copycat’s clean approach is to use normal outbound links where useful, not to copy third-party pages, misrepresent third-party data, or imply endorsement.</p>
        <p>If Copycat later adds deeper integrations, they should be reviewed separately.</p>
        <div className="cc-legal-note">External explorer links are provided for convenience only. Copycat is not affiliated with HypurrScan or any external explorer unless expressly stated.</div>
      </section>
      </main>
    </div>
  )
}
