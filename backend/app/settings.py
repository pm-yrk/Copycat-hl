from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    # Do not default to localhost in deployed environments. If DATABASE_URL is
    # missing on a Render worker, failing loudly is safer than silently trying
    # 127.0.0.1:5432 and producing a long SQLAlchemy stack trace.
    database_url: str = ''
    supabase_db_url: str = ''
    postgres_url: str = ''
    postgres_prisma_url: str = ''
    postgres_url_non_pooling: str = ''

    public_site_url: str = 'http://localhost:3000'
    api_base_url: str = 'http://localhost:8000'
    environment: str = 'local'

    hl_info_url: str = 'https://api.hyperliquid.xyz/info'

    # Copycat owned Data API / live-event stream.
    copycat_api_key_salt: str = ''
    live_event_wallet_limit: int = 50
    live_event_subscribe_order_updates: bool = False
    # Same worker also polls current Hyperliquid wallet state so headline KPI
    # values can refresh faster than the full collector cycle. Defaults are safe
    # for Render Starter/Supabase and can be tuned from Render later.
    live_state_wallet_limit: int = 50
    live_state_poll_seconds: int = 5
    live_state_max_age_seconds: int = 45
    live_state_max_workers: int = 10
    live_signal_min_coverage_ratio: float = 0.80
    hl_ws_url: str = 'wss://api.hyperliquid.xyz/ws'
    nansen_api_key: str = ''
    nansen_base_url: str = 'https://api.nansen.ai'
    nansen_lookback_days: int = 30
    nansen_max_candidates: int = 500
    nansen_min_account_value_usd: float = 50_000
    nansen_min_total_pnl_usd: float = 1_000
    nansen_backtest_days: int = 400
    nansen_backtest_rebalance_days: int = 7
    nansen_backtest_max_candidates: int = 150
    nansen_backtest_min_wallets: int = 10
    nansen_backtest_min_rows: int = 26
    nansen_backtest_replace_existing: bool = True

    # Long-term independence: default daily wallet refresh uses our own
    # Hyperliquid-native wallet metrics. Nansen remains optional fallback only.
    wallet_discovery_provider: str = 'owned_first'
    owned_discovery_seed_wallets: str = ''
    owned_discovery_lookback_days: int = 30
    # Full owned universe limit. The scheduled daily job uses owned_refresh_limit
    # below so a large discovery setting cannot make the cron overlap forever.
    owned_discovery_refresh_limit: int = 500
    owned_refresh_limit: int = 75
    owned_refresh_max_seconds: int = 600
    owned_refresh_run_collection: bool = False
    owned_discovery_fetch_fills: bool = False
    owned_discovery_min_account_value_usd: float = 50_000
    owned_discovery_min_30d_pnl_usd: float = 1_000
    owned_discovery_min_all_time_pnl_usd: float = 0
    owned_discovery_min_score: float = 45
    owned_discovery_min_fills_lookback: int = 1
    owned_discovery_min_replacement_ratio: float = 0.80
    owned_discovery_request_delay_seconds: float = 0.25
    owned_backtest_rebalance_days: int = 7
    owned_backtest_min_wallets: int = 10
    owned_backtest_min_rows: int = 26
    owned_backtest_replace_existing: bool = True

    qualified_wallet_limit: int = 50
    collector_interval_seconds: int = 1
    collector_freshness_seconds: int = 180
    signal_lookback_minutes: int = 60
    min_wallets_for_signal: int = 5

    telegram_bot_token: str = ''
    telegram_chat_id: str = ''
    alert_min_net_buyers: int = 5
    alert_min_net_value_flow_usd: float = 1_000_000
    alert_cooldown_minutes: int = 60

    supabase_url: str = ''
    supabase_jwt_secret: str = ''
    allow_demo_auth: bool = False

    stripe_secret_key: str = ''
    stripe_webhook_secret: str = ''
    stripe_price_id_monthly: str = ''
    stripe_price_id_annual: str = ''


@lru_cache
def get_settings() -> Settings:
    return Settings()
