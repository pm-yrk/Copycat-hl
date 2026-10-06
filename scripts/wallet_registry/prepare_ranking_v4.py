"""Resumable fresh candidate scan. Does not activate a cohort or reset an index."""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

from collect_ranking_evidence import candidates
import copycat_profit_history_worker_v1 as worker
from copycat_consistency_top50_v2 import atomic_text, parse_utc, read_wallets


def scan_is_fresh(metrics, evidence, now):
    if not metrics or not evidence or metrics.get('error'):
        return False
    stamps = [metrics.get('observed_at_utc'), evidence.get('portfolio_retrieved_at'),
              evidence.get('clearinghouseState_retrieved_at')]
    return all((stamp := parse_utc(raw)) is not None and
               0 <= (now-stamp).total_seconds() < 86400 for raw in stamps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path(r'C:\dev\hyper_wallet_tracker_saas_v1'))
    parser.add_argument('--active-publisher', type=Path, default=Path(r'C:\CopycatSnapshotPublisher\local_snapshot_publisher'))
    parser.add_argument('--limit', type=int, default=500)
    args = parser.parse_args()
    if not 50 <= args.limit <= 1000:
        parser.error('--limit must be 50 to 1000')
    wallets = read_wallets(args.active_publisher / 'wallets.txt')
    if len(wallets) != 50:
        raise RuntimeError('Expected exactly 50 active wallets')
    con = worker.connect_db(args.repo_root)
    output = args.repo_root / 'copycat_wallet_registry' / 'v4_review'
    output.mkdir(parents=True, exist_ok=True)
    try:
        rows = [dict(r) for r in con.execute('SELECT * FROM wallet_profit_metrics')]
        addresses = candidates(rows, wallets, worker.utc_now(), args.limit)
        atomic_text(output / 'candidate_selection.json', json.dumps({'addresses': addresses,
            'created_at': worker.utc_text(), 'note': 'Historical metrics only prioritise refresh, never waive freshness.'}))
        for index, address in enumerate(addresses, 1):
            metrics_row = con.execute('SELECT * FROM wallet_profit_metrics WHERE address=?', (address,)).fetchone()
            evidence_row = con.execute('SELECT evidence_json FROM wallet_performance_evidence WHERE address=?', (address,)).fetchone()
            metrics = dict(metrics_row) if metrics_row else None
            evidence = json.loads(evidence_row[0]) if evidence_row else None
            if scan_is_fresh(metrics, evidence, worker.utc_now()):
                print(f'{index}/{len(addresses)} already fresh; retained', flush=True)
                continue
            try:
                worker.scan_one(con, address)
                print(f'{index}/{len(addresses)} refreshed', flush=True)
            except Exception as exc:
                worker.store_metrics(con, worker.error_metrics(address, str(exc)))
                print(f'{index}/{len(addresses)} failed safely: {exc}', flush=True)
                if '429' in str(exc):
                    # Stop rather than hammering the API. Rerunning resumes.
                    raise RuntimeError('Rate limited. Rerun later; completed scans are saved.') from exc
            time.sleep(1.2)
    finally:
        con.close()
    report = output / 'ranking_v4_review.json'
    subprocess.run([sys.executable, str(Path(__file__).with_name('copycat_consistency_top50_v2.py')),
        '--repo-root', str(args.repo_root), '--active-publisher', str(args.active_publisher),
        '--performance-v4', '--report-path', str(report)], check=True)
    archive = Path.home() / 'Downloads' / ('Copycat-v4-review-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip')
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        z.write(report, report.name)
        z.write(output / 'candidate_selection.json', 'candidate_selection.json')
    result = json.loads(report.read_text())
    print(f"\nFresh qualified wallets: {result['qualified_wallets']}\nReview saved: {archive}")
    print('No new ranking activated; no index reset. Existing scheduled tasks remain unchanged.')


if __name__ == '__main__':
    main()
