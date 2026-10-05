import datetime as dt
import sqlite3
import unittest
from unittest.mock import patch

import copycat_profit_history_worker_v1 as worker


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.executescript('''
            CREATE TABLE wallets(address TEXT PRIMARY KEY, discovery_count INTEGER);
            CREATE TABLE wallet_trade_daily(address TEXT, day_utc TEXT, trade_count INTEGER, notional_usd REAL);
            CREATE TABLE wallet_profit_metrics(address TEXT PRIMARY KEY, observed_at_utc TEXT,
                score_ready INTEGER, history_complete INTEGER, net_pnl REAL, account_value REAL,
                span_days REAL, fill_count INTEGER);
        ''')
        self.old = '0x' + '1' * 40
        self.new = '0x' + '2' * 40
        self.con.executemany('INSERT INTO wallets VALUES (?, 25)', [(self.old,), (self.new,)])
        self.con.execute('INSERT INTO wallet_profit_metrics VALUES (?, ?, 1, 1, 1000, 10000, 90, 200)',
                         (self.old, '2026-01-01T00:00:00+00:00'))
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_discovery_backlog_does_not_starve_profitable_challengers(self):
        with patch.object(worker, 'utc_now', return_value=dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc)):
            self.assertEqual(worker.choose_candidate(self.con, []), self.old)
            self.assertEqual(worker.choose_candidate(self.con, []), self.new)
            self.assertEqual(worker.choose_candidate(self.con, []), self.old)

    def test_active_members_still_have_refresh_priority(self):
        self.assertEqual(worker.choose_candidate(self.con, [self.old]), self.old)


if __name__ == '__main__':
    unittest.main()
