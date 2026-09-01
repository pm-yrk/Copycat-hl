'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

export default function PublicNav() {
  const path = usePathname()
  const links = [
    ['/dashboard', 'Dashboard'],
    ['/#how-it-works', 'How it works'],
    ['/api-access', 'API'],
    ['/pricing', 'Pricing'],
  ] as const

  return <nav className="public-nav" aria-label="Primary navigation">
    <Link href="/" className="public-brand" aria-label="Copycat home"><span>Copy</span><em>cat</em></Link>
    <div className="public-nav-links">
      {links.map(([href, label]) => <Link key={href} href={href} className={path === href ? 'active' : ''}>{label}</Link>)}
    </div>
    <div className="public-nav-actions">
      <Link href="/login" className="public-signin">Sign in</Link>
      <Link href="/dashboard" className="public-nav-cta">Open dashboard <span>→</span></Link>
    </div>
    <details className="public-nav-mobile">
      <summary aria-label="Open navigation">Menu</summary>
      <div>
        {links.map(([href, label]) => <Link key={href} href={href}>{label}</Link>)}
        <Link href="/login">Sign in</Link>
      </div>
    </details>
  </nav>
}
