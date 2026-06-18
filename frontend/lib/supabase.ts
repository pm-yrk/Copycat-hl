'use client'

import type { SupabaseClient } from '@supabase/supabase-js'

type RuntimeConfig = {
  supabaseUrl: string
  supabaseAnonKey: string
  apiBaseUrl: string
}

let configPromise: Promise<RuntimeConfig> | null = null
let supabaseClient: SupabaseClient | null = null

export async function getRuntimeConfig(): Promise<RuntimeConfig> {
  if (!configPromise) {
    configPromise = fetch('/api/runtime-config', { cache: 'no-store' }).then(async (res) => {
      if (!res.ok) throw new Error('Could not load runtime config')
      return res.json()
    })
  }
  return configPromise
}

export async function getSupabase(): Promise<SupabaseClient> {
  if (supabaseClient) return supabaseClient
  const cfg = await getRuntimeConfig()
  if (!cfg.supabaseUrl || !cfg.supabaseAnonKey) {
    throw new Error('Supabase is not configured. Check frontend environment variables in Render.')
  }
  const { createClient } = await import('@supabase/supabase-js')
  supabaseClient = createClient(cfg.supabaseUrl, cfg.supabaseAnonKey)
  return supabaseClient
}

export async function getApiBaseUrl(): Promise<string> {
  const cfg = await getRuntimeConfig()
  return cfg.apiBaseUrl || 'https://hwt-api.onrender.com'
}
