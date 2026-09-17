"""Archive the existing public dashboard's complete top-50 snapshots.

No trading calculations or publisher state are changed. Only public aggregate
net USD and mark prices are retained, grouped by day on position-history.
"""
import base64
import datetime as dt
import json
import math
import os
import time
import urllib.error
import urllib.request

DAY_MS = 86_400_000
BRANCH = 'position-history'
FEED = 'https://pub-b9e0279f5eb0496b99c7fa37329e6b53.r2.dev/dashboard-feed.json'


def snapshot_frame(feed, now_ms):
    summary = feed.get('summary', {})
    ts = summary.get('latest_signal_ts_ms')
    if not isinstance(ts, (int, float)) or not now_ms - 10 * 60_000 <= ts <= now_ms + 60_000:
        raise ValueError('Dashboard snapshot is stale or has no valid signal timestamp')
    if summary.get('selected_wallet_count') != 50 or summary.get('wallets_with_live_state') != 50 or summary.get('wallets_missing_state', 0) or summary.get('wallets_with_stale_state', 0):
        raise ValueError('Only complete, live top-50 snapshots can be archived')
    signals = feed.get('signals')
    if not isinstance(signals, list) or not signals or len(signals) != summary.get('assets_with_signals'):
        raise ValueError('Signal set is incomplete')
    assets = {}
    for row in signals:
        coin = row.get('coin')
        net, price = row.get('net_value_usd'), row.get('price_usd')
        if not isinstance(coin, str) or not coin or coin in assets or row.get('ts_ms') != ts:
            raise ValueError('Invalid, duplicate or mixed-timestamp signal')
        if isinstance(net, bool) or not isinstance(net, (int, float)) or not math.isfinite(net):
            raise ValueError('Missing or invalid net position')
        price = price if isinstance(price, (int, float)) and not isinstance(price, bool) and math.isfinite(price) and price > 0 else None
        assets[coin] = [net, price]
    return {'ts_ms': int(ts), 'assets': assets}


def merge_frames(frames, incoming):
    # Never relabel the observation time or manufacture intermediate points.
    by_ts = {row['ts_ms']: row for row in frames}
    by_ts[incoming['ts_ms']] = incoming
    return [by_ts[ts] for ts in sorted(by_ts)]


def request_json(url, token=None, method='GET', payload=None):
    headers = {'User-Agent': 'Copycat-position-history', 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    body = None
    if payload is not None:
        body = json.dumps(payload, allow_nan=False).encode()
        headers['Content-Type'] = 'application/json'
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method=method), timeout=30) as response:
        return json.load(response)


def collect_once():
    repo, token = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN']
    api = 'https://api.github.com/repos/' + repo
    def gh(path, method='GET', payload=None):
        return request_json(api + path, token, method, payload)
    feed = request_json(FEED + '?archive=' + str(int(time.time() // 60)))
    frame = snapshot_frame(feed, int(time.time() * 1000))
    try:
        parent = gh('/git/ref/heads/' + BRANCH)['object']['sha']
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        parent = None
    tree_sha = gh('/git/commits/' + parent)['tree']['sha'] if parent else None
    entries = gh('/git/trees/' + tree_sha + '?recursive=1')['tree'] if tree_sha else []
    files = {entry['path']: entry for entry in entries if entry['type'] == 'blob'}
    def read_file(path, default):
        if path not in files:
            return default
        blob = gh('/git/blobs/' + files[path]['sha'])
        return json.loads(base64.b64decode(blob['content']))
    day = dt.datetime.fromtimestamp(frame['ts_ms'] / 1000, dt.timezone.utc).date().isoformat()
    path = 'days/' + day + '.json'
    existing = read_file(path, {'schema_version': 1, 'frames': []})
    frames = merge_frames(existing['frames'], frame)
    if frames == existing['frames']:
        print('No newer source snapshot; archive unchanged')
        return
    cutoff = dt.datetime.fromtimestamp((frame['ts_ms'] - 31 * DAY_MS) / 1000, dt.timezone.utc).date().isoformat()
    days = sorted({p[5:-5] for p in files if p.startswith('days/') and p.endswith('.json') and p[5:-5] >= cutoff} | {day})
    manifest = {'schema_version': 1, 'latest_ts_ms': frame['ts_ms'], 'days': days, 'cohort': 'Copycat-ranked top 50 at each observation', 'cadence_minutes': 5}
    contents = {
        path: '{"schema_version":1,"frames":[\n' + ',\n'.join(json.dumps(f, separators=(',', ':'), allow_nan=False) for f in frames) + '\n]}\n',
        'index.json': json.dumps(manifest, separators=(',', ':')) + '\n',
    }
    changes = []
    for name, content in contents.items():
        sha = gh('/git/blobs', 'POST', {'content': content, 'encoding': 'utf-8'})['sha']
        changes.append({'path': name, 'mode': '100644', 'type': 'blob', 'sha': sha})
    for name in files:
        if name.startswith('days/') and name.endswith('.json') and name[5:-5] < cutoff:
            changes.append({'path': name, 'mode': '100644', 'type': 'blob', 'sha': None})
    tree = gh('/git/trees', 'POST', dict({'tree': changes}, **({'base_tree': tree_sha} if tree_sha else {})))['sha']
    commit = gh('/git/commits', 'POST', {'message': '[skip ci] Record observed top-50 positioning', 'tree': tree, 'parents': [parent] if parent else []})['sha']
    if parent:
        gh('/git/refs/heads/' + BRANCH, 'PATCH', {'sha': commit, 'force': False})
    else:
        gh('/git/refs', 'POST', {'ref': 'refs/heads/' + BRANCH, 'sha': commit})
    print(f'Archived {len(frame["assets"])} tokens at {frame["ts_ms"]}; {len(frames)} observations today')


if __name__ == '__main__':
    collect_once()
