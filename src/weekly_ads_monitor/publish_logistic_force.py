from __future__ import annotations

import argparse
import calendar
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .changes import fetch_project_changes
from .env import load_env
from .google_sheets import GoogleSheetsClient
from .models import Period
from .publish_asko_hall import _empty, _fetch_plan, _period_raw, _write_sheet
from .publish_loglab import _fetch_target_visits
from .yandex_direct import YandexDirectClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/logistic-force.json")
    parser.add_argument("--credentials", default=".secrets/google-service-account.json")
    parser.add_argument(
        "--as-of", type=date.fromisoformat,
        default=date.today() - timedelta(days=date.today().weekday() + 1),
    )
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    secrets = load_env(Path(".env.local"))
    history_start, history_end = date(2026, 9, 1), args.as_of
    whole = Period(history_start, history_end)

    segments: list[Period] = []
    cursor = history_start
    while cursor <= history_end:
        sunday = cursor + timedelta(days=6 - cursor.weekday())
        month_end = cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1])
        end = min(sunday, month_end, history_end)
        segments.append(Period(cursor, end))
        cursor = end + timedelta(days=1)

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
    month_facts = {
        history_end.month: _period_raw(
            daily, Period(history_end.replace(day=1), history_end)
        )
    }
    plan = _fetch_plan(config["plan"]["csv_url"], history_end.replace(day=1))
    fact = month_facts[history_end.month]
    client = GoogleSheetsClient(Path(args.credentials))
    source = config.get("changes_source")
    operational_changes = fetch_project_changes(
        client, source["spreadsheet_id"], config["project"], latest_period,
        source.get("lookback_days", 3),
    ) if source else []
    sheet_id = _write_sheet(
        client, config["google_sheets"]["spreadsheet_id"],
        config["google_sheets"]["tab_name"], config, values, latest, previous,
        month_facts, plan, fact, history_end, operational_changes,
    )
    print(
        f"https://docs.google.com/spreadsheets/d/"
        f"{config['google_sheets']['spreadsheet_id']}/edit#gid={sheet_id}"
    )


if __name__ == "__main__":
    main()
