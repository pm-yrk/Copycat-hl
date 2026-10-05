import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collect_ranking_evidence as collector
import copycat_consistency_top50_v2 as legacy
from performance_top50_v4 import evidence_metrics, percentiles
from review_portfolio_evidence import DAY_MS, window


class EvidenceTests(unittest.TestCase):
    def test_sampled_drawdown_and_pnl_are_not_balance_returns(self):
        data = window([[1, 100], [DAY_MS, 150], [2 * DAY_MS, 120], [3 * DAY_MS, 140]])
        self.assertEqual(data['pnl_change_usd'], 40)
        self.assertEqual(data['sampled_pnl_drawdown_usd'], 30)

    def test_ties_are_not_all_top_percentile(self):
        self.assertEqual(percentiles({'a': 2, 'b': 2}), {'a': .5, 'b': .5})

    def test_retry_only_failed_endpoint(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            stamp = dt.datetime.now(dt.timezone.utc).isoformat()
            (directory / 'wallet.json').write_text(json.dumps({'address': 'wallet',
                'portfolio': [], 'portfolio_retrieved_at': stamp,
                'clearinghouseState_error': 'temporary failure'}))
            with patch.object(collector, 'fetch', return_value={'ok': True}) as fetch, patch.object(collector.time, 'sleep'):
                result = collector.collect_one('wallet', directory)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(fetch.call_args.args[0]['type'], 'clearinghouseState')
            self.assertNotIn('clearinghouseState_error', result)

    def test_preview_report_does_not_overwrite_live_files(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            legacy.write_report(path, path, {}, [], [], {}, [], 'warming', False, persist=False)
            self.assertEqual(list(path.iterdir()), [])

    def test_historical_profit_cannot_pass_with_recent_losses(self):
        now = dt.datetime.now(dt.timezone.utc)
        end = int(now.timestamp() * 1000)
        history = [[end - (100-i) * DAY_MS, i * 10] for i in range(101)]
        portfolio = [[key, {'pnlHistory': series}] for key, series in (
            ('perpAllTime', history), ('perpMonth', [[end-30*DAY_MS, 100], [end, 50]]),
            ('perpWeek', [[end-7*DAY_MS, 80], [end, 50]]))]
        record = {'address': 'wallet', 'portfolio': portfolio,
                  'portfolio_retrieved_at': now.isoformat(), 'clearinghouseState_retrieved_at': now.isoformat(),
                  'clearinghouseState': {'marginSummary': {'accountValue': '10000'}, 'assetPositions': []}}
        with self.assertRaisesRegex(ValueError, 'Nonpositive'):
            evidence_metrics(record, now)


if __name__ == '__main__':
    unittest.main()
