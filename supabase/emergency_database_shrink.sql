-- Copycat emergency database shrink for Supabase Free.
-- Run in Supabase SQL Editor after temporarily pausing heavy workers.
-- This keeps only hot/current operational data and removes long history from Supabase.
-- If you need perfect historical backtests later, export/archive first; this intentionally deletes old rows.

-- 1) Keep only the latest 6 completed position snapshots.
WITH keep AS (
  SELECT ts_ms FROM (
    SELECT DISTINCT ts_ms FROM public.positions ORDER BY ts_ms DESC LIMIT 6
  ) k
)
DELETE FROM public.positions p
WHERE NOT EXISTS (SELECT 1 FROM keep WHERE keep.ts_ms = p.ts_ms);

-- 2) Keep only the latest 6 wallet snapshots per wallet.
WITH ranked AS (
  SELECT id, row_number() OVER (PARTITION BY wallet ORDER BY ts_ms DESC, id DESC) AS rn
  FROM public.wallet_snapshots
)
DELETE FROM public.wallet_snapshots ws
USING ranked r
WHERE ws.id = r.id AND r.rn > 6;

-- 3) Keep one day-ish of signal/target snapshots, depending on collection cadence.
WITH keep AS (
  SELECT ts_ms FROM (
    SELECT DISTINCT ts_ms FROM public.asset_signals ORDER BY ts_ms DESC LIMIT 288
  ) k
)
DELETE FROM public.asset_signals a
WHERE NOT EXISTS (SELECT 1 FROM keep WHERE keep.ts_ms = a.ts_ms);

WITH keep AS (
  SELECT ts_ms FROM (
    SELECT DISTINCT ts_ms FROM public.portfolio_targets ORDER BY ts_ms DESC LIMIT 288
  ) k
)
DELETE FROM public.portfolio_targets p
WHERE NOT EXISTS (SELECT 1 FROM keep WHERE keep.ts_ms = p.ts_ms);

-- 4) Keep only recent live events and owned fills in hot Supabase.
DELETE FROM public.copycat_live_events
WHERE ts_ms < (extract(epoch from now() - interval '2 days') * 1000)::bigint;

DELETE FROM public.owned_wallet_fills
WHERE ts_ms < (extract(epoch from now() - interval '14 days') * 1000)::bigint;

-- 5) Trim supporting history tables.
DELETE FROM public.copycat_market_snapshots cms
WHERE id IN (SELECT id FROM public.copycat_market_snapshots ORDER BY ts_ms DESC OFFSET 2000);

DELETE FROM public.owned_wallet_metric_history h
WHERE id IN (SELECT id FROM public.owned_wallet_metric_history ORDER BY ts_ms DESC OFFSET 2000);

DELETE FROM public.strategy_index_points s
WHERE id IN (SELECT id FROM public.strategy_index_points ORDER BY ts_ms DESC OFFSET 5000);

DELETE FROM public.collector_runs c
WHERE id IN (SELECT id FROM public.collector_runs ORDER BY ts_ms DESC OFFSET 500);

-- 6) Reclaim disk space. These lock each table while running, but they are needed to physically reduce size.
VACUUM FULL public.positions;
VACUUM FULL public.wallet_snapshots;
VACUUM FULL public.owned_wallet_fills;
VACUUM FULL public.asset_signals;
VACUUM FULL public.copycat_market_snapshots;
VACUUM FULL public.copycat_live_events;
VACUUM FULL public.owned_wallet_metric_history;
VACUUM FULL public.strategy_index_points;
VACUUM FULL public.portfolio_targets;
VACUUM FULL public.collector_runs;

-- 7) Check sizes again.
select
  schemaname,
  relname as table_name,
  pg_size_pretty(pg_total_relation_size(relid)) as total_size,
  pg_total_relation_size(relid) as bytes
from pg_catalog.pg_statio_user_tables
order by pg_total_relation_size(relid) desc
limit 30;
