from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

import stripe
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .auth import get_current_user, require_active_subscription
from .db import fetch_all, fetch_one, execute, engine
from .settings import get_settings

settings = get_settings()
stripe.api_key = settings.stripe_secret_key or None

app = FastAPI(title='Hyper Wallet Tracker SaaS API')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_site_url, 'http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
def health():
    row = fetch_one('SELECT now() AS now')
    return {'status': 'ok', 'database': bool(row)}


@app.get('/api/me')
def me(user: dict = Depends(get_current_user)):
    return user


@app.get('/api/summary')
def summary(user: dict = Depends(require_active_subscription)):
    latest_signal_ts = fetch_one('SELECT max(ts_ms) AS ts_ms FROM asset_signals') or {'ts_ms': None}
    latest_pos_ts = fetch_one('SELECT max(ts_ms) AS ts_ms FROM positions') or {'ts_ms': None}
    latest_wallets = fetch_one("SELECT count(*) AS n FROM qualified_wallets WHERE status='active'") or {'n': 0}
    total_value = fetch_one(
        """
        WITH latest AS (
          SELECT DISTINCT ON (wallet) wallet, account_value_usd
          FROM wallet_snapshots ORDER BY wallet, ts_ms DESC
        ) SELECT COALESCE(sum(account_value_usd),0) AS total FROM latest
        """
    ) or {'total': 0}
    open_value = fetch_one(
        """
        WITH latest_ts AS (SELECT max(ts_ms) ts_ms FROM positions)
        SELECT COALESCE(sum(position_value_usd),0) AS total, count(*) AS positions
        FROM positions WHERE ts_ms=(SELECT ts_ms FROM latest_ts)
        """
    ) or {'total': 0, 'positions': 0}
    assets = fetch_one(
        """WITH latest_ts AS (SELECT max(ts_ms) ts_ms FROM asset_signals)
        SELECT count(*) AS n FROM asset_signals WHERE ts_ms=(SELECT ts_ms FROM latest_ts)"""
    ) or {'n': 0}
    return {
        'latest_signal_ts_ms': latest_signal_ts['ts_ms'],
        'latest_position_ts_ms': latest_pos_ts['ts_ms'],
        'qualified_wallets': latest_wallets['n'],
        'tracked_account_value_usd': float(total_value['total'] or 0),
        'tracked_open_position_value_usd': float(open_value['total'] or 0),
        'open_positions': open_value['positions'],
        'assets_with_signals': assets['n'],
    }


@app.get('/api/signals')
def signals(limit: int = 50, user: dict = Depends(require_active_subscription)):
    return fetch_all(
        """
        WITH latest_ts AS (SELECT max(ts_ms) AS ts_ms FROM asset_signals)
        SELECT * FROM asset_signals
        WHERE ts_ms=(SELECT ts_ms FROM latest_ts)
        ORDER BY signal DESC
        LIMIT :limit
        """,
        {'limit': limit},
    )


@app.get('/api/targets')
def targets(user: dict = Depends(require_active_subscription)):
    return fetch_all(
        """
        WITH latest_ts AS (SELECT max(ts_ms) AS ts_ms FROM portfolio_targets)
        SELECT * FROM portfolio_targets
        WHERE ts_ms=(SELECT ts_ms FROM latest_ts)
        ORDER BY target_weight DESC
        """
    )


@app.get('/api/flow')
def flow(limit: int = 50, user: dict = Depends(require_active_subscription)):
    return fetch_all(
        """
        WITH latest_ts AS (SELECT max(ts_ms) AS ts_ms FROM asset_signals)
        SELECT coin, signal, confidence, wallets_long, wallets_short, wallets_flat,
               value_long_usd, value_short_usd, net_value_usd,
               value_long_pct_total, value_short_pct_total,
               net_buyer_count, bullish_value_flow_usd, bearish_value_flow_usd, net_value_flow_usd
        FROM asset_signals
        WHERE ts_ms=(SELECT ts_ms FROM latest_ts)
        ORDER BY abs(net_value_flow_usd) DESC NULLS LAST
        LIMIT :limit
        """,
        {'limit': limit},
    )


@app.get('/api/wallets')
def wallets(limit: int = 100, user: dict = Depends(require_active_subscription)):
    return fetch_all(
        """
        SELECT q.rank, q.wallet, q.score, ws.account_value_usd, ws.pnl_30d_usd,
               ws.pnl_all_time_usd, ws.max_drawdown_pct, q.qualified_at
        FROM qualified_wallets q
        LEFT JOIN LATERAL (
          SELECT * FROM wallet_scores s WHERE s.wallet=q.wallet ORDER BY s.ts_ms DESC LIMIT 1
        ) ws ON true
        WHERE q.status='active'
        ORDER BY q.rank ASC
        LIMIT :limit
        """,
        {'limit': limit},
    )


@app.get('/api/runs')
def runs(limit: int = 30, user: dict = Depends(require_active_subscription)):
    return fetch_all('SELECT * FROM collector_runs ORDER BY ts_ms DESC LIMIT :limit', {'limit': limit})


@app.get('/api/recent-orders')
def recent_orders(limit: int = 3, user: dict = Depends(require_active_subscription)):
    """Derived recent order tape.

    Hyperliquid order events are not stored directly yet, so this endpoint derives the
    customer-facing "recent orders" tape from the latest two position snapshots for
    the active qualified wallet cohort. It surfaces the largest new/increased/reduced
    exposures so the dashboard updates as the collector runs.
    """
    rows = fetch_all(
        """
        WITH ordered_ts AS (
          SELECT DISTINCT ts_ms FROM positions ORDER BY ts_ms DESC LIMIT 2
        ), latest_ts AS (
          SELECT max(ts_ms) AS ts_ms FROM ordered_ts
        ), previous_ts AS (
          SELECT min(ts_ms) AS ts_ms FROM ordered_ts
        ), latest AS (
          SELECT p.* FROM positions p WHERE p.ts_ms=(SELECT ts_ms FROM latest_ts)
        ), previous AS (
          SELECT p.* FROM positions p WHERE p.ts_ms=(SELECT ts_ms FROM previous_ts)
        )
        SELECT l.ts_ms, l.wallet, l.coin, l.side,
               COALESCE(l.position_value_usd,0) - COALESCE(p.position_value_usd,0) AS delta_value_usd,
               COALESCE(l.position_value_usd,0) AS position_value_usd,
               COALESCE(l.size,0) - COALESCE(p.size,0) AS delta_size
        FROM latest l
        LEFT JOIN previous p ON p.wallet=l.wallet AND p.coin=l.coin AND lower(p.side)=lower(l.side)
        WHERE abs(COALESCE(l.position_value_usd,0) - COALESCE(p.position_value_usd,0)) > 0
        ORDER BY abs(COALESCE(l.position_value_usd,0) - COALESCE(p.position_value_usd,0)) DESC NULLS LAST
        LIMIT :limit
        """,
        {'limit': limit},
    )
    out = []
    for r in rows:
        side_raw = str(r.get('side') or '').lower()
        delta = float(r.get('delta_value_usd') or 0)
        if side_raw.startswith('short'):
            side = 'Short' if delta >= 0 else 'Cover'
        else:
            side = 'Long' if delta >= 0 else 'Reduce'
        wallet = r.get('wallet') or ''
        out.append({
            'ts_ms': r.get('ts_ms'),
            'wallet': wallet,
            'wallet_label': f"Wallet {wallet[:4]}…{wallet[-4:]}" if wallet else 'Wallet',
            'coin': r.get('coin'),
            'side': side,
            'delta_value_usd': delta,
            'position_value_usd': float(r.get('position_value_usd') or 0),
        })
    return out


_ICON_CACHE: dict[str, tuple[float, str | None]] = {}
_ICON_TTL_SECONDS = 60 * 60 * 24 * 7
_CG_ID_OVERRIDES = {
    'BTC': 'bitcoin', 'WBTC': 'wrapped-bitcoin', 'CBTC': 'coinbase-wrapped-btc',
    'ETH': 'ethereum', 'SOL': 'solana', 'HYPE': 'hyperliquid', 'ZEC': 'zcash',
    'NEAR': 'near', 'AAVE': 'aave', 'TRX': 'tron', 'XRP': 'ripple',
    'USDC': 'usd-coin', 'USDC/CASH': 'usd-coin', 'USDT': 'tether', 'USDS': 'usds',
    'WLD': 'worldcoin-wld', 'ARB': 'arbitrum', 'AVAX': 'avalanche-2', 'BNB': 'binancecoin',
    'DOGE': 'dogecoin', 'PENGU': 'pudgy-penguins', 'ENA': 'ethena', 'ONDO': 'ondo-finance',
    'FET': 'fetch-ai', 'LTC': 'litecoin', 'LINK': 'chainlink', 'UNI': 'uniswap',
    'APT': 'aptos', 'OP': 'optimism', 'SUI': 'sui', 'DOT': 'polkadot', 'FIL': 'filecoin',
    'ATOM': 'cosmos', 'INJ': 'injective-protocol', 'JUP': 'jupiter-exchange-solana',
    'TAO': 'bittensor', 'MNT': 'mantle', 'SEI': 'sei-network', 'BLUR': 'blur',
    'ZRO': 'layerzero', 'EIGEN': 'eigenlayer', 'STRK': 'starknet', 'XLM': 'stellar',
    'XAI': 'xai', 'FARTCOIN': 'fartcoin', 'VIRTUAL': 'virtual-protocol',
    'PENDLE': 'pendle', 'KAS': 'kaspa', 'DYDX': 'dydx-chain', 'AERO': 'aerodrome-finance',
    'BONK': 'bonk', 'KBONK': 'bonk', 'GRASS': 'grass', 'KAITO': 'kaito',
    'MELANIA': 'melania-meme', 'MOODENG': 'moo-deng', 'BERA': 'berachain-bera',
}
_CG_QUERY_OVERRIDES = {
    'HYPE': 'hyperliquid', 'MELANIA': 'melania meme', 'KBONK': 'bonk', 'BONK': 'bonk',
    'WLD': 'worldcoin', 'PENGU': 'pudgy penguins', 'KAITO': 'kaito', 'GRASS': 'grass',
    'MOODENG': 'moo deng', 'FARTCOIN': 'fartcoin', 'VIRTUAL': 'virtuals protocol',
    'LAYER': 'solayer', 'USDC/CASH': 'usd coin', 'USDS': 'usds',
}

def _open_json(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Copycat/1.0 (+https://copycat.hl)',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=6) as res:
            return json.loads(res.read().decode('utf-8'))
    except Exception:
        return None

def _coingecko_icon_for_symbol(symbol: str) -> str | None:
    symbol = (symbol or '').upper().strip()
    if not symbol:
        return None
    now = time.time()
    cached = _ICON_CACHE.get(symbol)
    if cached and now - cached[0] < _ICON_TTL_SECONDS:
        return cached[1]

    image = None
    coin_id = _CG_ID_OVERRIDES.get(symbol)
    if coin_id:
        # Bulk market endpoint gives a canonical current image URL for a CoinGecko ID.
        url = 'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=' + urllib.parse.quote(coin_id)
        payload = _open_json(url)
        if isinstance(payload, list) and payload:
            image = payload[0].get('image')

    if not image:
        query = _CG_QUERY_OVERRIDES.get(symbol, symbol)
        url = 'https://api.coingecko.com/api/v3/search?query=' + urllib.parse.quote(query)
        payload = _open_json(url)
        if isinstance(payload, dict):
            coins = payload.get('coins') or []
            def rank_key(coin: dict) -> int:
                rank = coin.get('market_cap_rank')
                return int(rank) if isinstance(rank, int) and rank > 0 else 10_000_000
            exact = [coin for coin in coins if str(coin.get('symbol') or '').upper() == symbol]
            chosen_pool = exact or coins
            chosen = sorted(chosen_pool, key=rank_key)[0] if chosen_pool else None
            if chosen:
                image = chosen.get('large') or chosen.get('small') or chosen.get('thumb')

    _ICON_CACHE[symbol] = (now, image)
    return image

@app.get('/api/token-icons')
def token_icons(symbols: str = ''):
    requested = []
    for raw in symbols.split(','):
        sym = raw.strip().upper()
        if sym and sym not in requested:
            requested.append(sym)
    requested = requested[:120]
    return {'icons': {sym: _coingecko_icon_for_symbol(sym) for sym in requested}}


@app.post('/api/billing/create-checkout-session')
def create_checkout_session(body: dict, user: dict = Depends(get_current_user)):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail='Stripe not configured')
    interval = body.get('interval', 'monthly')
    price_id = settings.stripe_price_id_annual if interval == 'annual' else settings.stripe_price_id_monthly
    if not price_id:
        raise HTTPException(status_code=500, detail='Stripe price ID missing')
    session = stripe.checkout.Session.create(
        mode='subscription',
        payment_method_types=['card'],
        line_items=[{'price': price_id, 'quantity': 1}],
        success_url=f'{settings.public_site_url}/dashboard?checkout=success',
        cancel_url=f'{settings.public_site_url}/pricing?checkout=cancelled',
        client_reference_id=user['sub'],
        customer_email=user.get('email'),
        metadata={'supabase_user_id': user['sub']},
    )
    return {'url': session.url}


@app.post('/api/stripe/webhook')
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get('stripe-signature')
    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
        except Exception as exc:
            raise HTTPException(status_code=400, detail='Invalid Stripe webhook') from exc
    else:
        event = await request.json()

    etype = event.get('type')
    data = event.get('data', {}).get('object', {})
    if etype in ('checkout.session.completed', 'customer.subscription.updated', 'customer.subscription.deleted'):
        user_id = data.get('client_reference_id') or data.get('metadata', {}).get('supabase_user_id')
        subscription_id = data.get('subscription') or data.get('id')
        customer_id = data.get('customer')
        status = data.get('status') or 'active'
        if user_id:
            execute(
                """
                INSERT INTO subscriptions(user_id, stripe_customer_id, stripe_subscription_id, status, raw_json)
                VALUES (:user_id, :customer_id, :subscription_id, :status, CAST(:raw_json AS jsonb))
                ON CONFLICT (stripe_subscription_id) DO UPDATE SET
                  status=excluded.status,
                  raw_json=excluded.raw_json,
                  updated_at=now()
                """,
                {
                    'user_id': user_id,
                    'customer_id': customer_id,
                    'subscription_id': subscription_id or f'session_{data.get("id")}',
                    'status': status,
                    'raw_json': str(data).replace("'", '"'),
                },
            )
    return {'received': True}
