import unittest

from weekly_ads_monitor.publish_accumulated_sheet import plan_color
from weekly_ads_monitor.publish_google_sheet import GREEN, RED, YELLOW


class PlanColorTests(unittest.TestCase):
    def test_directional_kpis(self):
        self.assertEqual(plan_color("higher_is_better", .15), GREEN)
        self.assertEqual(plan_color("higher_is_better", -.15), YELLOW)
        self.assertEqual(plan_color("higher_is_better", -.21), RED)
        self.assertEqual(plan_color("lower_is_better", -.15), GREEN)
        self.assertEqual(plan_color("lower_is_better", .15), YELLOW)

    def test_spend_and_ignored_kpis(self):
        self.assertEqual(plan_color("deviation_is_bad", -.15), YELLOW)
        self.assertEqual(plan_color("deviation_is_bad", .21), RED)
        self.assertIsNone(plan_color("ignore", .50))
        self.assertIsNone(plan_color("higher_is_better", .09))


if __name__ == "__main__":
    unittest.main()
