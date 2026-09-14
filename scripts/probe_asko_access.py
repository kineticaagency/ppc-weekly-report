from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from weekly_ads_monitor.env import load_env


def call(url: str, *, token_header: tuple[str, str], body: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET")
    request.add_header(*token_header)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw[:500]
        return exc.code, payload


def main() -> None:
    env = load_env(Path(".env.local"))
    metrika_token = env.get("YANDEX_METRIKA_OAUTH_TOKEN", env["YANDEX_DIRECT_OAUTH_TOKEN"])
    oauth = ("Authorization", f"OAuth {metrika_token}")
    direct_body = {"method": "get", "params": {"SelectionCriteria": {},
                   "FieldNames": ["Id", "Name", "State", "Status", "Type"]}}
    request = urllib.request.Request("https://api.direct.yandex.com/json/v5/campaigns",
                                     data=json.dumps(direct_body).encode(), method="POST")
    request.add_header("Authorization", f"Bearer {env['YANDEX_DIRECT_OAUTH_TOKEN']}")
    request.add_header("Client-Login", "asko-hall-direct")
    request.add_header("Accept-Language", "ru")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode())
            campaigns = result.get("result", {}).get("Campaigns", [])
            print("DIRECT", response.status, "campaigns", len(campaigns))
            for item in campaigns:
                print("CAMPAIGN", item.get("Id"), item.get("Name"), item.get("State"), item.get("Status"))
    except urllib.error.HTTPError as exc:
        print("DIRECT", exc.code, exc.read().decode("utf-8", errors="replace")[:700])

    status, counter = call("https://api-metrika.yandex.net/management/v1/counter/69158290", token_header=oauth)
    if isinstance(counter, dict) and counter.get("counter"):
        info = counter["counter"]
        print("METRIKA_COUNTER", status, info.get("id"), info.get("name"), info.get("time_zone_name"))
        for goal in info.get("goals", []):
            if goal.get("id") in (3069158290, 251176128):
                print("METRIKA_GOAL", goal.get("id"), "|", goal.get("name"), "|", goal.get("type"))
    else:
        print("METRIKA_COUNTER", status, json.dumps(counter, ensure_ascii=False)[:1200])
    params = urllib.parse.urlencode({
        "ids": "69158290", "date1": "7daysAgo", "date2": "yesterday",
        "metrics": "ym:s:goal3069158290reaches,ym:s:goal251176128reaches",
        "dimensions": "ym:s:date,ym:s:cross_device_last_significantDirectClickOrder",
        "accuracy": "full", "attribution": "cross_device_last_significant",
    })
    status, stats = call(f"https://api-metrika.yandex.net/stat/v1/data?{params}", token_header=oauth)
    if isinstance(stats, dict) and status == 200:
        print("METRIKA_STATS", status, "sampled", stats.get("sampled"), "rows", len(stats.get("data", [])))
        print("METRIKA_TOTALS", stats.get("totals"))
        for row in stats.get("data", [])[:20]:
            print("METRIKA_ROW", json.dumps(row, ensure_ascii=False))
    else:
        print("METRIKA_STATS", status, json.dumps(stats, ensure_ascii=False)[:1200])

    api = ("Api-key", env["ROISTAT_API_KEY"])
    for endpoint in ("metrics-new", "dimensions"):
        status, result = call(f"https://cloud.roistat.com/api/v1/project/analytics/{endpoint}?project=187383",
                              token_header=api, body={})
        print("ROISTAT", endpoint, status, "status", result.get("status") if isinstance(result, dict) else "text")
        if endpoint == "metrics-new" and isinstance(result, dict):
            for item in result.get("metrics", []):
                searchable = " ".join(str(item.get(k, "")) for k in ("name", "title", "info")).lower()
                if any(word in searchable for word in ("call", "звон", "phone")):
                    print("ROISTAT_METRIC", item.get("name"), "|", item.get("title"), "|", item.get("type"))
    status, calls = call("https://cloud.roistat.com/api/v1/project/calltracking/data?project=187383",
                         token_header=api, body={"period": {"from": "2026-09-01T00:00:00+0300",
                                                            "to": "2026-09-07T23:59:59+0300"}})
    print("ROISTAT_CALLTRACKING", status, json.dumps(calls, ensure_ascii=False)[:1800])
    if isinstance(calls, dict):
        def walk(value, path=""):
            if isinstance(value, dict):
                for key, child in value.items():
                    child_path = f"{path}.{key}" if path else key
                    if "unique" in key.lower():
                        print("ROISTAT_UNIQUE_FIELD", child_path, json.dumps(child, ensure_ascii=False)[:1000])
                    walk(child, child_path)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")
        walk(calls)
    status, unique_by_day = call(
        "https://cloud.roistat.com/api/v1/project/analytics/data?project=187383",
        token_header=api,
        body={
            "period": {"from": "2026-08-01T00:00:00+0300", "to": "2026-09-06T23:59:59+0300"},
            "metrics": ["uniqueCalls"],
            "dimensions": [],
        },
    )
    print("ROISTAT_UNIQUE_BY_DAY", status, json.dumps(unique_by_day, ensure_ascii=False)[:5000])


if __name__ == "__main__":
    main()
