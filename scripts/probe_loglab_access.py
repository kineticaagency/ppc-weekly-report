from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from weekly_ads_monitor.env import load_env


def get(url: str, token: str) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"OAuth {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    env = load_env(Path(".env.local"))
    direct_body = {"method": "get", "params": {"SelectionCriteria": {},
                   "FieldNames": ["Id", "Name", "State", "Status", "Type"]}}
    request = urllib.request.Request("https://api.direct.yandex.com/json/v5/campaigns",
        data=json.dumps(direct_body).encode(), method="POST", headers={
            "Authorization": f"Bearer {env['YANDEX_DIRECT_OAUTH_TOKEN']}",
            "Client-Login": "porg-zsyy7hra", "Accept-Language": "ru",
            "Content-Type": "application/json",
        })
    with urllib.request.urlopen(request, timeout=30) as response:
        campaigns = json.loads(response.read().decode()).get("result", {}).get("Campaigns", [])
    print("DIRECT", len(campaigns))
    for item in campaigns:
        if item.get("State") == "ON" or item.get("Status") == "ACCEPTED":
            print("CAMPAIGN", item.get("Id"), "|", item.get("Name"), "|", item.get("State"), "|", item.get("Status"))

    token = env["YANDEX_METRIKA_OAUTH_TOKEN"]
    counter = get("https://api-metrika.yandex.net/management/v1/counter/78913450", token)["counter"]
    print("COUNTER", counter.get("id"), "|", counter.get("name"), "|", counter.get("time_zone_name"))
    wanted = {496158533, 496158420, 517594584}
    goals = get("https://api-metrika.yandex.net/management/v1/counter/78913450/goals", token)
    found = set()
    for goal in goals.get("goals", []):
        if goal.get("id") in wanted:
            found.add(goal["id"])
            print("GOAL", goal.get("id"), "|", goal.get("name"), "|", goal.get("type"), "|", goal.get("status"))
    print("MISSING", sorted(wanted - found))


if __name__ == "__main__":
    main()
