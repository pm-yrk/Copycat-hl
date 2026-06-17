import Link from 'next/link'

export default function Nav(){
  return <div className="nav">
    <Link className="brand" href="/" aria-label="copycat.hl home"><span className="brand-mark">cc</span><span>copycat.hl</span></Link>
    <div className="links nav-links"><Link href="/pricing">Pricing</Link><Link href="/login">Login</Link><Link className="btn btn-sm" href="/dashboard">Dashboard</Link></div>
  </div>
}
