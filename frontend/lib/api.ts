import { supabase } from './supabase'

const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

export async function apiGet(path: string) {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token || 'demo'
  const res = await fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function apiPost(path: string, body: any) {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token || 'demo'
  const res = await fetch(`${API}${path}`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
