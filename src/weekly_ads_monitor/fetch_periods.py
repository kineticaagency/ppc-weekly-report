from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .env import load_env
from .models import Period
from .report import merge_metrics, serialize_period
from .roistat import RoistatClient
from .yandex_direct import YandexDirectClient, aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch exact read-only periods")
    parser.add_argument("--period", action="append", required=True, help="YYYY-MM-DD..YYYY-MM-DD")
    parser.add_argument("--config", default="config/reduktor40.json")
    parser.add_argument("--env", default=".env.local")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    secrets = load_env(Path(args.env))
    yd, ro = config["yandex_direct"], config["roistat"]
    direct = YandexDirectClient(secrets["YANDEX_DIRECT_OAUTH_TOKEN"], yd["client_login"],
                                yd["campaign_ids"], yd["include_vat"])
    roistat = RoistatClient(secrets["ROISTAT_API_KEY"], ro["project_id"], ro["source_marker"], {
        "target": set(ro["target_status_titles"]),
        "non_target": set(ro["non_target_status_titles"]),
        "unprocessed": set(ro["unprocessed_status_titles"]),
    })
    threshold = config["quality"]["preliminary_unprocessed_share"]
    result = []
    for raw in args.period:
        start, end = (date.fromisoformat(value) for value in raw.split(".."))
        period = Period(start, end)
        merged = merge_metrics(aggregate(direct.fetch(period)), roistat.fetch(period))
        result.append(serialize_period(period, merged, threshold))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"periods": result}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
