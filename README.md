# copycat.hl design build fix

This small patch keeps the new copycat.hl design but prevents Next.js Docker build from failing with `supabaseUrl is required` during prerender.

Files changed:
- frontend/lib/supabase.ts: dynamically imports Supabase at runtime only.
- frontend/Dockerfile: adds safe build-time placeholders. Render runtime env vars still control the real live site.
