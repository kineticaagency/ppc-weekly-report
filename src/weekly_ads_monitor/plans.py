from __future__ import annotations

import csv
import io
import re
from datetime import date
from urllib.request import urlopen


MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


def _number(value: str) -> float:
    cleaned = re.sub(r"[^0-9,.-]", "", value.replace("\u00a0", "")).replace(",", ".")
    return float(cleaned) if cleaned and cleaned != "-" else 0.0


def fetch_month_plan(url: str, row_labels: dict[str, str], month: date) -> dict[str, float]:
    with urlopen(url, timeout=60) as response:
        rows = list(csv.reader(io.StringIO(response.read().decode("utf-8-sig"))))
    target_header = f"{MONTHS_RU[month.month]} {month.year}"
    header = rows[0]
    try:
        column = header.index(target_header)
    except ValueError as exc:
        raise ValueError(f"Month {target_header!r} not found in plan") from exc
    lookup = {row[0]: row for row in rows if row}
    result = {}
    for metric, label in row_labels.items():
        if label not in lookup:
            raise ValueError(f"Plan row not found: {label!r}")
        result[metric] = _number(lookup[label][column])
    if result.get("cr", 0) > 1:
        result["cr"] /= 100
    return result

