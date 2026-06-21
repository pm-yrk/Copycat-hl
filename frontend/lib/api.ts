'use client'

import { getApiBaseUrl, getSupabase } from './supabase'

type ApiOptions = { signal?: AbortSignal; timeoutMs?: number }


function copycatSnapshotBaseUrl() {
  const configured = process.env.NEXT_PUBLIC_SNAPSHOT_BASE_URL || ''
  const fallback = process.env.NEXT_PUBLIC_STATIC_EXPORT === 'true' ? '/copycat-data' : ''
  return (configured || fallback).replace(/\/+$/, '')
}

function copycatPrefersSnapshot() {
  return process.env.NEXT_PUBLIC_SNAPSHOT_FIRST === 'true' || process.env.NEXT_PUBLIC_STATIC_EXPORT === 'true'
}

function copycatSnapshotUrlForPath(path: string) {
  const base = copycatSnapshotBaseUrl()
  if (!base) return ''
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
  }
  const file = map[clean]
  if (!file) return ''
  return `${base}/${file}`
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


const PUBLIC_GET_PREFIXES = [
  '/api/dashboard-feed',
  '/api/dashboard-tick',
  '/api/performance-index',
  '/api/performance-backtest',
  '/api/backtest-index',
  '/api/token-icons',
  '/api/data/v1/status',
  '/api/data/v1/public/',
]

function isPublicGet(path: string) {
  return PUBLIC_GET_PREFIXES.some(prefix => path === prefix || path.startsWith(prefix + '?'))
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
  const publicRead = isPublicGet(path)
  const token = publicRead ? null : await authToken()
  const apiBase = await getApiBaseUrl()
  const controller = options.signal ? null : new AbortController()
  const signal = options.signal || controller?.signal
  const timeout = controller ? window.setTimeout(() => controller.abort(), options.timeoutMs || 12000) : null
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
  try {
    const res = await fetch(`${apiBase}${path}`, {
      headers,
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
