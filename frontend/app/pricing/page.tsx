import Link from 'next/link'
import PublicNav from '../../components/PublicNav'
import PublicMeshBackdrop from '../../components/PublicMeshBackdrop'

const tiers = [
  { title: 'Free', price: '£0', desc: 'Explore Copycat with no commitment.', items: ['Delayed dashboard preview', 'Short API preview endpoints', 'Risk warnings and methodology notes', 'No credit card required'], cta: 'Coming soon', href: '/login', icon: '◇' },
  { title: 'Copycat Pro', price: '£49', unit: '/month', desc: 'Live dashboard access and advanced market intelligence.', items: ['Live dashboard access', 'Top 50 Copycat-ranked wallet cohort', 'Asset signal board and buyer/seller pressure', 'Portfolio allocation and Copycat Index', 'Market intelligence updates'], cta: 'Start Pro', href: '/login', featured: true, icon: '⌁' },
  { title: 'Copycat Pro + Alerts', price: '£99', unit: '/month', desc: 'Everything in Pro, plus alerts when the market moves.', items: ['Everything in Copycat Pro', '15-minute Telegram digests', 'Major conviction change alerts', 'Large accumulation/distribution alerts', 'Priority alert channels later'], cta: 'Start alerts', href: '/login', icon: '◷' },
]

const comparison = [
  ['Live dashboard', 'Delayed preview', '✓', '✓'],
  ['Top 50 wallet cohort', 'Preview', '✓', '✓'],
  ['Alerts & Telegram digests', '—', '—', '✓'],
  ['Public API preview', '✓', '✓', '✓'],
]

export default function Pricing() {
  return <div className="public-redesign-root">
    <PublicNav/>
    <main className="public-redesign-shell public-pricing">
      <PublicMeshBackdrop variant="pricing"/>
      <section className="public-pricing-hero">
        <p className="public-eyebrow"><span/> Dashboard + API</p>
        <h1>Simple pricing.</h1>
        <p>Start free, then unlock the full dashboard, alerts or developer access as you need them.</p>
      </section>

      <section className="public-pricing-cards">
        {tiers.map(t => <article key={t.title} className={t.featured ? 'featured' : ''}>
          {t.featured ? <em className="public-popular">★ Most popular</em> : null}
          <i className="public-plan-icon">{t.icon}</i>
          <h2>{t.title}</h2>
          <div className="public-plan-price">{t.price}<small>{t.unit || ''}</small></div>
          <div className="public-price-line"/>
          <p>{t.desc}</p>
          <ul>{t.items.map(item => <li key={item}><span>✓</span>{item}</li>)}</ul>
          <Link className={t.featured ? 'public-primary full' : 'public-secondary full'} href={t.href}>{t.cta} <span>→</span></Link>
        </article>)}
      </section>

      <section className="public-comparison">
        <div className="public-comparison-head"><span>Key features</span><b>Free</b><b>Copycat Pro</b><b>Pro + Alerts</b></div>
        {comparison.map(row => <div className="public-comparison-row" key={row[0]}><span>{row[0]}</span><em>{row[1]}</em><em>{row[2]}</em><em>{row[3]}</em></div>)}
      </section>

      <section className="public-api-offer">
        <div className="public-api-offer-copy"><i>&lt;/&gt;</i><div><p className="public-eyebrow"><span/> Developer access</p><h2>Building with Copycat?</h2><p>Programmatic access to ranked wallet data, positions, fills, market signals and historical intelligence.</p></div></div>
        <div className="public-api-price"><span>Developer API</span><b>£249<small>/month</small></b></div>
        <ul><li>✓ API key access</li><li>✓ Leaderboard, signals and flow endpoints</li><li>✓ Coverage and freshness metadata</li><li>✓ Usage logging and rate limits</li></ul>
        <div className="public-api-offer-actions"><Link className="public-primary" href="/api-access">Explore API <span>→</span></Link><a href="mailto:paulmurrin13@gmail.com?subject=Copycat%20API%20access">Request access →</a></div>
      </section>

      <footer className="public-disclaimer"><span>◇</span><p><b>Market intelligence only, not financial advice.</b> Crypto trading can result in loss. Subscription features are research and market-intelligence software.</p><Link href="/risk-disclaimer">Learn more →</Link></footer>
    </main>
  </div>
}
