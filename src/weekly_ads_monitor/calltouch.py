from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import json
import urllib.parse
import urllib.request

from .models import Period


def fetch_yandex_direct_leads_by_session(
    token: str,
    site_id: int,
    period: Period,
    attribution: int = 1,
) -> dict[date, int]:
    """Return all Calltouch requests linked to Yandex Direct, grouped by session date."""
    params = urllib.parse.urlencode({
        "clientApiId": token,
        "siteId": site_id,
        "dateFrom": period.start.strftime("%m/%d/%Y"),
        "dateTo": period.end.strftime("%m/%d/%Y"),
        "attribution": attribution,
        "bindTo": "session",
        "withYandexDirect": "true",
    })
    url = f"https://api.calltouch.ru/calls-service/RestAPI/requests?{params}"
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.load(response)
    result: dict[date, int] = defaultdict(int)
    for item in payload:
        if not item.get("yandexDirect"):
            continue
        session_date = (item.get("session") or {}).get("sessionDate")
        if not session_date:
            continue
        day = datetime.strptime(session_date, "%d/%m/%Y %H:%M:%S").date()
        if period.start <= day <= period.end:
            result[day] += 1
    return dict(result)
