import type { NextConfig } from 'next'

const staticExport = process.env.CLOUDFLARE_PAGES === '1' || process.env.NEXT_PUBLIC_STATIC_EXPORT === 'true'

const nextConfig: NextConfig = {
  reactStrictMode: true,
  ...(staticExport ? { output: 'export' as const, images: { unoptimized: true } } : {}),
}

export default nextConfig
