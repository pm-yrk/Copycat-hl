# Copycat DB health and free-mode deployment notes

Render should use `/health` for container liveness. This endpoint now returns 200 without opening a database connection so the API can deploy even when Supabase is recovering or temporarily refusing DB connections.

Use `/db-health` when you want to check the Supabase/Postgres connection itself.

If the dashboard shows `Live data connection interrupted`, first check:

1. `https://hwt-api.onrender.com/health` — should be OK if the API container is up.
2. `https://hwt-api.onrender.com/db-health` — shows whether Supabase is accepting DB connections.
3. Supabase usage limits and service health.

Keep heavy workers paused in free mode until DB and egress usage are stable.
