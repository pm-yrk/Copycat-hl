from __future__ import annotations

import json, math, time, logging, os
from datetime import date, timedelta
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def _extract_pnl_value(data: Any) -> float | None:
    """Return only real PnL fields. Never fall back to volume or account value.
    Ranking credibility depends on not mistaking turnover for profit.
    """
    if isinstance(data, dict):
        for key in ('pnl', 'totalPnl', 'total_pnl', 'profit', 'netPnl', 'net_pnl'):
            if key in data and data.get(key) is not None:
                return safe_float(data.get(key))
        # Hyperliquid portfolio responses commonly expose cumulative PnL as
        # pnlHistory rather than a direct pnl field. This is still real PnL; it
        # is safe to use. We intentionally do NOT use volume or account value.
        hist = data.get('pnlHistory') or data.get('pnl_history') or []
        if isinstance(hist, list) and hist:
            last = hist[-1]
            if isinstance(last, (list, tuple)) and len(last) >= 2:
                return safe_float(last[1])
            if isinstance(last, dict):
                return safe_float(last.get('pnl') or last.get('value'))
    elif isinstance(data, (int, float)):
        return float(data)
    return None


def _history_values(data: Any) -> list[float]:
    if not isinstance(data, dict):
        return []
    hist = data.get('accountValueHistory') or data.get('account_value_history') or []
    vals: list[float] = []
    if isinstance(hist, list):
        for item in hist:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                vals.append(safe_float(item[1], None))
            elif isinstance(item, dict):
                vals.append(safe_float(item.get('value') or item.get('accountValue'), None))
    return [v for v in vals if v is not None and v > 0]


def _max_drawdown(vals: list[float]) -> float:
    peak = 0.0
    dd = 0.0
    for v in vals:
        peak = max(peak, v)
        if peak > 0:
            dd = max(dd, (peak - v) / peak)
    return dd


def portfolio_pnl(portfolio: Any) -> dict[str, float]:
    """Extract real Hyperliquid PnL windows and basic risk metrics.

    Older builds were deliberately defensive and could fall back to volume or
    account-value history if a PnL field was missing. That is unsafe for a paid
    product because volume is not profit. This version ranks only on actual PnL
    fields and treats missing PnL as missing, not as zero profit.
    """
    windows: dict[str, float | None] = {'day': None, 'week': None, 'month': None, 'allTime': None}
    history: list[float] = []

    def store(key: Any, data: Any):
        k = str(key or '')
        pnl = _extract_pnl_value(data)
        if pnl is not None:
            windows[k] = pnl
        history.extend(_history_values(data))

    if isinstance(portfolio, list):
        for row in portfolio:
            if isinstance(row, list) and len(row) >= 2:
                store(row[0], row[1])
            elif isinstance(row, dict):
                key = row.get('period') or row.get('window') or row.get('name') or row.get('timeframe')
                if key:
                    store(key, row)
    elif isinstance(portfolio, dict):
        for k, v in portfolio.items():
            store(k, v)

    real_vals = [v for v in windows.values() if v is not None]
    positive = sum(1 for v in real_vals if v > 0)
    max_share = max([abs(v) for v in real_vals] or [0]) / max(1.0, sum(abs(v) for v in real_vals))
    active_days = 0
    if history:
        active_days = max(1, min(3650, len(history)))
    return {
        'pnl_day_usd': windows.get('day') or 0.0,
        'pnl_30d_usd': windows.get('month') if windows.get('month') is not None else (windows.get('30d') or 0.0),
        'pnl_all_time_usd': windows.get('allTime') if windows.get('allTime') is not None else (windows.get('all_time') or 0.0),
        'positive_windows': float(positive),
        'real_pnl_windows': float(len(real_vals)),
        'max_single_window_pnl_share': max_share,
        'max_drawdown_pct': _max_drawdown(history),
        'active_days_observed': float(active_days),
        'has_real_pnl': 1.0 if len(real_vals) >= 2 else 0.0,
    }


def wallet_score(wallet: str, state: dict[str, Any], portfolio: Any) -> dict[str, Any]:
    """Ranking V2: score profit quality rather than raw PnL only."""
    ts = now_ms()
    summary = extract_margin_summary(state)
    account_value = summary['account_value_usd']
    positions = normalize_positions(wallet, ts, state)
    pnl = portfolio_pnl(portfolio)
    pnl30 = pnl['pnl_30d_usd']
    pnlall = pnl['pnl_all_time_usd']

    real_windows = max(1.0, pnl.get('real_pnl_windows', 0.0))
    positive_window_ratio = pnl['positive_windows'] / real_windows
    consistency = clamp(positive_window_ratio * 100, 0, 100)

    weighted_pnl = 0.70 * pnl30 + 0.30 * pnlall
    pnl_quality_score = clamp(50 + 50 * math.tanh((weighted_pnl / max(account_value, 1)) * 4), 0, 100)
    roi_score = clamp(50 + 50 * math.tanh((pnl30 / max(account_value, 1)) * 8), 0, 100)
    drawdown_pct = pnl['max_drawdown_pct']
    drawdown_score = 55.0 if drawdown_pct <= 0 else clamp(100 * (1 - drawdown_pct / 0.50), 0, 100)
    capital_score = clamp(20 * math.log10(max(account_value, 1)) - 60, 0, 100)

    largest = max([p['position_value_usd'] for p in positions] or [0])
    total_pos = sum(p['position_value_usd'] for p in positions) or 1
    largest_position_share = largest / total_pos
    active_days = pnl.get('active_days_observed', 0.0)
    activity_score = clamp((len(positions) / 8) * 60 + min(active_days, 30) / 30 * 40, 0, 100)

    anti_fluke = 100.0
    if pnl['max_single_window_pnl_share'] > 0.70:
        anti_fluke -= 35
    if largest_position_share > 0.80:
        anti_fluke -= 30
    if real_windows < 2:
        anti_fluke -= 30
    anti_fluke = clamp(anti_fluke, 0, 100)

    components = {
        'net_pnl_quality': pnl_quality_score,
        'roi_capital_efficiency': roi_score,
        'consistency': consistency,
        'drawdown_risk_control': drawdown_score,
        'account_size_liquidity': capital_score,
        'recent_activity': activity_score,
        'anti_fluke': anti_fluke,
    }
    score = (
        .30 * components['net_pnl_quality'] +
        .20 * components['roi_capital_efficiency'] +
        .15 * components['consistency'] +
        .15 * components['drawdown_risk_control'] +
        .10 * components['account_size_liquidity'] +
        .05 * components['recent_activity'] +
        .05 * components['anti_fluke']
    )

    disqualifiers: list[str] = []
    if account_value < 50_000: disqualifiers.append('account_value_below_50k')
    if pnl30 <= 1_000: disqualifiers.append('30d_pnl_not_positive_enough')
    if pnlall <= 0: disqualifiers.append('all_time_pnl_not_positive')
    if real_windows < 2: disqualifiers.append('insufficient_real_pnl_windows')
    if consistency < 40: disqualifiers.append('low_consistency')
    if largest_position_share > 0.90: disqualifiers.append('single_position_dominates')
    if score < 45: disqualifiers.append('score_below_threshold')
    qualifies = len(disqualifiers) == 0

    metrics = {
        **summary,
        **pnl,
        'position_count': len(positions),
        'largest_position_share': largest_position_share,
        'score_components': components,
        'ranking_formula': 'v2_profit_quality',
        'disqualifiers': disqualifiers,
    }
    return {
        'ts_ms': ts, 'wallet': wallet, 'score': round(score,3), 'qualifies': qualifies,
        'account_value_usd': account_value, 'pnl_30d_usd': pnl30, 'pnl_all_time_usd': pnlall,
        'max_drawdown_pct': drawdown_pct, 'consistency_score': consistency,
        'anti_fluke_score': anti_fluke, 'metrics_json': json.dumps(metrics)
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


def collect_wallet_state(wallet: str, ts: int) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]], str | None]:
    '''Fetch one wallet. Created as a separate helper so the 50-wallet batch
    can be collected concurrently without sharing a requests.Session between
    threads.
    '''
    try:
        hl = Hyperliquid()
        state = hl.clearinghouse_state(wallet)
        summary = extract_margin_summary(state)
        snapshot = {'ts': ts, 'wallet': wallet, **summary, 'raw_json': json.dumps(state)}
        positions = normalize_positions(wallet, ts, state)
        return wallet, snapshot, positions, None
    except Exception as exc:
        log.exception('collect failed %s', wallet)
        return wallet, None, [], f'{wallet}: {exc}'


def collect_once() -> dict[str, Any]:
    ts = now_ms()
    with engine.begin() as conn:
        wallets = [r[0] for r in conn.execute(text("SELECT wallet FROM qualified_wallets WHERE status='active' ORDER BY rank")).fetchall()]

    if not wallets:
        with engine.begin() as conn:
            insert_run(conn, 'collect_once', 'error', 'no active wallets')
        return {'wallets_ok': 0, 'errors': ['no active wallets'], 'positions': 0, 'signals': 0}

    # Sequentially fetching 50 wallets can take about a minute on Render, which
    # makes the 10-second dashboard look stale. Fetch wallets in a bounded pool
    # so a full, completed snapshot is written much more quickly while still
    # keeping one consistent timestamp for the whole batch.
    try:
        max_workers = int(float(os.getenv('COLLECTOR_MAX_WORKERS', '12')))
    except Exception:
        max_workers = 12
    max_workers = max(2, min(max_workers, 20, len(wallets)))

    ok, errors = 0, []
    snapshot_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []

    started = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(collect_wallet_state, wallet, ts) for wallet in wallets]
        for fut in as_completed(futures):
            wallet, snapshot, positions, error = fut.result()
            if error:
                errors.append(error)
                continue
            if snapshot is not None:
                snapshot_rows.append(snapshot)
                position_rows.extend(positions)
                ok += 1

    min_ok = max(1, int(len(wallets) * 0.90))
    if ok < min_ok:
        # Do not publish a bad/partial signal board. Keep the previous completed
        # snapshot live and record the failure for the audit/logs.
        elapsed = time.time() - started
        with engine.begin() as conn:
            insert_run(conn, 'collect_once', 'error', f'incomplete batch wallets_ok={ok}/{len(wallets)}; errors={len(errors)}; elapsed={elapsed:.1f}s')
        return {'wallets_ok': ok, 'errors': errors[:5], 'positions': len(position_rows), 'signals': 0, 'elapsed_seconds': round(elapsed, 1)}

    with engine.begin() as conn:
        for row in snapshot_rows:
            conn.execute(text('''INSERT INTO wallet_snapshots(ts_ms,wallet,account_value_usd,total_margin_used_usd,withdrawable_usd,total_ntl_pos_usd,raw_json)
                VALUES(:ts,:wallet,:account_value_usd,:total_margin_used_usd,:withdrawable_usd,:total_ntl_pos_usd,CAST(:raw_json AS jsonb))'''), row)
        for p in position_rows:
            conn.execute(text('''INSERT INTO positions(ts_ms,wallet,coin,side,size,position_value_usd,entry_px,mark_px,unrealized_pnl_usd,return_on_equity,leverage,liquidation_px,raw_json)
                VALUES(:ts_ms,:wallet,:coin,:side,:size,:position_value_usd,:entry_px,:mark_px,:unrealized_pnl_usd,:return_on_equity,:leverage,:liquidation_px,CAST(:raw_json AS jsonb))'''), p)

    signals = compute_signals()
    check_alerts()
    elapsed = time.time() - started
    with engine.begin() as conn:
        insert_run(conn, 'collect_once', 'ok' if errors == [] else 'partial', f'wallets_ok={ok}/{len(wallets)}; errors={len(errors)}; positions={len(position_rows)}; signals={len(signals)}; elapsed={elapsed:.1f}s; workers={max_workers}')
    return {'wallets_ok': ok, 'errors': errors[:5], 'positions': len(position_rows), 'signals': len(signals), 'elapsed_seconds': round(elapsed, 1)}

def latest_snapshot_maps(conn, target_ts: int | None = None):
    # IMPORTANT: signal calculations must only use the current active 50-wallet
    # cohort. Older wallet snapshots from previous cohorts can remain in the DB;
    # using DISTINCT across the whole table would leak stale wallets into
    # total_tracked_value_usd and make the dashboard/audit inconsistent.
    if target_ts is None:
        snaps = conn.execute(text('''
            SELECT q.wallet, COALESCE(s.account_value_usd,0) AS account_value_usd
            FROM qualified_wallets q
            LEFT JOIN LATERAL (
              SELECT ws.account_value_usd
              FROM wallet_snapshots ws
              WHERE ws.wallet=q.wallet
              ORDER BY ws.ts_ms DESC
              LIMIT 1
            ) s ON TRUE
            WHERE q.status='active'
            ORDER BY q.rank
        ''')).mappings().all()
    else:
        snaps = conn.execute(text('''
            SELECT q.wallet, COALESCE(s.account_value_usd,0) AS account_value_usd
            FROM qualified_wallets q
            LEFT JOIN LATERAL (
              SELECT ws.account_value_usd
              FROM wallet_snapshots ws
              WHERE ws.wallet=q.wallet AND ws.ts_ms <= :target_ts
              ORDER BY ws.ts_ms DESC
              LIMIT 1
            ) s ON TRUE
            WHERE q.status='active'
            ORDER BY q.rank
        '''), {'target_ts': target_ts}).mappings().all()
    return {r['wallet']: safe_float(r['account_value_usd']) for r in snaps if safe_float(r['account_value_usd']) > 0}


def position_rows_at(conn, target_ts: int | None = None):
    # Keep current and lookback positions restricted to the same active cohort.
    # This prevents old positions from retired wallets influencing flow deltas.
    if target_ts is None:
        return conn.execute(text('''
            WITH t AS (
              SELECT max(p.ts_ms) ts
              FROM positions p JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
            )
            SELECT p.*
            FROM positions p JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
            WHERE p.ts_ms=(SELECT ts FROM t)
        ''')).mappings().all()
    return conn.execute(text('''
        WITH nearest AS (
          SELECT max(p.ts_ms) ts
          FROM positions p JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
          WHERE p.ts_ms <= :target_ts
        )
        SELECT p.*
        FROM positions p JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
        WHERE p.ts_ms=(SELECT ts FROM nearest)
    '''), {'target_ts': target_ts}).mappings().all()


def compute_signals() -> list[dict[str, Any]]:
    settings = get_settings()
    with engine.begin() as conn:
        current_position_ts_row = conn.execute(text("""SELECT max(p.ts_ms) AS ts_ms FROM positions p JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'""")).mappings().first()
        current_position_ts = int(current_position_ts_row['ts_ms']) if current_position_ts_row and current_position_ts_row['ts_ms'] else now_ms()
        # Use the positions batch timestamp as the signal timestamp. This keeps
        # /api/summary, /api/signals, /api/flow, and /api/recent-orders aligned.
        ts = current_position_ts
        account_values = latest_snapshot_maps(conn, ts)
        total_tracked = sum(v for v in account_values.values() if v > 0)
        scores = {r['wallet']: safe_float(r['score']) for r in conn.execute(text('''SELECT DISTINCT ON(wallet) wallet, score FROM wallet_scores ORDER BY wallet, ts_ms DESC''')).mappings().all()}
        current = position_rows_at(conn, ts)
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
