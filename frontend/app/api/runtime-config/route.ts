export const dynamic = 'force-static';
export const revalidate = false;

export async function GET() {
  return Response.json({
    supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL || '',
    supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '',
    apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL || 'https://hwt-api.onrender.com',
  }, { headers: { 'Cache-Control': 'no-store' } })
}