'use client'

import { getApiBaseUrl, getSupabase } from './supabase'

type ApiOptions = { signal?: AbortSignal; timeoutMs?: number }

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
