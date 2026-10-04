import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from copycat_telegram_alerts import build_hourly_brief, flow_summary


class TelegramAlertTests(unittest.TestCase):
    def test_flow_without_breadth_does_not_claim_zero_wallets(self):
        buying = flow_summary({"coin": "BTC", "net_value_flow_usd": 125_000, "net_buyer_count": 0})
        selling = flow_summary({"coin": "ETH", "net_value_flow_usd": -75_000, "net_buyer_count": 0})

        self.assertIn("net buying flow", buying)
        self.assertIn("net selling flow", selling)
        self.assertNotIn("0 more wallets", buying + selling)

    def test_hourly_brief_uses_distinct_wallet_breadth_when_available(self):
        message = build_hourly_brief({
            "flow": [
                {"coin": "BTC", "net_value_flow_usd": 125_000, "net_buyer_count": 4},
                {"coin": "ETH", "net_value_flow_usd": -75_000, "net_buyer_count": -3},
            ]
        })

        self.assertIn("4 more wallets buying", message)
        self.assertIn("3 more wallets selling", message)
        self.assertLessEqual(len(message), 4096)


if __name__ == "__main__":
    unittest.main()
