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
