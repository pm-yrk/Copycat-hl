'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

export default function Nav() {
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    const saved = typeof window !== 'undefined' ? localStorage.getItem('copycat-theme') : null
    const next = saved === 'light' || saved === 'dark' ? saved : 'dark'
    setTheme(next)
    document.documentElement.dataset.theme = next
  }, [])

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    document.documentElement.dataset.theme = next
    localStorage.setItem('copycat-theme', next)
  }

  return (
    <nav className="nav">
      <Link href="/" className="brand" aria-label="Copycat home">
        <span>Copy</span><em>cat</em>
      </Link>
      <div className="nav-links">
        <Link href="/pricing">Pricing</Link>
        <Link href="/login">Login</Link>
        <button className="theme-switch" onClick={toggleTheme} aria-label="Toggle light and dark mode"><span>{theme === 'dark' ? 'Dark' : 'Light'}</span><i /></button>
        <Link className="dashboard-nav" href="/dashboard">Dashboard</Link>
      </div>
    </nav>
  )
}
