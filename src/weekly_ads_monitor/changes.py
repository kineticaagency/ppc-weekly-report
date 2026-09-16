from __future__ import annotations

from datetime import date, datetime, timedelta

from .google_sheets import GoogleSheetsClient
from .models import Period


MONTH_TABS = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
    7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def _parse_date(value: str) -> date | None:
    parts = value.strip().split()
    if not parts:
        return None
    raw = parts[0]
    for pattern in ("%d.%m.%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            pass
    return None


def _month_starts(start: date, end: date):
    cursor = start.replace(day=1)
    while cursor <= end:
        yield cursor
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)


def fetch_project_changes(
    client: GoogleSheetsClient,
    spreadsheet_id: str,
    project: str,
    period: Period,
    lookback_days: int = 3,
) -> list[dict[str, str]]:
    start = period.start - timedelta(days=lookback_days)
    metadata = client.metadata(spreadsheet_id)
    sheets = {item["properties"]["title"].strip(): item["properties"] for item in metadata["sheets"]}
    result: list[dict[str, str]] = []
    for month in _month_starts(start, period.end):
        title = f"{MONTH_TABS[month.month]} {month.year}"
        props = sheets.get(title)
        if not props:
            continue
        row_count = props.get("gridProperties", {}).get("rowCount", 1000)
        rows = client.values_get(spreadsheet_id, f"'{props['title']}'!A1:M{row_count}")
        if not rows:
            continue
        headers = {str(value).strip(): index for index, value in enumerate(rows[0])}
        required = {"Дата", "Проект", "Правка"}
        if not required.issubset(headers):
            raise ValueError(f"Unexpected changes sheet structure in {props['title']}")

        def value(row: list, header: str) -> str:
            index = headers.get(header)
            return str(row[index]).strip() if index is not None and index < len(row) else ""

        for row in rows[1:]:
            changed_at = _parse_date(value(row, "Дата"))
            if changed_at is None or not start <= changed_at <= period.end:
                continue
            if value(row, "Проект").casefold() != project.casefold():
                continue
            change = value(row, "Правка")
            if not change:
                continue
            result.append({
                "date": changed_at.isoformat(),
                "system": value(row, "Система"),
                "campaign": value(row, "Название РК"),
                "change": change,
                "objective": value(row, "Зачем это делать? В чем проблема? KPI"),
                "change_type": value(row, "Характер правки"),
                "timing": "during" if changed_at >= period.start else "before",
            })
    return sorted(result, key=lambda item: (item["date"], item["campaign"], item["change"]))
