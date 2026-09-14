from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

from .env import load_env
from .google_sheets import GoogleSheetsClient
from .models import Period
from .publish_asko_hall import _derived, _empty, _fetch_plan, _period_raw, _sum, _write_sheet
from .yandex_direct import YandexDirectClient


def _fetch_target_visits(token: str, config: dict, start: date, end: date) -> dict[date, int]:
    metrika = config["yandex_metrika"]
    goal_filter = " OR ".join(
        f"ym:s:goal{goal_id}IsReached=='Yes'" for goal_id in metrika["goal_ids"]
    )
    params = urllib.parse.urlencode({
        "ids": str(metrika["counter_id"]),
        "date1": start.isoformat(), "date2": end.isoformat(),
        "metrics": "ym:s:visits",
        "dimensions": (
            "ym:s:date,ym:s:cross_device_last_significantTrafficSource,"
            "ym:s:cross_device_last_significantSourceEngine"
        ),
        "filters": f"({goal_filter})",
        "accuracy": "full", "attribution": metrika["attribution"], "lang": "ru", "limit": 100000,
    })
    request = urllib.request.Request(
        f"https://api-metrika.yandex.net/stat/v1/data?{params}",
        headers={"Authorization": f"OAuth {token}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get("sampled"):
        raise RuntimeError("Metrika returned sampled data")
    result: dict[date, int] = defaultdict(int)
    for row in payload.get("data", []):
        dimensions = row["dimensions"]
        if dimensions[1].get("name") != metrika["traffic_source"]:
            continue
        if dimensions[2].get("name") not in metrika["source_engines"]:
            continue
        result[date.fromisoformat(dimensions[0]["name"])] += round(row["metrics"][0])
    return dict(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/loglab.json")
    parser.add_argument("--credentials", default=".secrets/google-service-account.json")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    secrets = load_env(Path(".env.local"))
    segments = [
        Period(date(2026, 8, 1), date(2026, 8, 2)),
        Period(date(2026, 8, 3), date(2026, 8, 9)),
        Period(date(2026, 8, 10), date(2026, 8, 16)),
        Period(date(2026, 8, 17), date(2026, 8, 23)),
        Period(date(2026, 8, 24), date(2026, 8, 30)),
        Period(date(2026, 8, 31), date(2026, 8, 31)),
        Period(date(2026, 9, 1), date(2026, 9, 6)),
    ]
    whole = Period(date(2026, 8, 1), date(2026, 9, 6))
    yd = config["yandex_direct"]
    direct_rows = YandexDirectClient(
        secrets["YANDEX_DIRECT_OAUTH_TOKEN"], yd["client_login"],
        yd["campaign_ids"], yd["include_vat"],
    ).fetch(whole)
    daily: dict[date, dict] = defaultdict(_empty)
    for row in direct_rows:
        day = date.fromisoformat(row["Date"])
        daily[day]["spend"] += float(row["Cost"])
        daily[day]["impressions"] += int(row["Impressions"])
        daily[day]["clicks"] += int(row["Clicks"])
    visits = _fetch_target_visits(
        secrets["YANDEX_METRIKA_OAUTH_TOKEN"], config, whole.start, whole.end
    )
    for day, count in visits.items():
        daily[day]["leads"] += count
    values = [(period, _period_raw(daily, period)) for period in segments]
    previous = values[4][1]
    latest = _sum([values[5][1], values[6][1]])
    month_facts = {
        8: _period_raw(daily, Period(date(2026, 8, 1), date(2026, 8, 31))),
        9: _period_raw(daily, Period(date(2026, 9, 1), date(2026, 9, 6))),
    }
    plan = _fetch_plan(config["plan"]["csv_url"], date(2026, 9, 1))
    fact = values[6][1]
    client = GoogleSheetsClient(Path(args.credentials))
    sheet_id = _write_sheet(
        client, config["google_sheets"]["spreadsheet_id"], config["google_sheets"]["tab_name"],
        config, values, latest, previous, month_facts, plan, fact, date(2026, 9, 6),
    )
    print(f"https://docs.google.com/spreadsheets/d/{config['google_sheets']['spreadsheet_id']}/edit#gid={sheet_id}")


if __name__ == "__main__":
    main()
