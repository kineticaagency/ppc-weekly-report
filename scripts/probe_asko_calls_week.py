from __future__ import annotations

import json
from pathlib import Path

from weekly_ads_monitor.env import load_env
from weekly_ads_monitor.http import request_json


def main() -> None:
    env = load_env(Path('.env.local'))
    headers = {'Api-key': env['ROISTAT_API_KEY'], 'Content-Type': 'application/json'}
    period = {'from': '2026-08-03T00:00:00+0300', 'to': '2026-08-09T23:59:59+0300'}
    for dimensions in ([], ['marker_level_1'], ['order_field_1']):
        response = request_json(
            'https://cloud.roistat.com/api/v1/project/analytics/data?project=187383',
            headers=headers,
            body={
                'period': period,
                'metrics': ['calls', 'uniqueCalls', 'uniquePhoneCalls', 'answeredCalls', 'missedCalls'],
                'dimensions': dimensions,
            },
        )
        print('ANALYTICS', dimensions, json.dumps(response, ensure_ascii=False)[:12000])
    calltracking = request_json(
        'https://cloud.roistat.com/api/v1/project/calltracking/data?project=187383',
        headers=headers,
        body={'period': period},
    )
    data = calltracking.get('data', {})
    print('CALLTRACKING_KEYS', sorted(data))
    print('CALLTRACKING_HOURLY', json.dumps(data.get('hourlyWeeklyQuantity'), ensure_ascii=False))


if __name__ == '__main__':
    main()
