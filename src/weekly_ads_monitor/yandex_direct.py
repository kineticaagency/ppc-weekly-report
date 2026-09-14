from __future__ import annotations

import csv
import io
from collections import defaultdict

from .http import request_text
from .models import Metrics, Period


REPORTS_URL = "https://api.direct.yandex.com/json/v501/reports"


class YandexDirectClient:
    def __init__(self, token: str, client_login: str, campaign_ids: list[int], include_vat: bool):
        self.token = token
        self.client_login = client_login
        self.campaign_ids = campaign_ids
        self.include_vat = include_vat

    def fetch(self, period: Period) -> list[dict[str, str]]:
        fields = ["Date", "CampaignId", "CampaignName", "AdNetworkType", "Impressions", "Clicks", "Cost"]
        selection = {
            "DateFrom": period.start.isoformat(),
            "DateTo": period.end.isoformat(),
        }
        if self.campaign_ids:
            selection["Filter"] = [
                {"Field": "CampaignId", "Operator": "IN", "Values": [str(x) for x in self.campaign_ids]}
            ]
        body = {
            "params": {
                "SelectionCriteria": selection,
                "FieldNames": fields,
                "ReportName": f"weekly_monitor_{period.start:%Y%m%d}_{period.end:%Y%m%d}",
                "ReportType": "CUSTOM_REPORT",
                "DateRangeType": "CUSTOM_DATE",
                "Format": "TSV",
                "IncludeVAT": "YES" if self.include_vat else "NO",
            }
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Client-Login": self.client_login,
            "Accept-Language": "ru",
            "returnMoneyInMicros": "false",
            "processingMode": "auto",
            "skipReportHeader": "true",
            "skipReportSummary": "true",
            "Content-Type": "application/json; charset=utf-8",
        }
        text = request_text(REPORTS_URL, headers=headers, body=body, retries=8)
        return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def aggregate(rows: list[dict[str, str]]) -> dict[str, Metrics]:
    result: dict[str, Metrics] = defaultdict(Metrics)
    network_names = {"SEARCH": "search", "AD_NETWORK": "context"}
    for row in rows:
        network = network_names.get(row["AdNetworkType"], row["AdNetworkType"].lower())
        keys = ("account", f"network:{network}", f"campaign:{row['CampaignId']}")
        for key in keys:
            item = result[key]
            item.spend += float(row["Cost"])
            item.impressions += int(row["Impressions"])
            item.clicks += int(row["Clicks"])
    return dict(result)
