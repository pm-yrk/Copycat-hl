import unittest
from unittest.mock import patch

import copycat_profit_history_worker_v1 as worker


class PaginationTests(unittest.TestCase):
    @patch.object(worker.time, 'sleep')
    def test_boundary_fills_are_not_skipped(self, _sleep):
        page = [{'time': i + 1, 'tid': i} for i in range(2000)]
        tail = [page[-1], {'time': 2000, 'tid': 2000}, {'time': 2001, 'tid': 2001}]
        with patch.object(worker, 'post_info', side_effect=[page, tail]) as request:
            rows = worker.fetch_fills('wallet', 1, 3000)
        self.assertEqual(request.call_args_list[1].args[0]['startTime'], 2000)
        self.assertEqual(len(rows), 2002)
        self.assertTrue(rows.complete)

    @patch.object(worker.time, 'sleep')
    def test_saturated_timestamp_fails_closed(self, _sleep):
        page = [{'time': 100, 'tid': i} for i in range(2000)]
        with patch.object(worker, 'post_info', return_value=page):
            rows = worker.fetch_fills('wallet', 1, 3000)
        self.assertFalse(rows.complete)

    @patch.object(worker.time, 'sleep')
    def test_funding_is_paginated_without_double_counting(self, _sleep):
        page = [{'time': i + 1, 'delta': {'usdc': '1'}} for i in range(500)]
        with patch.object(worker, 'post_info', side_effect=[page, [page[-1], {'time': 501, 'delta': {'usdc': '2'}}]]):
            rows = worker.fetch_funding('wallet', 1, 1000)
        self.assertEqual(len(rows), 501)
        self.assertTrue(rows.complete)

    def test_malformed_responses_are_errors_not_empty_accounts(self):
        with patch.object(worker, 'post_info', return_value={'error': 'busy'}):
            with self.assertRaises(ValueError):
                worker.fetch_fills('wallet', 1, 100)
            with self.assertRaises(ValueError):
                worker.fetch_funding('wallet', 1, 100)
            with self.assertRaises(ValueError):
                worker.fetch_state('wallet')

    def test_funding_does_not_inflate_trading_active_days(self):
        base = 1750000000000
        metrics = worker.calculate_metrics('wallet',
            [{'time': base, 'closedPnl': '5', 'fee': '1'}],
            [{'time': base + 86400000, 'delta': {'usdc': '1'}}],
            {'marginSummary': {'accountValue': '10000'}}, base)
        self.assertEqual(metrics['active_days'], 1)
        self.assertEqual(metrics['net_pnl'], 5)


if __name__ == '__main__':
    unittest.main()
