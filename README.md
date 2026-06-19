# Copycat Nansen credit-safe refresh patch

This patch prevents the daily refresh cron from failing when Nansen returns `403 Insufficient credits`.

What changed:

- If Nansen candidate discovery fails, the job continues using cached candidates/current active cohort.
- The current active top-50 cohort is never wiped just because external candidate discovery fails.
- If Ranking V2 qualifies too few wallets, the last known good cohort stays active.
- The cron exits cleanly and records warnings in `collector_runs` instead of crashing.

This does not add Nansen credits. It makes Copycat resilient while you wait for credits to renew or upgrade the Nansen plan.
