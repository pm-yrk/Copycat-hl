import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from performance_index_v3 import advance, build_targets, record, display_targets, public_snapshot


def cohort():
    wallets = ['0x' + f'{i:040x}' for i in range(1, 51)]
    states = [{'_wallet': a, '_copycat_state_status': 'live',
               'marginSummary': {'accountValue': '1000'}, 'assetPositions': []} for a in wallets]
    return wallets, states


def position(coin, value):
    return {'position': {'coin': coin, 'szi': '1' if value > 0 else '-1', 'positionValue': str(abs(value))}}


def targets(weight=.25):
    return [{'coin': 'BTC', 'signed_weight': weight}]


def prices(btc=100):
    return {'BTC': btc, 'ETH': 100, 'xyz:SP500': 100}


class IndexTests(unittest.TestCase):
    def test_opposing_books_cancel_without_amplification(self):
        wallets, states = cohort()
        for i, state in enumerate(states):
            state['assetPositions'] = [position('BTC', 1000 if i < 26 else -1000)]
        result = build_targets(states, wallets, set())
        self.assertAlmostEqual(result[0]['signed_weight'], .04)

    def test_leveraged_wallet_book_scales_proportionally(self):
        wallets, states = cohort()
        states[0]['assetPositions'] = [position('BTC', 9000), position('ETH', 1000)]
        result = {r['coin']: r['signed_weight'] for r in build_targets(states, wallets, set())}
        self.assertAlmostEqual(result['BTC'], .018)
        self.assertAlmostEqual(result['ETH'], .002)

    def test_idle_wallets_do_not_inflate_active_wallet_budget(self):
        wallets, states = cohort()
        states[0]['assetPositions'] = [position('BTC', 500)]
        self.assertAlmostEqual(build_targets(states, wallets, set())[0]['target_weight'], .01)

    def test_missing_or_stale_state_blocks_rebalance(self):
        wallets, states = cohort()
        with self.assertRaises(ValueError):
            build_targets(states[:-1], wallets, set())
        states[0]['_copycat_state_status'] = 'stale'
        with self.assertRaises(ValueError):
            build_targets(states, wallets, set())

    def test_real_movement_is_not_clipped_at_eight_percent(self):
        first = advance(None, 1000, targets(), prices())
        next_state = advance(first, 2000, targets(), prices(200))
        self.assertGreater(next_state['copycat_nav'], 124)
        self.assertLess(next_state['copycat_nav'], 125)
        self.assertGreater(next_state['fee_slippage_cost_usd'], 0)

    def test_roundtrip_cost_and_retry_are_accounted_once(self):
        first = advance(None, 1000, targets(), prices())
        closed = advance(first, 2000, [], prices())
        self.assertAlmostEqual(closed['copycat_nav'], 100 - 25 * .0015)
        self.assertEqual(advance(closed, 2000, [], prices()), closed)

    def test_short_pnl_has_correct_sign(self):
        first = advance(None, 1000, targets(-.25), prices())
        falling = advance(first, 2000, targets(-.25), prices(80))
        self.assertGreater(falling['copycat_nav'], 104.9)

    def test_restart_preserves_nav_and_missing_prices_do_not_write(self):
        with tempfile.TemporaryDirectory() as root:
            record(root, 'test_series', 1000, targets(), prices())
            second = record(root, 'test_series', 2000, targets(), prices(120))
            self.assertEqual(record(root, 'test_series', 2000, targets(), prices(120)), second)
            with self.assertRaises(KeyError):
                record(root, 'test_series', 3000, targets(), {'ETH': 100})
            path = Path(root) / 'test_series' / 'index.sqlite'
            with sqlite3.connect(path) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM points').fetchone()[0], 2)
                saved = json.loads(con.execute('SELECT json FROM state').fetchone()[0])
                self.assertEqual(saved, second)

    def test_corrupt_existing_series_cannot_silently_restart(self):
        with tempfile.TemporaryDirectory() as root:
            record(root, 'test_series', 1000, targets(), prices())
            with sqlite3.connect(Path(root) / 'test_series' / 'index.sqlite') as con:
                con.execute('DELETE FROM state')
            with self.assertRaisesRegex(ValueError, 'refusing implicit reset'):
                record(root, 'test_series', 2000, targets(), prices())

    def test_series_are_isolated(self):
        with tempfile.TemporaryDirectory() as root:
            record(root, 'old_series', 1000, targets(), prices())
            old = record(root, 'old_series', 2000, targets(), prices(80))
            new = record(root, 'new_series', 3000, targets(), prices(80))
            self.assertLess(old['copycat_nav'], 100)
            self.assertEqual(new['copycat_nav'], 100)

    def test_allocation_includes_unallocated_collateral(self):
        rows = display_targets(targets(.04), 1000)
        self.assertAlmostEqual(rows[-1]['target_weight'], .96)
        self.assertEqual(rows[-1]['direction'], 'reserve')
        self.assertAlmostEqual(sum(r['target_weight'] for r in rows[1:]), .96)

    def test_public_chart_is_chronological_and_preserves_inception(self):
        with tempfile.TemporaryDirectory() as root:
            start = 1790000000000
            record(root, 'new_series', start, targets(), prices())
            state = record(root, 'new_series', start + 60000, targets(), prices(90))
            snapshot = public_snapshot(root, state)
            self.assertEqual(snapshot['points'][0]['copycat_nav'], 100)
            self.assertEqual(snapshot['points'][-1]['copycat_nav'], state['copycat_nav'])
            self.assertEqual(snapshot['copycat_return_pct'], state['copycat_nav']-100)
            self.assertFalse(snapshot['funding_included'])

    def test_publisher_manifest_selects_one_cohort_without_reading_wallet_file(self):
        import publish_snapshots as publisher
        from unittest.mock import patch
        wallets, _ = cohort()
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / 'scanner_state'
            state.mkdir()
            manifest = {'series_id': 'new_series', 'ranking_method': 'copycat_perpetual_profit_v4',
                        'index_method': 'copycat_equal_wallet_net_exposure_v3', 'wallets': wallets,
                        'selected': [{'wallet': w} for w in wallets]}
            (state / 'index_activation.json').write_text(json.dumps(manifest))
            with patch.object(publisher, 'SCRIPT_DIR', Path(root)), patch.object(publisher, '_ACTIVE_INDEX_MANIFEST', None):
                self.assertEqual(publisher.load_wallets(Path(root) / 'absent.txt', 50), wallets)
                manifest['selected'] = []
                (state / 'index_activation.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    publisher.load_wallets(Path(root) / 'absent.txt', 50)


if __name__ == '__main__':
    unittest.main()
