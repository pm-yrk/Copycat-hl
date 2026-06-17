import Link from 'next/link'
export default function Nav(){return <div className="nav"><Link className="brand" href="/">Hyper Wallet Tracker</Link><div className="links"><Link href="/pricing">Pricing</Link><Link href="/login">Login</Link><Link className="btn" href="/dashboard">Dashboard</Link></div></div>}
