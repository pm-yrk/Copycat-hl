"""Read-only evidence collection; never selects wallets or resets the index."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sqlite3
import time
import urllib.request
import zipfile

from copycat_consistency_top50_v2 import qualify, rank, valid_wallet


def candidates(rows, active, now, limit):
    # Keep active members and current qualifiers, then examine historical
    # challengers. Refresh timestamps only on temporary copies for prioritising
    # collection, NEVER for ranking eligibility or publication.
    complete = [r for r in rows if r.get('score_ready') == 1 and r.get('history_complete') == 1]
    fresh, _ = qualify([dict(r) for r in complete], now)
    historical, _ = qualify([{**r, 'observed_at_utc': now.isoformat()} for r in complete], now)
    ordered = list(active) + [r['address'] for r in rank(fresh)[:50]] + [r['address'] for r in rank(historical)]
    return list(dict.fromkeys(a.lower() for a in ordered if valid_wallet(a)))[:limit]


def fetch(body):
    request = urllib.request.Request('https://api.hyperliquid.xyz/info',
                                     data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', default=r'C:\dev\hyper_wallet_tracker_saas_v1')
    parser.add_argument('--active-publisher', default=r'C:\CopycatSnapshotPublisher\local_snapshot_publisher')
    parser.add_argument('--limit', type=int, default=250)
    args = parser.parse_args()
    if not 50 <= args.limit <= 500:
        parser.error('--limit must be between 50 and 500')
    database = Path(args.repo_root) / 'copycat_wallet_registry' / 'copycat_wallet_registry.sqlite'
    connection = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    rows = [dict(r) for r in connection.execute('SELECT * FROM wallet_profit_metrics')]
    connection.close()
    wallet_file = Path(args.active_publisher) / 'wallets.txt'
    if not wallet_file.exists():
        raise RuntimeError('Active wallets.txt not found; specify --active-publisher before collecting.')
    active = [a.strip().lower() for a in wallet_file.read_text().splitlines() if valid_wallet(a.strip().lower())]
    if len(set(active)) != 50:
        raise RuntimeError('Expected 50 unique active wallets; no evidence collected.')
    now = dt.datetime.now(dt.timezone.utc)
    addresses = candidates(rows, active, now, args.limit)
    output = Path.home() / 'Downloads' / ('Copycat-performance-evidence-' + now.strftime('%Y%m%d-%H%M%S') + '.zip')
    errors = []
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('selection.json', json.dumps({'active_wallets': active, 'candidates': addresses,
            'created_at': now.isoformat(), 'purpose': 'Review only; historical scores prioritise collection, not selection.'}))
        archive.writestr('candidate_metrics.json', json.dumps([r for r in rows if r['address'] in set(addresses)]))
        for index, address in enumerate(addresses, 1):
            record = {'address': address, 'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat()}
            for endpoint in ('portfolio', 'clearinghouseState'):
                try:
                    record[endpoint] = fetch({'type': endpoint, 'user': address})
                except Exception as exc:
                    record[endpoint + '_error'] = str(exc)
                    errors.append({'address': address, 'endpoint': endpoint, 'error': str(exc)})
                time.sleep(1.2)
            archive.writestr('wallets/' + address + '.json', json.dumps(record))
            print(f'{index}/{len(addresses)} collected', flush=True)
        archive.writestr('errors.json', json.dumps(errors))
    print(f'Saved: {output}\nEndpoint failures: {len(errors)}\nNo live settings or index values changed.')


if __name__ == '__main__':
    main()
