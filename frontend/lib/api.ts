import { getApiBaseUrl, getSupabase } from './supabase'

export async function apiGet(path: string) {
  const supabase = await getSupabase()
  const apiBaseUrl = await getApiBaseUrl()
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token || 'demo'
  const sep = path.includes('?') ? '&' : '?'
  const url = `${apiBaseUrl}${path}${sep}_=${Date.now()}`
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Cache-Control': 'no-cache, no-store, max-age=0',
      Pragma: 'no-cache',
    },
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function apiPost(path: string, body: any) {
  const supabase = await getSupabase()
  const apiBaseUrl = await getApiBaseUrl()
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token || 'demo'
  const res = await fetch(`${apiBaseUrl}${path}`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Cache-Control': 'no-cache, no-store, max-age=0', Pragma: 'no-cache' }, body: JSON.stringify(body), cache: 'no-store' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
