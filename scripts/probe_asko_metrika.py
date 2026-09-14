from __future__ import annotations

import json
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

from weekly_ads_monitor.env import load_env


def get(url: str, token: str) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"OAuth {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode("utf-8")) from exc


def main() -> None:
    token = load_env(Path(".env.local"))["YANDEX_METRIKA_OAUTH_TOKEN"]
    counter = get("https://api-metrika.yandex.net/management/v1/counter/69158290", token)["counter"]
    print("COUNTER", counter.get("id"), "|", counter.get("name"), "|", counter.get("time_zone_name"))
    wanted = {3069158290, 251176128}
    goals = get("https://api-metrika.yandex.net/management/v1/counter/69158290/goals", token)
    for goal in goals.get("goals", []):
        if goal.get("id") in wanted:
            print("GOAL", goal.get("id"), "|", goal.get("name"), "|", goal.get("type"))
    params = urllib.parse.urlencode({
        "ids": "69158290", "date1": "2026-08-01", "date2": "2026-09-06",
        "metrics": "ym:s:goal3069158290visits,ym:s:goal251176128visits",
        "dimensions": (
            "ym:s:date,"
            "ym:s:cross_device_last_significantTrafficSource,"
            "ym:s:cross_device_last_significantSourceEngine,"
            "ym:s:cross_device_last_significantDirectClickOrder"
        ),
        "accuracy": "full", "attribution": "cross_device_last_significant", "lang": "ru",
    })
    stats = get(f"https://api-metrika.yandex.net/stat/v1/data?{params}", token)
    print("STATS", "sampled", stats.get("sampled"), "rows", len(stats.get("data", [])),
          "totals", stats.get("totals"))
    for row in stats.get("data", []):
        print("ROW", json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
