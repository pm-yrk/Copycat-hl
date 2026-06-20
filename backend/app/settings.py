from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    database_url: str = 'postgresql+psycopg://postgres:postgres@localhost:5432/hwt'
    public_site_url: str = 'http://localhost:3000'
    api_base_url: str = 'http://localhost:8000'
    environment: str = 'local'

    hl_info_url: str = 'https://api.hyperliquid.xyz/info'
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
