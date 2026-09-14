from __future__ import annotations

import calendar
from datetime import date
from pathlib import Path

from weekly_ads_monitor.env import load_env
from weekly_ads_monitor.models import Period
from weekly_ads_monitor.publish_asko_hall import _fetch_unique_calls


def main() -> None:
    key = load_env(Path('.env.local'))['ROISTAT_API_KEY']
    for start_day, end_day in ((1, 4), (5, 11), (12, 18), (19, 25), (26, 31)):
        period = Period(date(2026, 1, start_day), date(2026, 1, end_day))
        try:
            print(period.label, 'OK', _fetch_unique_calls(key, 187383, 'direct1', period))
        except Exception as exc:
            print(period.label, 'ERROR', exc)
    for month in range(1, 10):
        end = min(date(2026, month, calendar.monthrange(2026, month)[1]), date(2026, 9, 6))
        period = Period(date(2026, month, 1), end)
        try:
            value = _fetch_unique_calls(key, 187383, 'direct1', period)
            print(period.label, 'OK', value)
        except Exception as exc:
            print(period.label, 'ERROR', exc)


if __name__ == '__main__':
    main()
