import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from prepare_index_restart import prepare, validate_report
from prepare_ranking_v4 import scan_is_fresh


def report(now):
    selected = []
    for i in range(1, 51):
        address = '0x' + f'{i:040x}'
        selected.append({'wallet': address, 'performance_evidence': {
            'address': address, 'evidence_issues': [], 'month': {'pnl_change_usd': 1},
            'long_window': {'pnl_change_usd': 1, 'coverage_days': 90}}})
    return {'method': 'copycat_perpetual_profit_v4', 'status': 'ready',
            'generated_at_utc': now.isoformat(), 'selected': selected, 'note': 'test'}


class PreparationTests(unittest.TestCase):
    def test_refuses_stale_short_or_duplicate_cohort(self):
        now = dt.datetime.now(dt.timezone.utc)
        r = report(now-dt.timedelta(hours=1))
        with self.assertRaises(ValueError):
            validate_report(r, now)
        r = report(now)
        r['selected'].pop()
        with self.assertRaises(ValueError):
            validate_report(r, now)
        r['selected'].append(r['selected'][0])
        with self.assertRaises(ValueError):
            validate_report(r, now)

    def test_archive_preserves_committed_wal_and_never_installs_manifest(self):
        now = dt.datetime.now(dt.timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            state = root / 'legacy.json'
            state.write_text('{"copycat_nav": 81}')
            history = root / 'history.sqlite'
            with sqlite3.connect(history) as con:
                con.execute('PRAGMA journal_mode=WAL')
                con.execute('CREATE TABLE points(nav REAL)')
                con.execute('INSERT INTO points VALUES (81)')
                con.commit()
                prepared = prepare(report(now), state, history, root / 'archives', now)
                self.assertEqual(state.read_text(), '{"copycat_nav": 81}')
                with sqlite3.connect(prepared.parent / 'legacy_history.sqlite') as copied:
                    self.assertEqual(copied.execute('SELECT nav FROM points').fetchone()[0], 81)
            manifest = json.loads(prepared.read_text())
            self.assertEqual(len(manifest['wallets']), 50)
            self.assertIn('legacy_history.sqlite', manifest['legacy_archive_checksums'])
            self.assertFalse((root / 'scanner_state' / 'index_activation.json').exists())

    def test_resume_requires_both_fresh_metrics_and_fresh_portfolio(self):
        now = dt.datetime.now(dt.timezone.utc)
        metrics = {'observed_at_utc': now.isoformat()}
        evidence = {'portfolio_retrieved_at': now.isoformat(), 'clearinghouseState_retrieved_at': now.isoformat()}
        self.assertTrue(scan_is_fresh(metrics, evidence, now))
        evidence['portfolio_retrieved_at'] = (now-dt.timedelta(days=2)).isoformat()
        self.assertFalse(scan_is_fresh(metrics, evidence, now))


if __name__ == '__main__':
    unittest.main()
