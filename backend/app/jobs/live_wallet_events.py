from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import threading

import websockets
from sqlalchemy import text

from ..copycat_data_api import ensure_copycat_data_api, safe_float
from ..db import engine
from ..settings import get_settings

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

_LAST_EVENT_STATE_REFRESH: dict[str, float] = {}
_EVENT_STATE_REFRESH_MIN_SECONDS = 2.0
_STATE_WRITE_LOCK = threading.Lock()
_SCHEMA_INITIALISED = False


def _ensure_schema_once() -> None:
    global _SCHEMA_INITIALISED
    if _SCHEMA_INITIALISED:
        return
    ensure_copycat_data_api()
    _SCHEMA_INITIALISED = True


def _active_wallets(limit: int) -> list[str]:
    _ensure_schema_once()
    with engine.begin() as conn:
        rows = conn.execute(text('''
            SELECT wallet
            FROM qualified_wallets
            WHERE status='active' AND wallet ~* '^0x[0-9a-f]{40}$'
            ORDER BY rank ASC NULLS LAST, qualified_at_ms DESC NULLS LAST
            LIMIT :limit
        '''), {'limit': limit}).fetchall()
    return [str(r[0]).lower() for r in rows]



def _fetch_clearinghouse_state(wallet: str, info_url: str) -> dict[str, Any] | None:
    body = json.dumps({'type': 'clearinghouseState', 'user': wallet}).encode('utf-8')
    req = urllib.request.Request(info_url, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data if isinstance(data, dict) else None


def _position_rows(wallet: str, state: dict[str, Any], ts_ms: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    margin = state.get('marginSummary') if isinstance(state.get('marginSummary'), dict) else {}
    cross = state.get('crossMarginSummary') if isinstance(state.get('crossMarginSummary'), dict) else {}
    account_value = safe_float(margin.get('accountValue') or cross.get('accountValue'))
    rows: list[dict[str, Any]] = []
    for item in state.get('assetPositions') or []:
        if not isinstance(item, dict):
            continue
        pos = item.get('position') if isinstance(item.get('position'), dict) else item
        coin = str(pos.get('coin') or '').upper().strip()
        if not coin:
            continue
        size = safe_float(pos.get('szi'))
        value = abs(safe_float(pos.get('positionValue')))
        if value <= 0 and abs(size) <= 0:
            continue
        mark_px = (value / abs(size)) if abs(size) > 0 and value > 0 else safe_float(pos.get('markPx'), None)
        rows.append({
            'wallet': wallet,
            'coin': coin,
            'side': 'short' if size < 0 else 'long',
            'ts_ms': ts_ms,
            'size': size,
            'position_value_usd': value,
            'mark_px': mark_px,
            'entry_px': safe_float(pos.get('entryPx'), None),
            'unrealized_pnl_usd': safe_float(pos.get('unrealizedPnl')),
            'raw_json': json.dumps(pos)[:8000],
        })
    state_row = {
        'wallet': wallet,
        'ts_ms': ts_ms,
        'account_value_usd': account_value,
        'open_position_value_usd': sum(r['position_value_usd'] for r in rows),
        'open_positions': len(rows),
        'raw_json': json.dumps({k: state.get(k) for k in ('marginSummary', 'crossMarginSummary')})[:8000],
    }
    return state_row, rows


def _store_wallet_state(state_row: dict[str, Any], position_rows: list[dict[str, Any]]) -> None:
    _ensure_schema_once()
    # Keep wallet-state writes serial in this worker. This prevents the 5s
    # poll loop and event-triggered refreshes from updating/deleting the same
    # live tables at the same time.
    with _STATE_WRITE_LOCK:
        with engine.begin() as conn:
            conn.execute(text('''
                INSERT INTO copycat_live_wallet_states(
                  wallet, ts_ms, account_value_usd, open_position_value_usd, open_positions, source, raw_json, updated_at
                ) VALUES (
                  :wallet, :ts_ms, :account_value_usd, :open_position_value_usd, :open_positions,
                  'hyperliquid_info', CAST(:raw_json AS jsonb), now()
                )
                ON CONFLICT(wallet) DO UPDATE SET
                  ts_ms=excluded.ts_ms,
                  account_value_usd=excluded.account_value_usd,
                  open_position_value_usd=excluded.open_position_value_usd,
                  open_positions=excluded.open_positions,
                  source=excluded.source,
                  raw_json=excluded.raw_json,
                  updated_at=now()
            '''), state_row)
            conn.execute(text('DELETE FROM copycat_live_positions WHERE wallet=:wallet'), {'wallet': state_row['wallet']})
            if position_rows:
                conn.execute(text('''
                    INSERT INTO copycat_live_positions(
                      wallet, coin, side, ts_ms, size, position_value_usd, mark_px, entry_px,
                      unrealized_pnl_usd, source, raw_json, updated_at
                    ) VALUES (
                      :wallet, :coin, :side, :ts_ms, :size, :position_value_usd, :mark_px, :entry_px,
                      :unrealized_pnl_usd, 'hyperliquid_info', CAST(:raw_json AS jsonb), now()
                    )
                    ON CONFLICT(wallet, coin, side) DO UPDATE SET
                      ts_ms=excluded.ts_ms,
                      size=excluded.size,
                      position_value_usd=excluded.position_value_usd,
                      mark_px=excluded.mark_px,
                      entry_px=excluded.entry_px,
                      unrealized_pnl_usd=excluded.unrealized_pnl_usd,
                      source=excluded.source,
                      raw_json=excluded.raw_json,
                      updated_at=now()
                '''), position_rows)


def _poll_single_wallet_state(wallet: str) -> bool:
    settings = get_settings()
    state = _fetch_clearinghouse_state(wallet, settings.hl_info_url)
    if not state:
        return False
    ts_ms = int(time.time() * 1000)
    state_row, positions = _position_rows(wallet, state, ts_ms)
    _store_wallet_state(state_row, positions)
    return True


def _fetch_wallet_state_for_poll(wallet: str, info_url: str) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    state = _fetch_clearinghouse_state(wallet, info_url)
    if not state:
        raise RuntimeError('empty Hyperliquid clearinghouseState')
    ts_ms = int(time.time() * 1000)
    state_row, positions = _position_rows(wallet, state, ts_ms)
    return wallet, state_row, positions


def _poll_wallet_states_once(limit: int) -> dict[str, Any]:
    """Refresh live wallet state without making the dashboard wait ~80s.

    The previous version fetched and wrote 50 wallets one-by-one. In Render logs
    that made a "5 second" poll actually take ~78-80 seconds, so most wallets
    looked stale before the poll even finished. This version fetches Hyperliquid
    states concurrently, then writes to Postgres serially under the existing
    write lock so the database stays safe.
    """
    settings = get_settings()
    wallets = _active_wallets(limit)
    ok = 0
    errors: list[str] = []
    started = time.time()
    max_workers = max(1, min(int(getattr(settings, 'live_state_max_workers', 10) or 10), 16, len(wallets) or 1))
    fetched: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_wallet_state_for_poll, wallet, settings.hl_info_url): wallet for wallet in wallets}
        for future in as_completed(futures):
            wallet = futures[future]
            try:
                fetched.append(future.result())
            except Exception as exc:
                errors.append(f'{wallet[:8]}: {type(exc).__name__}')
                if len(errors) <= 3:
                    log.warning('failed to fetch live wallet state for %s: %s', wallet, exc)

    # Write in active-wallet order so the latest timestamps land coherently and
    # logs are easier to reason about.
    by_wallet = {wallet: (state_row, positions) for wallet, state_row, positions in fetched}
    for wallet in wallets:
        payload = by_wallet.get(wallet)
        if not payload:
            continue
        state_row, positions = payload
        try:
            _store_wallet_state(state_row, positions)
            ok += 1
        except Exception as exc:
            errors.append(f'{wallet[:8]}: {type(exc).__name__}')
            if len(errors) <= 3:
                log.warning('failed to store live wallet state for %s: %s', wallet, exc)

    return {
        'wallets_ok': ok,
        'wallets_total': len(wallets),
        'errors': errors[:10],
        'max_workers': max_workers,
        'elapsed_seconds': round(time.time() - started, 1),
    }


def _schedule_event_state_refresh(wallet: str) -> None:
    wallet = (wallet or '').lower().strip()
    if not wallet:
        return
    now = time.time()
    last = _LAST_EVENT_STATE_REFRESH.get(wallet, 0.0)
    if now - last < _EVENT_STATE_REFRESH_MIN_SECONDS:
        return
    _LAST_EVENT_STATE_REFRESH[wallet] = now

    async def _run() -> None:
        try:
            await asyncio.to_thread(_poll_single_wallet_state, wallet)
        except Exception as exc:
            log.warning('event-triggered live state refresh failed for %s: %s', wallet[:8], exc)

    try:
        asyncio.create_task(_run())
    except RuntimeError:
        # No running event loop; safe fallback for local/manual calls.
        try:
            _poll_single_wallet_state(wallet)
        except Exception as exc:
            log.warning('event-triggered live state refresh failed for %s: %s', wallet[:8], exc)


async def _state_poll_loop() -> None:
    settings = get_settings()
    interval = max(5, int(settings.live_state_poll_seconds or 5))
    limit = max(1, int(settings.live_state_wallet_limit or settings.live_event_wallet_limit or 50))
    while True:
        try:
            result = await asyncio.to_thread(_poll_wallet_states_once, limit)
            log.info('live state poll: %s', result)
        except Exception:
            log.exception('live wallet state poll failed')
        await asyncio.sleep(interval)


def _event_id(prefix: str, wallet: str, payload: dict[str, Any]) -> str:
    coin = payload.get('coin') or payload.get('order', {}).get('coin') or ''
    ts = payload.get('time') or payload.get('statusTimestamp') or payload.get('order', {}).get('timestamp') or int(time.time() * 1000)
    tid = payload.get('tid') or payload.get('oid') or payload.get('order', {}).get('oid') or payload.get('hash') or ''
    status = payload.get('status') or ''
    return f'{prefix}:{wallet}:{coin}:{ts}:{tid}:{status}'[:300]


def _store_event(row: dict[str, Any]) -> None:
    _ensure_schema_once()
    with engine.begin() as conn:
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


async def _handle_message(msg: dict[str, Any]) -> int:
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
        if stored and wallet:
            _schedule_event_state_refresh(wallet)
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
        if stored and wallet:
            _schedule_event_state_refresh(wallet)
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
                _schedule_event_state_refresh(user)
    elif channel == 'subscriptionResponse':
        log.info('subscription ack: %s', data)
    return stored


async def _websocket_loop() -> None:
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
                        n = await _handle_message(msg)
                        if n:
                            log.info('stored %s live wallet events', n)
                    except Exception:
                        log.exception('failed to handle Hyperliquid WS message')
                log.warning('Hyperliquid live event stream ended cleanly; reconnecting in 5s')
                await asyncio.sleep(5)
        except Exception:
            log.exception('Hyperliquid live event stream disconnected; reconnecting in 10s')
            await asyncio.sleep(10)


async def _run_forever() -> None:
    await asyncio.to_thread(_ensure_schema_once)
    await asyncio.gather(_websocket_loop(), _state_poll_loop())


def main() -> None:
    asyncio.run(_run_forever())


if __name__ == '__main__':
    main()
