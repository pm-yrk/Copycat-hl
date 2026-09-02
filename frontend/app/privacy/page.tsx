import Link from 'next/link'
import PublicNav from '../../components/PublicNav'
import PublicMeshBackdrop from '../../components/PublicMeshBackdrop'

export const metadata = {
  title: 'Privacy Policy | Copycat',
  description: 'Copycat legal information.',
}

export default function Page() {
  return (
    <div className="public-redesign-root">
      <PublicNav />
      <main className="cc-legal-page">
      <PublicMeshBackdrop variant="privacy"/>
      <section className="cc-legal-wrap">
        <Link className="cc-legal-back" href="/">← Back to Copycat</Link>
        <div className="cc-legal-kicker">Copycat privacy</div>
        <h1>Privacy Policy</h1>
        <p className="cc-legal-updated">Last updated: 30 June 2026</p>
      <h2>Overview</h2>
        <p>Copycat aims to collect as little personal information as practical. At the current stage, the dashboard is primarily a public market-intelligence site.</p>
        <p>If paid accounts, email capture, analytics, alerts, or login features are added, this policy should be updated before launch.</p>
      <h2>Information we may collect</h2>
        <p>We may collect information you provide directly, such as email address, account details, support messages, waitlist submissions, or billing-related identifiers.</p>
        <p>We may collect basic technical information such as browser type, device information, pages viewed, approximate region, referral source, timestamps, and security logs.</p>
      <h2>How information is used</h2>
        <p>Information may be used to operate Copycat, provide access, process subscriptions, send alerts, improve the product, detect abuse, secure the service, and communicate important updates.</p>
        <p>Copycat does not sell personal information to advertisers.</p>
      <h2>Payments</h2>
        <p>If subscriptions are enabled, payment details should be handled by a payment processor such as Stripe. Copycat should not store full card numbers on its own servers.</p>
        <p>Billing providers may process personal information according to their own privacy terms.</p>
      <h2>Cookies and analytics</h2>
        <p>Copycat may use cookies or similar technologies for login, security, preferences, analytics, or subscription access.</p>
        <p>Any future analytics should be configured in a privacy-conscious way and disclosed clearly.</p>
      <h2>Data retention and security</h2>
        <p>We keep information only as long as reasonably needed for the purposes described here, legal compliance, dispute resolution, and security.</p>
        <p>No internet service can guarantee perfect security, but we use reasonable safeguards and avoid placing private secrets in frontend code.</p>
      <h2>Contact</h2>
        <p>For privacy questions, contact the Copycat operator using the contact details provided on the site or product support channel.</p>
        <div className="cc-legal-note">Before adding logins, email capture, payments, analytics, or user alerts, update this page to match the exact tools used.</div>
      </section>
      </main>
    </div>
  )
}
