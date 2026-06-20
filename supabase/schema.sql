CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS profiles (
  user_id uuid PRIMARY KEY,
  email text,
  role text NOT NULL DEFAULT 'customer',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id bigserial PRIMARY KEY,
  user_id text NOT NULL,
  stripe_customer_id text,
  stripe_subscription_id text UNIQUE,
  status text NOT NULL DEFAULT 'inactive',
  current_period_end timestamptz,
  raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_status ON subscriptions(user_id, status);

CREATE TABLE IF NOT EXISTS wallet_candidates (
  wallet text PRIMARY KEY,
  label text,
  source text,
  notes text,
  discovered_at timestamptz NOT NULL DEFAULT now(),
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS wallet_scores (
  id bigserial PRIMARY KEY,
  ts_ms bigint NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  wallet text NOT NULL,
  score double precision NOT NULL,
  qualifies boolean NOT NULL,
  account_value_usd double precision,
  pnl_30d_usd double precision,
  pnl_all_time_usd double precision,
  max_drawdown_pct double precision,
  consistency_score double precision,
  anti_fluke_score double precision,
  metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_wallet_scores_wallet_ts ON wallet_scores(wallet, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_scores_score_ts ON wallet_scores(ts_ms DESC, score DESC);

CREATE TABLE IF NOT EXISTS qualified_wallets (
  wallet text PRIMARY KEY,
  rank integer NOT NULL,
  score double precision NOT NULL,
  qualified_at timestamptz NOT NULL DEFAULT now(),
  qualified_at_ms bigint NOT NULL,
  status text NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS wallet_snapshots (
  id bigserial PRIMARY KEY,
  ts_ms bigint NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  wallet text NOT NULL,
  account_value_usd double precision,
  total_margin_used_usd double precision,
  withdrawable_usd double precision,
  total_ntl_pos_usd double precision,
  raw_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_wallet_snapshots_wallet_ts ON wallet_snapshots(wallet, ts_ms DESC);

CREATE TABLE IF NOT EXISTS positions (
  id bigserial PRIMARY KEY,
  ts_ms bigint NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  wallet text NOT NULL,
  coin text NOT NULL,
  side text NOT NULL,
  size double precision NOT NULL,
  position_value_usd double precision NOT NULL,
  entry_px double precision,
  mark_px double precision,
  unrealized_pnl_usd double precision,
  return_on_equity double precision,
  leverage double precision,
  liquidation_px double precision,
  raw_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_positions_ts_coin ON positions(ts_ms DESC, coin);
CREATE INDEX IF NOT EXISTS idx_positions_wallet_ts ON positions(wallet, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_positions_coin_ts ON positions(coin, ts_ms DESC);

CREATE TABLE IF NOT EXISTS asset_signals (
  id bigserial PRIMARY KEY,
  ts_ms bigint NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  coin text NOT NULL,
  signal double precision NOT NULL,
  confidence text NOT NULL,
  wallets_long integer NOT NULL DEFAULT 0,
  wallets_short integer NOT NULL DEFAULT 0,
  wallets_flat integer NOT NULL DEFAULT 0,
  weighted_net_exposure double precision NOT NULL DEFAULT 0,
  exposure_change_lookback double precision NOT NULL DEFAULT 0,
  participation_rate double precision NOT NULL DEFAULT 0,
  value_long_usd double precision NOT NULL DEFAULT 0,
  value_short_usd double precision NOT NULL DEFAULT 0,
  net_value_usd double precision NOT NULL DEFAULT 0,
  total_tracked_value_usd double precision NOT NULL DEFAULT 0,
  value_long_pct_total double precision NOT NULL DEFAULT 0,
  value_short_pct_total double precision NOT NULL DEFAULT 0,
  net_buyer_count integer NOT NULL DEFAULT 0,
  bullish_value_flow_usd double precision NOT NULL DEFAULT 0,
  bearish_value_flow_usd double precision NOT NULL DEFAULT 0,
  net_value_flow_usd double precision NOT NULL DEFAULT 0,
  raw_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_asset_signals_ts_coin ON asset_signals(ts_ms DESC, coin);

CREATE TABLE IF NOT EXISTS portfolio_targets (
  id bigserial PRIMARY KEY,
  ts_ms bigint NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  coin text NOT NULL,
  target_weight double precision NOT NULL,
  signal double precision NOT NULL,
  confidence text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_portfolio_targets_ts ON portfolio_targets(ts_ms DESC);

CREATE TABLE IF NOT EXISTS notification_events (
  id bigserial PRIMARY KEY,
  ts_ms bigint NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  coin text NOT NULL,
  alert_type text NOT NULL,
  severity text NOT NULL,
  message text NOT NULL,
  key text NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_notification_events_ts ON notification_events(ts_ms DESC);

CREATE TABLE IF NOT EXISTS collector_runs (
  id bigserial PRIMARY KEY,
  ts_ms bigint NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  run_type text NOT NULL,
  status text NOT NULL,
  message text
);
CREATE INDEX IF NOT EXISTS idx_collector_runs_ts ON collector_runs(ts_ms DESC);

CREATE TABLE IF NOT EXISTS strategy_index_points (
  id bigserial PRIMARY KEY,
  ts_ms bigint NOT NULL UNIQUE,
  ts timestamptz NOT NULL DEFAULT now(),
  copycat_nav double precision NOT NULL,
  btc_nav double precision NOT NULL,
  eth_nav double precision NOT NULL,
  spx_nav double precision NOT NULL DEFAULT 100,
  copycat_return_pct double precision NOT NULL,
  btc_return_pct double precision NOT NULL,
  eth_return_pct double precision NOT NULL,
  spx_return_pct double precision NOT NULL DEFAULT 0,
  method text NOT NULL,
  weights_json jsonb NOT NULL,
  prices_json jsonb NOT NULL,
  benchmark_prices_json jsonb NOT NULL,
  metadata_json jsonb NOT NULL
);
ALTER TABLE strategy_index_points ADD COLUMN IF NOT EXISTS spx_nav double precision NOT NULL DEFAULT 100;
ALTER TABLE strategy_index_points ADD COLUMN IF NOT EXISTS spx_return_pct double precision NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_strategy_index_points_ts ON strategy_index_points(ts_ms DESC);

CREATE TABLE IF NOT EXISTS strategy_backtest_points (
  id bigserial PRIMARY KEY,
  ts_ms bigint NOT NULL UNIQUE,
  ts timestamptz NOT NULL DEFAULT now(),
  copycat_nav double precision NOT NULL,
  btc_nav double precision NOT NULL,
  eth_nav double precision NOT NULL,
  spx_nav double precision NOT NULL,
  copycat_return_pct double precision NOT NULL,
  btc_return_pct double precision NOT NULL,
  eth_return_pct double precision NOT NULL,
  spx_return_pct double precision NOT NULL,
  method text NOT NULL DEFAULT 'copycat_backtest_v1_weekly',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_strategy_backtest_points_ts ON strategy_backtest_points(ts_ms DESC);

-- Copycat owned Hyperliquid-native wallet intelligence tables.
-- These remove live-product dependence on paid Nansen discovery by storing our
-- own wallet fills and ranking metrics from Hyperliquid public endpoints.
CREATE TABLE IF NOT EXISTS owned_wallet_fills (
  id bigserial PRIMARY KEY,
  wallet text NOT NULL,
  tid text NOT NULL,
  ts_ms bigint NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  coin text,
  side text,
  direction text,
  px double precision,
  size double precision,
  closed_pnl_usd double precision,
  fee_usd double precision,
  raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(wallet, tid)
);
CREATE INDEX IF NOT EXISTS idx_owned_wallet_fills_wallet_ts ON owned_wallet_fills(wallet, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_owned_wallet_fills_ts ON owned_wallet_fills(ts_ms DESC);

CREATE TABLE IF NOT EXISTS owned_wallet_metrics (
  wallet text PRIMARY KEY,
  ts_ms bigint NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  source text NOT NULL DEFAULT 'hyperliquid_native',
  account_value_usd double precision NOT NULL DEFAULT 0,
  total_ntl_pos_usd double precision NOT NULL DEFAULT 0,
  pnl_day_usd double precision NOT NULL DEFAULT 0,
  pnl_30d_usd double precision NOT NULL DEFAULT 0,
  pnl_all_time_usd double precision NOT NULL DEFAULT 0,
  closed_pnl_lookback_usd double precision NOT NULL DEFAULT 0,
  fees_lookback_usd double precision NOT NULL DEFAULT 0,
  fills_lookback_count integer NOT NULL DEFAULT 0,
  active_days_observed integer NOT NULL DEFAULT 0,
  score double precision NOT NULL DEFAULT 0,
  qualifies boolean NOT NULL DEFAULT false,
  metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_owned_wallet_metrics_score ON owned_wallet_metrics(qualifies, score DESC);
CREATE INDEX IF NOT EXISTS idx_owned_wallet_metrics_ts ON owned_wallet_metrics(ts_ms DESC);

CREATE TABLE IF NOT EXISTS owned_wallet_metric_history (
  id bigserial PRIMARY KEY,
  wallet text NOT NULL,
  ts_ms bigint NOT NULL,
  ts timestamptz NOT NULL DEFAULT now(),
  source text NOT NULL DEFAULT 'hyperliquid_native',
  account_value_usd double precision NOT NULL DEFAULT 0,
  total_ntl_pos_usd double precision NOT NULL DEFAULT 0,
  pnl_day_usd double precision NOT NULL DEFAULT 0,
  pnl_30d_usd double precision NOT NULL DEFAULT 0,
  pnl_all_time_usd double precision NOT NULL DEFAULT 0,
  closed_pnl_lookback_usd double precision NOT NULL DEFAULT 0,
  fees_lookback_usd double precision NOT NULL DEFAULT 0,
  fills_lookback_count integer NOT NULL DEFAULT 0,
  active_days_observed integer NOT NULL DEFAULT 0,
  score double precision NOT NULL DEFAULT 0,
  qualifies boolean NOT NULL DEFAULT false,
  metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_owned_wallet_metric_history_wallet_ts ON owned_wallet_metric_history(wallet, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_owned_wallet_metric_history_ts ON owned_wallet_metric_history(ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_owned_wallet_metric_history_score ON owned_wallet_metric_history(ts_ms DESC, qualifies, score DESC);
