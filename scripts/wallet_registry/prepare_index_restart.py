"""Archive the legacy series and prepare (but never install) an activation manifest."""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3
import uuid

from copycat_consistency_top50_v2 import atomic_text, parse_utc, valid_wallet


def validate_report(report, now):
    if report.get('method') != 'copycat_perpetual_profit_v4' or report.get('status') == 'warming':
        raise ValueError('A qualified V4 report is required')
    generated = parse_utc(report.get('generated_at_utc'))
    if generated is None or not 0 <= (now-generated).total_seconds() <= 900:
        raise ValueError('Ranking review must be freshly generated (within 15 minutes)')
    selected = report.get('selected', [])
    wallets = [r.get('wallet') for r in selected]
    if len(wallets) != 50 or len(set(wallets)) != 50 or not all(valid_wallet(w) for w in wallets):
        raise ValueError('Exactly 50 unique qualified wallets are required')
    for row in selected:
        evidence = row.get('performance_evidence', {})
        month, long = evidence.get('month', {}), evidence.get('long_window', {})
        values = [month.get('pnl_change_usd', 0), long.get('pnl_change_usd', 0), long.get('coverage_days', 0)]
        if (not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)
                or evidence.get('evidence_issues') != [] or month.get('pnl_change_usd', 0) <= 0
                or long.get('pnl_change_usd', 0) <= 0 or long.get('coverage_days', 0) < 90
                or evidence.get('address') != row['wallet']):
            raise ValueError('Missing or invalid portfolio qualification evidence')
    return wallets


def prepare(report, state_path, history_path, output, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    wallets = validate_report(report, now)
    state_path, history_path, output = Path(state_path), Path(history_path), Path(output)
    if not state_path.is_file() or not history_path.is_file():
        raise ValueError('Both legacy state and history must exist before preparing a reset')
    series_id = 'v3_' + now.strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8]
    archive = output / series_id
    archive.mkdir(parents=True, exist_ok=False)
    # No renames/deletes of live state. SQLite backup includes committed WAL data.
    shutil.copy2(state_path, archive / 'legacy_state.json')
    backup = state_path.with_name(state_path.name + '.bak')
    if backup.exists():
        shutil.copy2(backup, archive / 'legacy_state.json.bak')
    source = sqlite3.connect(history_path.resolve().as_uri() + '?mode=ro', uri=True)
    destination = sqlite3.connect(archive / 'legacy_history.sqlite')
    try:
        source.backup(destination)
        if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Archived history failed integrity check')
        destination.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    finally:
        destination.close()
        source.close()
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.iterdir() if p.is_file()}
    atomic_text(archive / 'ranking_review.json', json.dumps(report, indent=2))
    manifest = {'series_id': series_id, 'ranking_method': 'copycat_perpetual_profit_v4',
        'index_method': 'copycat_equal_wallet_net_exposure_v3', 'wallets': wallets,
        'selected': report['selected'], 'method_note': report['note'],
        'prepared_at_utc': now.isoformat(), 'archive_name': series_id,
        'legacy_archive_checksums': hashes,
        'activation_note': 'Start at the first complete live capture, not the preparation time. Never reset this series on restart.'}
    path = archive / 'prepared_index_activation.json'
    atomic_text(path, json.dumps(manifest, indent=2))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--legacy-state', type=Path, required=True)
    parser.add_argument('--legacy-history', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    path = prepare(json.loads(args.report.read_text()), args.legacy_state, args.legacy_history, args.output)
    print(f'Archive checked and activation manifest prepared: {path}')
    print('Not installed. No live wallets, index state, scheduled tasks or publisher settings changed.')


if __name__ == '__main__':
    main()
