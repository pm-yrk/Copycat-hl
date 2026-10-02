import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from publish_snapshots import position_history_snapshots


def complete_feed(ts_ms: int, btc_net: float = 125.0):
    return {
        "summary": {
            "latest_signal_ts_ms": ts_ms,
            "selected_wallet_count": 50,
            "wallets_with_live_state": 50,
            "wallets_missing_state": 0,
            "wallets_with_stale_state": 0,
        },
        "signals": [
            {"coin": "BTC", "net_value_usd": btc_net, "price_usd": 70_000.0},
            {"coin": "ETH", "net_value_usd": -45.0, "price_usd": 3_500.0},
        ],
    }


class PositionHistoryTests(unittest.TestCase):
    def test_records_only_distinct_complete_observations(self):
        first = 1_790_899_200_000
        with tempfile.TemporaryDirectory() as directory:
            history_dir = Path(directory)
            snapshots = position_history_snapshots(complete_feed(first), history_dir)
            self.assertEqual(snapshots["position-history/index.json"][1]["latest_ts_ms"], first)

            position_history_snapshots(complete_feed(first + 3 * 60_000, 130.0), history_dir)
            position_history_snapshots(complete_feed(first + 5 * 60_000, 135.0), history_dir)
            day = json.loads(next(history_dir.glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual([row["ts_ms"] for row in day["frames"]], [first, first + 5 * 60_000])
            self.assertEqual(day["frames"][-1]["assets"]["BTC"], [135.0, 70000.0])

    def test_rejects_incomplete_or_stale_cohort(self):
        with tempfile.TemporaryDirectory() as directory:
            feed = complete_feed(1_790_899_200_000)
            feed["summary"]["wallets_with_stale_state"] = 1
            self.assertEqual(position_history_snapshots(feed, Path(directory)), {})
            self.assertEqual(list(Path(directory).glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
