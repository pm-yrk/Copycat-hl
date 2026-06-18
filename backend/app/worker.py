from __future__ import annotations

import json, math, time, logging
from datetime import date, timedelta
from typing import Any

import requests
from sqlalchemy import text

from .db import engine
from .settings import get_settings

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def now_ms() -> int:
    return int(time.time() * 1000)


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None: return default
        return float(x)
    except Exception:
        return default


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def is_address(s: str) -> bool:
    return isinstance(s, str) and s.startswith('0x') and len(s) == 42


class Hyperliquid:
    def __init__(self):
        self.settings = get_settings()
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

    def info(self, payload: dict[str, Any]) -> Any:
        last = None
        for attempt in range(6):
            r = self.session.post(self.settings.hl_info_url, json=payload, timeout=20)
            if r.status_code == 429:
                last = RuntimeError(f'Hyperliquid 429: {r.text[:200]}')
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f'Hyperliquid HTTP {r.status_code}: {r.text[:500]}')
            return r.json()
        raise last or RuntimeError('Hyperliquid request failed')

    def clearinghouse_state(self, wallet: str):
        return self.info({'type': 'clearinghouseState', 'user': wallet})

    def portfolio(self, wallet: str):
        return self.info({'type': 'portfolio', 'user': wallet})

    def user_role(self, wallet: str):
        return self.info({'type': 'userRole', 'user': wallet})


class Nansen:
    def __init__(self):
        self.settings = get_settings()
        self.session = requests.Session()
        self.session.headers.update({
            'apiKey': self.settings.nansen_api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

    def leaderboard(self, page: int, per_page: int = 100) -> Any:
        end = date.today()
        start = end - timedelta(days=self.settings.nansen_lookback_days)
        payload = {
            'date': {'from': start.isoformat(), 'to': end.isoformat()},
            'pagination': {'page': page, 'per_page': per_page},
            'filters': {
                'account_value': {'min': self.settings.nansen_min_account_value_usd},
                'total_pnl': {'min': self.settings.nansen_min_total_pnl_usd},
            },
            'order_by': [{'field': 'total_pnl', 'direction': 'DESC'}],
        }
        url = f'{self.settings.nansen_base_url.rstrip("/")}/api/v1/perp-leaderboard'
        r = self.session.post(url, json=payload, timeout=40)
        if r.status_code == 422:
            payload.pop('order_by', None)
            r = self.session.post(url, json=payload, timeout=40)
        if r.status_code >= 400:
            raise RuntimeError(f'Nansen HTTP {r.status_code}: {r.text[:500]}')
        return r.json()


def extract_records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    buckets = []
    for key in ('data','records','items','results','leaderboard','rows'):
        if key in data: buckets.append(data[key])
    if isinstance(data.get('data'), dict):
        for key in ('records','items','results','leaderboard','rows'):
            if key in data['data']: buckets.append(data['data'][key])
    out=[]
    for b in buckets:
        if isinstance(b, list): out += [x for x in b if isinstance(x, dict)]
        elif isinstance(b, dict): out += [x for x in b.values() if isinstance(x, dict)]
    return out


def find_address(v: Any, depth: int = 3) -> str | None:
    if depth < 0: return None
    if isinstance(v, str) and is_address(v): return v.lower()
    if isinstance(v, dict):
        for k in ('trader_address','traderAddress','address','wallet','wallet_address','walletAddress','user','account'):
            if k in v:
                found = find_address(v[k], depth-1)
                if found: return found
        for vv in v.values():
            found = find_address(vv, depth-1)
            if found: return found
    if isinstance(v, list):
        for vv in v[:10]:
            found = find_address(vv, depth-1)
            if found: return found
    return None


def discover_candidates() -> int:
    settings = get_settings()
    if not settings.nansen_api_key:
        raise RuntimeError('NANSEN_API_KEY missing')
    client = Nansen()
    max_candidates = settings.nansen_max_candidates
    seen, rows = set(), []
    pages = max(1, math.ceil(max_candidates / 100))
    for page in range(1, pages + 1):
        log.info('Fetching Nansen leaderboard page %s/%s', page, pages)
        data = client.leaderboard(page=page, per_page=100)
        records = extract_records(data)
        if not records:
            break
        for rec in records:
            wallet = find_address(rec)
            if wallet and wallet not in seen:
                seen.add(wallet)
                rows.append({'wallet': wallet, 'source': 'nansen_perp_leaderboard', 'label': '', 'notes': json.dumps(rec)[:1000]})
                if len(rows) >= max_candidates: break
        if len(rows) >= max_candidates: break
        time.sleep(0.25)
    with engine.begin() as conn:
        for r in rows:
            conn.execute(text('''
                INSERT INTO wallet_candidates(wallet,label,source,notes,active)
                VALUES(:wallet,:label,:source,:notes,true)
                ON CONFLICT(wallet) DO UPDATE SET source=excluded.source, notes=excluded.notes, active=true
            '''), r)
        insert_run(conn, 'discover_candidates', 'ok', f'imported_or_updated={len(rows)}')
    return len(rows)


def extract_margin_summary(state: dict[str, Any]) -> dict[str, float]:
    ms = state.get('marginSummary') or state.get('crossMarginSummary') or {}
    return {
        'account_value_usd': safe_float(ms.get('accountValue')),
        'total_margin_used_usd': safe_float(ms.get('totalMarginUsed')),
        'withdrawable_usd': safe_float(state.get('withdrawable')),
        'total_ntl_pos_usd': safe_float(ms.get('totalNtlPos')),
    }


def normalize_positions(wallet: str, ts: int, state: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]
    for item in state.get('assetPositions') or []:
        p = item.get('position') or item
        coin = p.get('coin')
        szi = safe_float(p.get('szi'))
        if not coin or szi == 0: continue
        value = abs(safe_float(p.get('positionValue')))
        out.append({
            'ts_ms': ts, 'wallet': wallet, 'coin': coin, 'side': 'long' if szi > 0 else 'short',
            'size': abs(szi), 'position_value_usd': value,
            'entry_px': safe_float(p.get('entryPx'), None), 'mark_px': safe_float(p.get('markPx'), None),
            'unrealized_pnl_usd': safe_float(p.get('unrealizedPnl'), None),
            'return_on_equity': safe_float(p.get('returnOnEquity'), None),
            'leverage': safe_float((p.get('leverage') or {}).get('value') if isinstance(p.get('leverage'), dict) else p.get('leverage'), None),
            'liquidation_px': safe_float(p.get('liquidationPx'), None),
            'raw_json': json.dumps(p),
        })
    return out


def portfolio_pnl(portfolio: Any) -> dict[str, float]:
    # Defensive extraction: Hyperliquid portfolio response shape can vary.
    windows = {'day':0.0, 'week':0.0, 'month':0.0, 'allTime':0.0}
    if isinstance(portfolio, list):
        for row in portfolio:
            if isinstance(row, list) and len(row) >= 2:
                key, data = row[0], row[1]
                if isinstance(data, dict):
                    windows[str(key)] = safe_float(data.get('pnl') or data.get('vlm') or data.get('accountValueHistory', [[0,0]])[-1][-1])
            elif isinstance(row, dict):
                key = row.get('period') or row.get('window') or row.get('name')
                if key: windows[str(key)] = safe_float(row.get('pnl') or row.get('profit') or row.get('totalPnl'))
    elif isinstance(portfolio, dict):
        for k, v in portfolio.items():
            if isinstance(v, dict): windows[str(k)] = safe_float(v.get('pnl') or v.get('totalPnl'))
            else: windows[str(k)] = safe_float(v)
    vals = [v for v in windows.values()]
    positive = sum(1 for v in vals if v > 0)
    max_share = max([abs(v) for v in vals] or [0]) / max(1.0, sum(abs(v) for v in vals))
    return {
        'pnl_day_usd': windows.get('day', 0.0),
        'pnl_30d_usd': windows.get('month', windows.get('30d', 0.0)),
        'pnl_all_time_usd': windows.get('allTime', windows.get('all_time', 0.0)),
        'positive_windows': positive,
        'max_single_window_pnl_share': max_share,
        'max_drawdown_pct': 0.0,
    }


def wallet_score(wallet: str, state: dict[str, Any], portfolio: Any) -> dict[str, Any]:
    ts = now_ms()
    summary = extract_margin_summary(state)
    account_value = summary['account_value_usd']
    positions = normalize_positions(wallet, ts, state)
    pnl = portfolio_pnl(portfolio)
    pnl30 = pnl['pnl_30d_usd']
    pnlall = pnl['pnl_all_time_usd']
    pnl_pct = (0.65 * pnl30 + 0.35 * pnlall) / max(account_value, 1)
    pnl_score = clamp(50 + 50 * math.tanh(pnl_pct * 4), 0, 100)
    consistency = clamp((pnl['positive_windows'] / 4) * 100, 0, 100)
    capital = clamp(20 * math.log10(max(account_value, 1)) - 60, 0, 100)
    recency = clamp(50 + 50 * math.tanh((pnl30 / max(account_value, 1)) * 5), 0, 100)
    largest = max([p['position_value_usd'] for p in positions] or [0])
    total_pos = sum(p['position_value_usd'] for p in positions) or 1
    anti_fluke = 100
    if pnl['max_single_window_pnl_share'] > 0.70: anti_fluke -= 35
    if largest / total_pos > 0.80: anti_fluke -= 30
    score = .30*pnl_score + .20*consistency + .15*capital + .15*recency + .10*100 + .10*anti_fluke
    qualifies = account_value >= 50_000 and abs(pnl30) >= 1_000 and consistency >= 25 and score >= 35
    return {
        'ts_ms': ts, 'wallet': wallet, 'score': round(score,3), 'qualifies': qualifies,
        'account_value_usd': account_value, 'pnl_30d_usd': pnl30, 'pnl_all_time_usd': pnlall,
        'max_drawdown_pct': pnl['max_drawdown_pct'], 'consistency_score': consistency,
        'anti_fluke_score': anti_fluke, 'metrics_json': json.dumps({**summary, **pnl, 'position_count': len(positions)})
    }


def score_wallets(limit: int | None = None) -> int:
    settings = get_settings()
    hl = Hyperliquid()
    with engine.begin() as conn:
        wallets = [r[0] for r in conn.execute(text('SELECT wallet FROM wallet_candidates WHERE active=true ORDER BY discovered_at DESC')).fetchall()]
    scored = []
    for i, wallet in enumerate(wallets, start=1):
        log.info('Scoring %s/%s %s', i, len(wallets), wallet)
        try:
            state = hl.clearinghouse_state(wallet)
            portfolio = hl.portfolio(wallet)
            score = wallet_score(wallet, state, portfolio)
            scored.append(score)
            with engine.begin() as conn:
                conn.execute(text('''
                    INSERT INTO wallet_scores(ts_ms,wallet,score,qualifies,account_value_usd,pnl_30d_usd,pnl_all_time_usd,max_drawdown_pct,consistency_score,anti_fluke_score,metrics_json)
                    VALUES(:ts_ms,:wallet,:score,:qualifies,:account_value_usd,:pnl_30d_usd,:pnl_all_time_usd,:max_drawdown_pct,:consistency_score,:anti_fluke_score,CAST(:metrics_json AS jsonb))
                '''), score)
        except Exception as exc:
            log.exception('Failed scoring wallet %s: %s', wallet, exc)
        time.sleep(0.5)
    qualified = [s for s in scored if s['qualifies']]
    qualified.sort(key=lambda x: x['score'], reverse=True)
    qualified = qualified[:(limit or settings.qualified_wallet_limit)]
    ts = now_ms()
    with engine.begin() as conn:
        conn.execute(text("UPDATE qualified_wallets SET status='inactive'"))
        for rank, s in enumerate(qualified, start=1):
            conn.execute(text('''
                INSERT INTO qualified_wallets(wallet,rank,score,qualified_at_ms,status)
                VALUES(:wallet,:rank,:score,:ts,'active')
                ON CONFLICT(wallet) DO UPDATE SET rank=excluded.rank, score=excluded.score, qualified_at=now(), qualified_at_ms=excluded.qualified_at_ms, status='active'
            '''), {'wallet': s['wallet'], 'rank': rank, 'score': s['score'], 'ts': ts})
        insert_run(conn, 'score_wallets', 'ok', f'scored={len(scored)} qualified={len(qualified)}')
    return len(scored)


def insert_run(conn, run_type: str, status: str, message: str=''):
    conn.execute(text('INSERT INTO collector_runs(ts_ms,run_type,status,message) VALUES(:ts,:type,:status,:message)'), {'ts': now_ms(), 'type': run_type, 'status': status, 'message': message})


def collect_once() -> dict[str, Any]:
    hl = Hyperliquid()
    ts = now_ms()
    with engine.begin() as conn:
        wallets = [r[0] for r in conn.execute(text("SELECT wallet FROM qualified_wallets WHERE status='active' ORDER BY rank")).fetchall()]

    ok, errors = 0, []
    snapshot_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []

    for wallet in wallets:
        try:
            state = hl.clearinghouse_state(wallet)
            summary = extract_margin_summary(state)
            snapshot_rows.append({'ts': ts, 'wallet': wallet, **summary, 'raw_json': json.dumps(state)})
            position_rows.extend(normalize_positions(wallet, ts, state))
            ok += 1
        except Exception as exc:
            errors.append(f'{wallet}: {exc}')
            log.exception('collect failed %s', wallet)
        time.sleep(0.10)

    with engine.begin() as conn:
        for row in snapshot_rows:
            conn.execute(text('''INSERT INTO wallet_snapshots(ts_ms,wallet,account_value_usd,total_margin_used_usd,withdrawable_usd,total_ntl_pos_usd,raw_json)
                VALUES(:ts,:wallet,:account_value_usd,:total_margin_used_usd,:withdrawable_usd,:total_ntl_pos_usd,CAST(:raw_json AS jsonb))'''), row)
        for p in position_rows:
            conn.execute(text('''INSERT INTO positions(ts_ms,wallet,coin,side,size,position_value_usd,entry_px,mark_px,unrealized_pnl_usd,return_on_equity,leverage,liquidation_px,raw_json)
                VALUES(:ts_ms,:wallet,:coin,:side,:size,:position_value_usd,:entry_px,:mark_px,:unrealized_pnl_usd,:return_on_equity,:leverage,:liquidation_px,CAST(:raw_json AS jsonb))'''), p)

    signals = compute_signals()
    check_alerts()
    with engine.begin() as conn:
        insert_run(conn, 'collect_once', 'ok' if errors == [] else 'partial', f'wallets_ok={ok}; errors={len(errors)}; positions={len(position_rows)}; signals={len(signals)}')
    return {'wallets_ok': ok, 'errors': errors[:5], 'positions': len(position_rows), 'signals': len(signals)}

def latest_snapshot_maps(conn):
    snaps = conn.execute(text('''SELECT DISTINCT ON (wallet) wallet, account_value_usd FROM wallet_snapshots ORDER BY wallet, ts_ms DESC''')).mappings().all()
    return {r['wallet']: safe_float(r['account_value_usd']) for r in snaps}


def position_rows_at(conn, target_ts: int | None = None):
    if target_ts is None:
        return conn.execute(text('''WITH t AS (SELECT max(ts_ms) ts FROM positions) SELECT * FROM positions WHERE ts_ms=(SELECT ts FROM t)''')).mappings().all()
    return conn.execute(text('''WITH nearest AS (SELECT max(ts_ms) ts FROM positions WHERE ts_ms <= :target_ts)
        SELECT * FROM positions WHERE ts_ms=(SELECT ts FROM nearest)'''), {'target_ts': target_ts}).mappings().all()


def compute_signals() -> list[dict[str, Any]]:
    settings = get_settings()
    ts = now_ms()
    with engine.begin() as conn:
        account_values = latest_snapshot_maps(conn)
        total_tracked = sum(v for v in account_values.values() if v > 0)
        scores = {r['wallet']: safe_float(r['score']) for r in conn.execute(text('''SELECT DISTINCT ON(wallet) wallet, score FROM wallet_scores ORDER BY wallet, ts_ms DESC''')).mappings().all()}
        current = position_rows_at(conn)
        previous = position_rows_at(conn, ts - settings.signal_lookback_minutes * 60_000)
    current_by_coin, prev_by_coin = {}, {}
    for rows, dest in [(current, current_by_coin), (previous, prev_by_coin)]:
        for r in rows:
            wallet, coin = r['wallet'], r['coin']
            av = account_values.get(wallet) or 0
            if av <= 0: continue
            sign = 1 if r['side'] == 'long' else -1
            exposure = sign * safe_float(r['position_value_usd']) / av
            dest.setdefault(coin, {})[wallet] = {'exposure': exposure, 'value': safe_float(r['position_value_usd']), 'side': r['side']}
    signals=[]
    wallets_all = set(account_values)
    for coin, wallets in current_by_coin.items():
        active = len(wallets)
        if active < settings.min_wallets_for_signal: continue
        weighted_sum = total_weight = 0
        long_count = short_count = 0
        value_long = value_short = 0.0
        for w, data in wallets.items():
            weight = clamp(scores.get(w, 50)/100, .05, 1.5)
            weighted_sum += data['exposure'] * weight
            total_weight += weight
            if data['side'] == 'long':
                long_count += 1; value_long += data['value']
            else:
                short_count += 1; value_short += data['value']
        weighted_net = weighted_sum / max(total_weight, .0001)
        prev_weighted_sum = prev_weight = 0
        for w, data in prev_by_coin.get(coin, {}).items():
            weight = clamp(scores.get(w, 50)/100, .05, 1.5)
            prev_weighted_sum += data['exposure'] * weight; prev_weight += weight
        prev_weighted = prev_weighted_sum / max(prev_weight, .0001)
        exposure_change = weighted_net - prev_weighted
        prev_wallets = prev_by_coin.get(coin, {})
        net_buyer_count, bullish_flow, bearish_flow = 0, 0.0, 0.0
        for w in set(wallets) | set(prev_wallets):
            cur_exp = wallets.get(w, {}).get('exposure', 0.0)
            old_exp = prev_wallets.get(w, {}).get('exposure', 0.0)
            av = account_values.get(w, 0)
            delta_usd = (cur_exp - old_exp) * av
            if delta_usd > 1000:
                net_buyer_count += 1; bullish_flow += delta_usd
            elif delta_usd < -1000:
                net_buyer_count -= 1; bearish_flow += abs(delta_usd)
        participation = active / max(1, len(wallets_all))
        consensus = (long_count - short_count) / max(1, active)
        signal = clamp(.55*weighted_net + .30*exposure_change + .15*consensus, -1, 1)
        confidence = 'High' if abs(signal) >= .35 and participation >= .45 else 'Medium' if abs(signal) >= .15 and participation >= .25 else 'Low'
        row = {
            'ts_ms': ts, 'coin': coin, 'signal': round(signal,6), 'confidence': confidence,
            'wallets_long': long_count, 'wallets_short': short_count, 'wallets_flat': max(0, len(wallets_all)-active),
            'weighted_net_exposure': round(weighted_net,6), 'exposure_change_lookback': round(exposure_change,6), 'participation_rate': round(participation,6),
            'value_long_usd': round(value_long,2), 'value_short_usd': round(value_short,2), 'net_value_usd': round(value_long-value_short,2),
            'total_tracked_value_usd': round(total_tracked,2), 'value_long_pct_total': round(value_long/max(total_tracked,1),6), 'value_short_pct_total': round(value_short/max(total_tracked,1),6),
            'net_buyer_count': net_buyer_count, 'bullish_value_flow_usd': round(bullish_flow,2), 'bearish_value_flow_usd': round(bearish_flow,2), 'net_value_flow_usd': round(bullish_flow-bearish_flow,2),
            'raw_json': json.dumps({'active_wallets': active})
        }
        signals.append(row)
    signals.sort(key=lambda x: x['signal'], reverse=True)
    targets = compute_targets(signals, ts)
    with engine.begin() as conn:
        for s in signals:
            conn.execute(text('''INSERT INTO asset_signals(ts_ms,coin,signal,confidence,wallets_long,wallets_short,wallets_flat,weighted_net_exposure,exposure_change_lookback,participation_rate,value_long_usd,value_short_usd,net_value_usd,total_tracked_value_usd,value_long_pct_total,value_short_pct_total,net_buyer_count,bullish_value_flow_usd,bearish_value_flow_usd,net_value_flow_usd,raw_json)
            VALUES(:ts_ms,:coin,:signal,:confidence,:wallets_long,:wallets_short,:wallets_flat,:weighted_net_exposure,:exposure_change_lookback,:participation_rate,:value_long_usd,:value_short_usd,:net_value_usd,:total_tracked_value_usd,:value_long_pct_total,:value_short_pct_total,:net_buyer_count,:bullish_value_flow_usd,:bearish_value_flow_usd,:net_value_flow_usd,CAST(:raw_json AS jsonb))'''), s)
        for t in targets:
            conn.execute(text('INSERT INTO portfolio_targets(ts_ms,coin,target_weight,signal,confidence) VALUES(:ts_ms,:coin,:target_weight,:signal,:confidence)'), t)
        insert_run(conn, 'compute_signals', 'ok', f'signals={len(signals)} targets={len(targets)}')
    return signals


def compute_targets(signals: list[dict[str,Any]], ts: int) -> list[dict[str,Any]]:
    positives = [s for s in signals if s['signal'] >= .10]
    budget, max_asset = .85, .35
    total = sum(max(0,s['signal']) for s in positives)
    targets=[]
    for s in positives:
        w = min(max_asset, budget * s['signal'] / max(total, .0001))
        targets.append({'ts_ms': ts, 'coin': s['coin'], 'target_weight': round(w,6), 'signal': s['signal'], 'confidence': s['confidence']})
    cash = max(0, 1 - sum(t['target_weight'] for t in targets))
    targets.append({'ts_ms': ts, 'coin': 'USDC/CASH', 'target_weight': round(cash,6), 'signal': 0.0, 'confidence': 'Reserve'})
    targets.sort(key=lambda x: x['target_weight'], reverse=True)
    return targets


def send_telegram(text_msg: str) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id: return False
    url = f'https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage'
    r = requests.post(url, json={'chat_id': settings.telegram_chat_id, 'text': text_msg, 'parse_mode': 'HTML'}, timeout=20)
    r.raise_for_status()
    return True


def check_alerts() -> int:
    settings = get_settings()
    sent = 0
    with engine.begin() as conn:
        latest = conn.execute(text('''WITH t AS (SELECT max(ts_ms) ts FROM asset_signals) SELECT * FROM asset_signals WHERE ts_ms=(SELECT ts FROM t)''')).mappings().all()
        for s in latest:
            alert_type = None
            if s['net_buyer_count'] <= -settings.alert_min_net_buyers and s['net_value_flow_usd'] <= -settings.alert_min_net_value_flow_usd:
                alert_type = 'dump_warning'
                emoji = '🚨'
                title = f'{s["coin"]} dump warning'
            elif s['net_buyer_count'] >= settings.alert_min_net_buyers and s['net_value_flow_usd'] >= settings.alert_min_net_value_flow_usd:
                alert_type = 'accumulation'
                emoji = '🟢'
                title = f'{s["coin"]} accumulation alert'
            if not alert_type: continue
            bucket = int(now_ms() / (settings.alert_cooldown_minutes * 60_000))
            key = f'{s["coin"]}:{alert_type}:{bucket}'
            exists = conn.execute(text('SELECT 1 FROM notification_events WHERE key=:key'), {'key': key}).first()
            if exists: continue
            msg = (f'{emoji} <b>{title}</b>\n'
                   f'Net buyers: {s["net_buyer_count"]}\n'
                   f'Net value flow: ${s["net_value_flow_usd"]:,.0f}\n'
                   f'Current value: ${s["value_long_usd"]:,.0f} long / ${s["value_short_usd"]:,.0f} short\n'
                   f'Signal: {s["signal"]:.2f} ({s["confidence"]})')
            send_telegram(msg)
            conn.execute(text('INSERT INTO notification_events(ts_ms,coin,alert_type,severity,message,key) VALUES(:ts,:coin,:type,:sev,:msg,:key)'), {'ts': now_ms(), 'coin': s['coin'], 'type': alert_type, 'sev': 'high', 'msg': msg, 'key': key})
            sent += 1
    return sent


def daily_refresh() -> dict[str, Any]:
    c = discover_candidates()
    s = score_wallets(get_settings().qualified_wallet_limit)
    collected = collect_once()
    send_telegram(f'✅ Daily wallet refresh complete\nCandidates: {c}\nScored: {s}\nWallets collected: {collected.get("wallets_ok")}')
    return {'candidates': c, 'scored': s, 'collection': collected}
