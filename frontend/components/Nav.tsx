'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

function Brand() {
  return (
    <Link href="/" className="brand" aria-label="Copycat home">
      <span className="brand-word"><span>Copy</span><em>cat</em></span>
    </Link>
  )
}

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
      <Brand />
      <div className="links nav-links">
        <Link href="/pricing">Pricing</Link>
        <Link href="/login">Login</Link>
        <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle light and dark mode">
          <span>{theme === 'dark' ? 'Dark' : 'Light'}</span>
          <i />
        </button>
        <Link className="btn nav-dashboard" href="/dashboard">Dashboard</Link>
      </div>
    </nav>
  )
}
