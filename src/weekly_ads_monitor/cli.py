from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .env import load_env
from .diagnostics import analyze
from .markdown_report import write_markdown
from .periods import calendar_progress, completed_weeks, month_to_date
from .plans import fetch_month_plan
from .report import compare, merge_metrics, serialize_period
from .roistat import RoistatClient
from .yandex_direct import YandexDirectClient, aggregate


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only weekly ads monitor")
    parser.add_argument("--config", default="config/reduktor40.json")
    parser.add_argument("--env", default=".env.local")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output", default="output/reduktor40-report.json")
    parser.add_argument("--markdown", default="output/reduktor40-report.md")
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    secrets = load_env(Path(args.env))
    yd_cfg = config["yandex_direct"]
    ro_cfg = config["roistat"]
    direct = YandexDirectClient(
        secrets["YANDEX_DIRECT_OAUTH_TOKEN"], yd_cfg["client_login"], yd_cfg["campaign_ids"], yd_cfg["include_vat"]
    )
    roistat = RoistatClient(
        secrets["ROISTAT_API_KEY"], ro_cfg["project_id"], ro_cfg["source_marker"],
        {
            "target": set(ro_cfg["target_status_titles"]),
            "non_target": set(ro_cfg["non_target_status_titles"]),
            "unprocessed": set(ro_cfg["unprocessed_status_titles"]),
        },
    )

    latest, previous = completed_weeks(args.as_of)
    mtd = month_to_date(args.as_of)
    periods = [latest, previous, mtd]
    datasets = {}
    campaign_names = {}
    campaign_networks = {}
    for period in periods:
        direct_rows = direct.fetch(period)
        campaign_names.update({row["CampaignId"]: row["CampaignName"] for row in direct_rows})
        for row in direct_rows:
            campaign_networks[f"campaign:{row['CampaignId']}"] = (
                "network:search" if row["AdNetworkType"] == "SEARCH" else "network:context"
            )
        datasets[period.label] = merge_metrics(aggregate(direct_rows), roistat.fetch(period))

    plan = fetch_month_plan(config["plan"]["csv_url"], config["plan"]["rows"], args.as_of)
    progress = calendar_progress(args.as_of)
    plan_to_date = {key: value * progress for key, value in plan.items() if key in {"spend", "clicks", "leads"}}
    plan_to_date.update({key: plan[key] for key in ("cpc", "cr", "cpa")})
    threshold = config["quality"]["preliminary_unprocessed_share"]
    labels = {
        "network:search": "Поиск",
        "network:context": "РСЯ",
        **{f"campaign:{key}": value for key, value in campaign_names.items()},
    }
    payload = {
        "project": config["project"],
        "as_of": args.as_of.isoformat(),
        "latest_week": serialize_period(latest, datasets[latest.label], threshold),
        "previous_week": serialize_period(previous, datasets[previous.label], threshold),
        "week_over_week": compare(datasets[latest.label]["account"], datasets[previous.label]["account"]),
        "diagnostics": analyze(
            datasets[latest.label]["account"], datasets[previous.label]["account"], threshold,
            datasets[latest.label], datasets[previous.label], labels, campaign_networks,
        ),
        "month_to_date": serialize_period(mtd, datasets[mtd.label], threshold),
        "month_plan": plan,
        "plan_to_date": plan_to_date,
        "labels": labels,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = Path(args.markdown)
    write_markdown(payload, markdown)
    print(output)
    print(markdown)


if __name__ == "__main__":
    main()
