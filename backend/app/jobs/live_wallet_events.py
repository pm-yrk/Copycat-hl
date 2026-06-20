from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import websockets
from sqlalchemy import text

from ..copycat_data_api import ensure_copycat_data_api_tables, safe_float
from ..db import engine
from ..settings import get_settings

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def _active_wallets(limit: int) -> list[str]:
    with engine.begin() as conn:
        ensure_copycat_data_api_tables(conn)
        rows = conn.execute(text('''
            SELECT wallet
            FROM qualified_wallets
            WHERE status='active' AND wallet ~* '^0x[0-9a-f]{40}$'
            ORDER BY rank ASC NULLS LAST, qualified_at_ms DESC NULLS LAST
            LIMIT :limit
        '''), {'limit': limit}).fetchall()
    return [str(r[0]).lower() for r in rows]


def _event_id(prefix: str, wallet: str, payload: dict[str, Any]) -> str:
    coin = payload.get('coin') or payload.get('order', {}).get('coin') or ''
    ts = payload.get('time') or payload.get('statusTimestamp') or payload.get('order', {}).get('timestamp') or int(time.time() * 1000)
    tid = payload.get('tid') or payload.get('oid') or payload.get('order', {}).get('oid') or payload.get('hash') or ''
    status = payload.get('status') or ''
    return f'{prefix}:{wallet}:{coin}:{ts}:{tid}:{status}'[:300]


def _store_event(row: dict[str, Any]) -> None:
    with engine.begin() as conn:
        ensure_copycat_data_api_tables(conn)
        conn.execute(text('''
            INSERT INTO copycat_live_events(
              event_id,wallet,event_type,ts_ms,coin,side,direction,px,size,notional_usd,
              closed_pnl_usd,fee_usd,source,raw_json
            ) VALUES (
              :event_id,:wallet,:event_type,:ts_ms,:coin,:side,:direction,:px,:size,:notional_usd,
              :closed_pnl_usd,:fee_usd,'hyperliquid_ws',CAST(:raw_json AS jsonb)
            )
            ON CONFLICT(event_id) DO NOTHING
        '''), row)


def _normalise_fill(wallet: str, fill: dict[str, Any]) -> dict[str, Any]:
    px = safe_float(fill.get('px'))
    size = safe_float(fill.get('sz'))
    return {
        'event_id': _event_id('fill', wallet, fill),
        'wallet': wallet,
        'event_type': 'fill',
        'ts_ms': int(fill.get('time') or time.time() * 1000),
        'coin': fill.get('coin'),
        'side': fill.get('side'),
        'direction': fill.get('dir') or fill.get('side'),
        'px': px,
        'size': size,
        'notional_usd': abs(px * size),
        'closed_pnl_usd': safe_float(fill.get('closedPnl')),
        'fee_usd': safe_float(fill.get('fee')),
        'raw_json': json.dumps(fill)[:8000],
    }


def _normalise_order(wallet: str, update: dict[str, Any]) -> dict[str, Any] | None:
    order = update.get('order') if isinstance(update.get('order'), dict) else update
    if not isinstance(order, dict):
        return None
    px = safe_float(order.get('limitPx'))
    size = safe_float(order.get('sz') or order.get('origSz'))
    ts_ms = int(update.get('statusTimestamp') or order.get('timestamp') or time.time() * 1000)
    status = str(update.get('status') or 'update')
    return {
        'event_id': _event_id('order', wallet, {**update, 'order': order}),
        'wallet': wallet,
        'event_type': 'order',
        'ts_ms': ts_ms,
        'coin': order.get('coin'),
        'side': order.get('side'),
        'direction': status,
        'px': px,
        'size': size,
        'notional_usd': abs(px * size),
        'closed_pnl_usd': 0,
        'fee_usd': 0,
        'raw_json': json.dumps(update)[:8000],
    }


def _handle_message(msg: dict[str, Any]) -> int:
    channel = msg.get('channel')
    data = msg.get('data')
    stored = 0
    if channel == 'userFills' and isinstance(data, dict):
        if data.get('isSnapshot') is True:
            return 0
        wallet = str(data.get('user') or '').lower()
        for fill in data.get('fills') or []:
            if isinstance(fill, dict) and wallet:
                _store_event(_normalise_fill(wallet, fill))
                stored += 1
    elif channel == 'userEvents' and isinstance(data, dict):
        wallet = str(data.get('user') or data.get('userAddress') or '').lower()
        # Some Hyperliquid user event messages nest fills directly under data.
        fills = data.get('fills')
        if not fills and isinstance(data.get('event'), dict):
            fills = data['event'].get('fills')
        if isinstance(fills, list) and wallet:
            for fill in fills:
                if isinstance(fill, dict):
                    _store_event(_normalise_fill(wallet, fill))
                    stored += 1
    elif channel == 'orderUpdates' and isinstance(data, list):
        for update in data:
            if not isinstance(update, dict):
                continue
            user = str(update.get('user') or update.get('wallet') or '').lower()
            # orderUpdates does not always echo the user. The subscription data is not echoed here,
            # so store only messages that include a user to avoid misattribution.
            if not user:
                continue
            row = _normalise_order(user, update)
            if row:
                _store_event(row)
                stored += 1
    elif channel == 'subscriptionResponse':
        log.info('subscription ack: %s', data)
    return stored


async def _run_forever() -> None:
    settings = get_settings()
    limit = max(1, int(settings.live_event_wallet_limit))
    while True:
        wallets = _active_wallets(limit)
        if not wallets:
            log.warning('No active wallets for live event subscriptions; retrying in 30s')
            await asyncio.sleep(30)
            continue
        log.info('Subscribing to Hyperliquid live events for %s wallets', len(wallets))
        try:
            async with websockets.connect(settings.hl_ws_url, ping_interval=20, ping_timeout=20, close_timeout=10) as ws:
                for wallet in wallets:
                    await ws.send(json.dumps({'method': 'subscribe', 'subscription': {'type': 'userFills', 'user': wallet, 'aggregateByTime': True}}))
                    if settings.live_event_subscribe_order_updates:
                        await ws.send(json.dumps({'method': 'subscribe', 'subscription': {'type': 'orderUpdates', 'user': wallet}}))
                    await asyncio.sleep(0.02)
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        n = _handle_message(msg)
                        if n:
                            log.info('stored %s live wallet events', n)
                    except Exception:
                        log.exception('failed to handle Hyperliquid WS message')
        except Exception:
            log.exception('Hyperliquid live event stream disconnected; reconnecting in 10s')
            await asyncio.sleep(10)


def main() -> None:
    asyncio.run(_run_forever())


if __name__ == '__main__':
    main()
