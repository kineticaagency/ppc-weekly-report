from __future__ import annotations

import argparse
import calendar
import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
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
    parser.add_argument("--as-of", type=date.fromisoformat,
                        default=date.today() - timedelta(days=date.today().weekday() + 1))
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    secrets = load_env(Path(".env.local"))
    history_start, history_end = date(2026, 8, 1), args.as_of
    segments = []
    cursor = history_start
    while cursor <= history_end:
        sunday = cursor + timedelta(days=6 - cursor.weekday())
        month_end = cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1])
        end = min(sunday, month_end, history_end)
        segments.append(Period(cursor, end))
        cursor = end + timedelta(days=1)
    whole = Period(history_start, history_end)
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
    latest_period = Period(history_end - timedelta(days=6), history_end)
    previous_period = Period(history_end - timedelta(days=13), history_end - timedelta(days=7))
    latest = _period_raw(daily, latest_period)
    previous = _period_raw(daily, previous_period)
    month_facts = {}
    for month in range(history_start.month, history_end.month + 1):
        end = min(date(history_end.year, month, calendar.monthrange(history_end.year, month)[1]),
                  history_end)
        month_facts[month] = _period_raw(daily, Period(date(history_end.year, month, 1), end))
    plan = _fetch_plan(config["plan"]["csv_url"], history_end.replace(day=1))
    fact = month_facts[history_end.month]
    client = GoogleSheetsClient(Path(args.credentials))
    sheet_id = _write_sheet(
        client, config["google_sheets"]["spreadsheet_id"], config["google_sheets"]["tab_name"],
        config, values, latest, previous, month_facts, plan, fact, history_end,
    )
    print(f"https://docs.google.com/spreadsheets/d/{config['google_sheets']['spreadsheet_id']}/edit#gid={sheet_id}")


if __name__ == "__main__":
    main()
