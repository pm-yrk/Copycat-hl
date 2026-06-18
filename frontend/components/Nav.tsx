'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

type Theme = 'dark' | 'light'

function preferredTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  const saved = localStorage.getItem('copycat-theme')
  if (saved === 'dark' || saved === 'light') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export default function Nav() {
  const [theme, setTheme] = useState<Theme>('light')

  useEffect(() => {
    const initial = preferredTheme()
    setTheme(initial)
    document.documentElement.dataset.theme = initial

    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => {
      const saved = localStorage.getItem('copycat-theme')
      if (saved === 'dark' || saved === 'light') return
      const next = mq.matches ? 'dark' : 'light'
      setTheme(next)
      document.documentElement.dataset.theme = next
    }
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])

  function toggleTheme() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
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
        <button className="theme-switch" onClick={toggleTheme} aria-label="Toggle light and dark mode">
          <span>{theme === 'dark' ? 'Dark' : 'Light'}</span><i />
        </button>
        <Link className="dashboard-nav" href="/dashboard">Dashboard</Link>
      </div>
    </nav>
  )
}
