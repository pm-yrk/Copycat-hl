# copycat.hl Docker npm build fix

This patch changes the frontend Dockerfile to use Node 20 LTS and a more reliable npm install step.
It keeps the build-time Supabase placeholders from the previous patch.
