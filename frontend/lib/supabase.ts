'use client'

import type { SupabaseClient } from '@supabase/supabase-js'

type RuntimeConfig = {
  supabaseUrl: string
  supabaseAnonKey: string
  apiBaseUrl: string
}

let configPromise: Promise<RuntimeConfig> | null = null
let supabaseClient: SupabaseClient | null = null
let supabasePromise: Promise<SupabaseClient> | null = null

function envRuntimeConfig(): RuntimeConfig {
  return {
    supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL || '',
    supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '',
    apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL || 'https://hwt-api.onrender.com',
  }
}

export async function getRuntimeConfig(): Promise<RuntimeConfig> {
  const envCfg = envRuntimeConfig()
  // Cloudflare Pages/static export has no Next API routes, so prefer build-time public env vars.
  if (envCfg.supabaseUrl || envCfg.supabaseAnonKey || envCfg.apiBaseUrl) return envCfg

  if (!configPromise) {
    configPromise = fetch('/api/runtime-config', { cache: 'force-cache' }).then(async (res) => {
      if (!res.ok) throw new Error('Could not load runtime config')
      return res.json()
    }).catch(() => envRuntimeConfig())
  }
  return configPromise
}

export async function getSupabase(): Promise<SupabaseClient> {
  if (supabaseClient) return supabaseClient
  if (!supabasePromise) {
    supabasePromise = (async () => {
      const cfg = await getRuntimeConfig()
      if (!cfg.supabaseUrl || !cfg.supabaseAnonKey) {
        throw new Error('Supabase is not configured. Check frontend environment variables.')
      }
      const { createClient } = await import('@supabase/supabase-js')
      supabaseClient = createClient(cfg.supabaseUrl, cfg.supabaseAnonKey)
      return supabaseClient
    })().catch((error) => {
      // Allow a later retry if configuration/network setup was temporarily unavailable.
      supabasePromise = null
      throw error
    })
  }
  return supabasePromise
}

export async function getApiBaseUrl(): Promise<string> {
  const cfg = await getRuntimeConfig()
  return cfg.apiBaseUrl || 'https://hwt-api.onrender.com'
}
