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
      const next: Theme = mq.matches ? 'dark' : 'light'
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

      <div className="nav-menu-wrap">
        <button className="nav-menu-trigger" aria-haspopup="true" aria-label="Open navigation menu">
          <span>Menu</span>
          <i />
        </button>
        <div className="nav-menu" role="menu">
          <Link href="/api-access" role="menuitem">API</Link>
          <Link href="/pricing" role="menuitem">Pricing</Link>
          <Link href="/login" role="menuitem">Login</Link>
          <Link href="/dashboard" role="menuitem">Dashboard</Link>
          <button className="theme-switch menu-theme" onClick={toggleTheme} aria-label="Toggle light and dark mode">
            <span>{theme === 'dark' ? 'Dark mode' : 'Light mode'}</span><i />
          </button>
        </div>
      </div>
    </nav>
  )
}
