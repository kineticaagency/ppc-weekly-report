from __future__ import annotations

from collections import defaultdict

from .http import request_json
from .models import Metrics, Period


ANALYTICS_URL = "https://cloud.roistat.com/api/v1/project/analytics/data"


class RoistatClient:
    def __init__(self, api_key: str, project_id: int, source_marker: str, status_groups: dict[str, set[str]]):
        self.api_key = api_key
        self.project_id = project_id
        self.source_marker = source_marker
        self.status_groups = status_groups

    def fetch(self, period: Period) -> dict[str, Metrics]:
        common = {
            "metrics": ["leads"],
            "period": {
                "from": f"{period.start.isoformat()}T00:00:00+0300",
                "to": f"{period.end.isoformat()}T23:59:59+0300",
            },
            "filters": [{"field": "marker_level_1", "operation": "=", "value": self.source_marker}],
        }
        totals_response = request_json(
            f"{ANALYTICS_URL}?project={self.project_id}",
            headers={"Api-key": self.api_key, "Content-Type": "application/json"},
            body={**common, "dimensions": ["marker_level_1", "marker_level_2", "marker_level_3"]},
        )
        status_response = request_json(
            f"{ANALYTICS_URL}?project={self.project_id}",
            headers={"Api-key": self.api_key, "Content-Type": "application/json"},
            body={**common, "dimensions": ["marker_level_1", "marker_level_2", "marker_level_3", "order_field_1"]},
        )
        for response in (totals_response, status_response):
            if response.get("status") != "success":
                raise RuntimeError(f"Roistat error: {response}")
        result: dict[str, Metrics] = defaultdict(Metrics)
        for block in totals_response.get("data", []):
            for row in block.get("items", []):
                dimensions = row["dimensions"]
                network = dimensions["marker_level_2"]["value"]
                campaign = dimensions["marker_level_3"]["value"]
                leads = int(row["metrics"][0]["value"])
                for key in ("account", f"network:{network}", f"campaign:{campaign}"):
                    result[key].leads += leads
        for block in status_response.get("data", []):
            for row in block.get("items", []):
                dimensions = row["dimensions"]
                network = dimensions["marker_level_2"]["value"]
                campaign = dimensions["marker_level_3"]["value"]
                status = dimensions["order_field_1"]["title"]
                leads = int(row["metrics"][0]["value"])
                for key in ("account", f"network:{network}", f"campaign:{campaign}"):
                    item = result[key]
                    if status in self.status_groups["target"]:
                        item.target_leads += leads
                    elif status in self.status_groups["non_target"]:
                        item.non_target_leads += leads
                    elif status in self.status_groups["unprocessed"]:
                        item.unprocessed_leads += leads
                    else:
                        item.unclassified_leads += leads
        for item in result.values():
            classified = item.target_leads + item.non_target_leads + item.unprocessed_leads + item.unclassified_leads
            item.unclassified_leads += max(item.leads - classified, 0)
        return dict(result)
