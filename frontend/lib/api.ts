'use client'

import { getApiBaseUrl, getSupabase } from './supabase'

type ApiOptions = { signal?: AbortSignal; timeoutMs?: number }



function copycatIsCloudflarePagesRuntime() {
  if (typeof window === 'undefined') return false
  const host = window.location.hostname || ''
  return host.endsWith('.pages.dev') || host.includes('copycat')
}

function copycatSnapshotFileForPath(path: string) {
  const clean = path.split('?')[0].replace(/\/+$/, '')
  const map: Record<string, string> = {
    '/api/dashboard-feed': 'dashboard-feed.json',
    '/api/dashboard-tick': 'dashboard-tick.json',
    '/api/performance-index': 'performance-index.json',
    '/api/data/v1/status': 'api/status.json',
    '/api/data/v1/public/leaderboard-preview': 'api/leaderboard-preview.json',
    '/api/data/v1/public/token-screener-preview': 'api/token-screener-preview.json',
    '/api/data/v1/public/coverage-preview': 'api/coverage-preview.json',
    '/api/data/v1/public/platform-health': 'api/platform-health.json',
    '/api/token-icons': 'token-icons.json',
    '/api/ranking-audit': 'api/ranking-audit.json',
    '/api/audit': 'api/audit.json',
    '/api/free-mode-status': 'api/free-mode-status.json',
    '/api/scanner-status': 'api/scanner-status.json',
  }
  return map[clean] || ''
}

function copycatSnapshotUrlsForPath(path: string) {
  const file = copycatSnapshotFileForPath(path)
  if (!file) return [] as string[]
  const configured = (process.env.NEXT_PUBLIC_SNAPSHOT_BASE_URL || 'https://pub-b9e0279f5eb0496b99c7fa37329e6b53.r2.dev').replace(/\/+$/, '')
  const urls: string[] = []
  if (configured) urls.push(`${configured}/${file}`)
  // Always keep the same-origin Cloudflare Pages bundled snapshot as a fallback.
  // This avoids blank/zero dashboards when R2 CORS, R2 upload paths, or env vars are wrong.
  urls.push(`/copycat-data/${file}`)
  return Array.from(new Set(urls))
}


function copycatFreshSnapshotUrlsForPath(path: string) {
  const file = copycatSnapshotFileForPath(path)
  if (!file) return [] as string[]
  const configured = (process.env.NEXT_PUBLIC_SNAPSHOT_BASE_URL || 'https://pub-b9e0279f5eb0496b99c7fa37329e6b53.r2.dev').replace(/\/+$/, '')
  return configured ? [`${configured}/${file}`] : []
}

function copycatPrefersSnapshot(path: string) {
  if (!copycatSnapshotFileForPath(path)) return false
  return process.env.NEXT_PUBLIC_SNAPSHOT_FIRST === 'true'
    || process.env.NEXT_PUBLIC_STATIC_EXPORT === 'true'
    || copycatIsCloudflarePagesRuntime()
}

async function copycatFetchJson(url: string, options: ApiOptions = {}, cache: RequestCache = 'default') {
  const controller = options.signal ? null : new AbortController()
  const signal = options.signal || controller?.signal
  const timeout = controller ? window.setTimeout(() => controller.abort(), options.timeoutMs || 12000) : null
  try {
    const res = await fetch(url, { cache, signal })
    if (!res.ok) throw new Error(`Snapshot request failed: ${res.status}`)
    return await res.json()
  } finally {
    if (timeout) window.clearTimeout(timeout)
  }
}


async function authToken() {
  try {
    const supabase = await getSupabase()
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token || 'demo'
  } catch {
    return 'demo'
  }
}

export async function apiGet(path: string, options: ApiOptions = {}) {
  const snapshotUrls = copycatSnapshotUrlsForPath(path)
  if (snapshotUrls.length && copycatPrefersSnapshot(path)) {
    for (const url of snapshotUrls) {
      try {
        return await copycatFetchJson(url, options, 'default')
      } catch {
        // Try next snapshot source, then fall back to the live API.
      }
    }
  }

  const token = await authToken()
  const apiBase = await getApiBaseUrl()
  const controller = options.signal ? null : new AbortController()
  const signal = options.signal || controller?.signal
  const timeout = controller ? window.setTimeout(() => controller.abort(), options.timeoutMs || 12000) : null
  try {
    const res = await fetch(`${apiBase}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
      signal,
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(text || `Request failed: ${res.status}`)
    }
    return res.json()
  } catch (err: any) {
    if (err?.name === 'AbortError') throw new Error('Live data request timed out')
    if (err instanceof TypeError) throw new Error('Live data temporarily unavailable')
    throw err
  } finally {
    if (timeout) window.clearTimeout(timeout)
  }
}

export async function apiPost(path: string, body: any, options: ApiOptions = {}) {
  const token = await authToken()
  const apiBase = await getApiBaseUrl()
  const controller = options.signal ? null : new AbortController()
  const signal = options.signal || controller?.signal
  const timeout = controller ? window.setTimeout(() => controller.abort(), options.timeoutMs || 12000) : null
  try {
    const res = await fetch(`${apiBase}${path}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(text || `Request failed: ${res.status}`)
    }
    return res.json()
  } catch (err: any) {
    if (err?.name === 'AbortError') throw new Error('Live data request timed out')
    if (err instanceof TypeError) throw new Error('Live data temporarily unavailable')
    throw err
  } finally {
    if (timeout) window.clearTimeout(timeout)
  }
}

/**
 * Fresh public-data fetch used by the redesigned public pages.
 * Unlike apiGet(), this deliberately does not fall back to the bundled
 * /public/copycat-data files because those can be old at deploy time.
 * If R2 and the live API are both unavailable, callers should render an
 * unavailable/stale state rather than presenting an old number as live.
 */
export async function apiGetFresh(path: string, options: ApiOptions = {}) {
  const snapshotUrls = copycatFreshSnapshotUrlsForPath(path)
  for (const url of snapshotUrls) {
    try {
      return await copycatFetchJson(url, options, 'no-store')
    } catch {
      // Fall through to the authenticated/live API below.
    }
  }

  const token = await authToken()
  const apiBase = await getApiBaseUrl()
  const controller = options.signal ? null : new AbortController()
  const signal = options.signal || controller?.signal
  const timeout = controller ? window.setTimeout(() => controller.abort(), options.timeoutMs || 12000) : null
  try {
    const res = await fetch(`${apiBase}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
      signal,
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(text || `Request failed: ${res.status}`)
    }
    return res.json()
  } catch (err: any) {
    if (err?.name === 'AbortError') throw new Error('Live data request timed out')
    if (err instanceof TypeError) throw new Error('Live data temporarily unavailable')
    throw err
  } finally {
    if (timeout) window.clearTimeout(timeout)
  }
}

