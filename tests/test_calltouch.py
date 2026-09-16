import unittest
from unittest.mock import patch

from weekly_ads_monitor.calltouch import fetch_yandex_direct_leads_by_session
from weekly_ads_monitor.models import Period
from datetime import date


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


class CalltouchTests(unittest.TestCase):
    @patch("weekly_ads_monitor.calltouch.json.load")
    @patch("weekly_ads_monitor.calltouch.urllib.request.urlopen")
    def test_counts_only_yandex_direct_linked_requests_by_session_date(self, urlopen, load):
        urlopen.return_value = _Response()
        load.return_value = [
            {"yandexDirect": {"campaignId": 1}, "session": {"sessionDate": "01/09/2026 10:00:00"}},
            {"yandexDirect": {"campaignId": 1}, "session": {"sessionDate": "01/09/2026 11:00:00"}},
            {"yandexDirect": None, "session": {"sessionDate": "01/09/2026 12:00:00"}},
        ]
        result = fetch_yandex_direct_leads_by_session(
            "secret", 37805, Period(date(2026, 9, 1), date(2026, 9, 1))
        )
        self.assertEqual(result, {date(2026, 9, 1): 2})
        requested_url = urlopen.call_args.args[0]
        self.assertIn("bindTo=session", requested_url)
        self.assertIn("withYandexDirect=true", requested_url)


if __name__ == "__main__":
    unittest.main()
