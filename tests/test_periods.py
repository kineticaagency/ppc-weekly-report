from datetime import date
import unittest

from weekly_ads_monitor.periods import calendar_progress, completed_weeks


class PeriodTests(unittest.TestCase):
    def test_completed_weeks(self):
        latest, previous = completed_weeks(date(2026, 9, 2))
        self.assertEqual((latest.start, latest.end), (date(2026, 8, 24), date(2026, 8, 30)))
        self.assertEqual((previous.start, previous.end), (date(2026, 8, 17), date(2026, 8, 23)))

    def test_completed_weeks_includes_explicit_sunday_cutoff(self):
        latest, previous = completed_weeks(date(2026, 9, 13))
        self.assertEqual((latest.start, latest.end), (date(2026, 9, 7), date(2026, 9, 13)))
        self.assertEqual((previous.start, previous.end), (date(2026, 8, 31), date(2026, 9, 6)))

    def test_calendar_progress(self):
        self.assertAlmostEqual(calendar_progress(date(2026, 9, 2)), 2 / 30)


if __name__ == "__main__":
    unittest.main()
