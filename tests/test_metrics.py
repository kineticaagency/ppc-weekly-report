import unittest

from weekly_ads_monitor.models import Metrics
from weekly_ads_monitor.yandex_direct import aggregate


class MetricsTests(unittest.TestCase):
    def test_derived(self):
        values = Metrics(spend=1000, impressions=10000, clicks=100, leads=10, target_leads=4, unprocessed_leads=2).derived()
        self.assertEqual(values["ctr"], 0.01)
        self.assertEqual(values["cpc"], 10)
        self.assertEqual(values["cpa"], 100)
        self.assertEqual(values["cr"], 0.1)
        self.assertEqual(values["target_cpa"], 250)
        self.assertEqual(values["target_share"], 0.4)
        self.assertEqual(values["unprocessed_share"], 0.2)

    def test_zero_denominators(self):
        values = Metrics().derived()
        self.assertTrue(all(value is None for value in values.values()))

    def test_direct_network_names_are_normalized(self):
        rows = [{
            "CampaignId": "1", "AdNetworkType": "AD_NETWORK",
            "Cost": "10", "Impressions": "20", "Clicks": "2",
        }]
        result = aggregate(rows)
        self.assertIn("network:context", result)
        self.assertNotIn("network:AD_NETWORK", result)


if __name__ == "__main__":
    unittest.main()
