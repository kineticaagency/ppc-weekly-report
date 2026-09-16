from __future__ import annotations

import argparse
import calendar
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .google_sheets import GoogleSheetsClient
from .diagnostics import analyze
from .models import Metrics
from .publish_google_sheet import BLUE, GREEN, LIGHT_BLUE, RED, WHITE, YELLOW, display_period

MONTHS = {1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
          7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"}
MONTHS_GENITIVE = {1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
                   7: "июля", 8: "августа", 9: "сентября", 10: "октября",
                   11: "ноября", 12: "декабря"}


def metric(values: dict) -> Metrics:
    return Metrics(**{key: values.get(key, 0) for key in (
        "spend", "impressions", "clicks", "leads", "target_leads", "non_target_leads",
        "unprocessed_leads", "unclassified_leads")})


def combine(*items: Metrics) -> Metrics:
    return Metrics(**{key: sum(getattr(item, key) for item in items) for key in Metrics.__dataclass_fields__})


def week_row(period: str, values: dict) -> list:
    return [display_period(period), values["spend"], values["impressions"], values["ctr"], values["clicks"],
            values["cpc"], values["cr"], values["leads"], values["cpa"], values["target_leads"],
            values["target_cpa"], values["target_share"]]


def value_cell(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, bool):
        return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, (int, float)):
        return {"userEnteredValue": {"numberValue": value}}
    return {"userEnteredValue": {"stringValue": str(value)}}


def repeat(sheet_id: int, r1: int, r2: int, c1: int, c2: int, fmt: dict, fields: str) -> dict:
    return {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": r1, "endRowIndex": r2,
                                       "startColumnIndex": c1, "endColumnIndex": c2},
                           "cell": {"userEnteredFormat": fmt}, "fields": fields}}


def merged(sheet_id: int, row: int, height: int = 1) -> dict:
    return {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": row,
                                       "endRowIndex": row + height, "startColumnIndex": 0,
                                       "endColumnIndex": 13}, "mergeType": "MERGE_ALL"}}


def row_height(sheet_id: int, start: int, end: int, pixels: int) -> dict:
    return {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "ROWS",
                                                       "startIndex": start, "endIndex": end},
                                           "properties": {"pixelSize": pixels}, "fields": "pixelSize"}}


def plan_color(direction: str, deviation: float | None) -> dict | None:
    if deviation is None or abs(deviation) < .10 or direction == "ignore":
        return None
    if direction == "deviation_is_bad":
        return YELLOW if abs(deviation) <= .20 else RED
    improves = (direction == "higher_is_better" and deviation > 0) or (
        direction == "lower_is_better" and deviation < 0)
    if improves:
        return GREEN
    return YELLOW if abs(deviation) <= .20 else RED


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish accumulated weekly project sheet")
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--tab", default="reduktor40.ru")
    parser.add_argument("--payload", default="output/reduktor40-report.json")
    parser.add_argument("--history-payload", action="append", default=[])
    parser.add_argument("--calendar-splits")
    parser.add_argument("--config", default="config/reduktor40.json")
    parser.add_argument("--credentials", default=".secrets/google-service-account.json")
    args = parser.parse_args()

    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    archive = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.history_payload]
    split_periods = []
    if args.calendar_splits:
        split_periods = json.loads(Path(args.calendar_splits).read_text(encoding="utf-8"))["periods"]
    weeks: dict[str, dict] = {}
    saved_comments: dict[str, str] = {}
    exact_facts: dict[tuple[int, int], dict] = {}
    for item in [*archive, payload]:
        for name in ("previous_week", "latest_week"):
            week = item[name]
            weeks.setdefault(week["period"], week)  # first saved closed-week snapshot wins
        latest_period = item["latest_week"]["period"]
        comment = item.get("diagnostics", {}).get("human_comment")
        if comment:
            saved_comments.setdefault(latest_period, comment)
        mtd = item.get("month_to_date")
        if mtd:
            start, end = (datetime.fromisoformat(value) for value in mtd["period"].split(".."))
            if start.day == 1 and end.day == calendar.monthrange(end.year, end.month)[1]:
                exact_facts[(end.year, end.month)] = mtd["rows"]["account"]

    ordered_weeks = sorted(weeks.values(), key=lambda item: item["period"])
    threshold = config.get("quality", {}).get("preliminary_unprocessed_share", .2)
    for index, week in enumerate(ordered_weeks):
        if week["period"] in saved_comments:
            continue
        if index == 0:
            saved_comments[week["period"]] = (
                "Для корректного сравнения недостаточно сохранённых данных предыдущей недели."
            )
            continue
        current = metric(week["rows"]["account"])
        previous = metric(ordered_weeks[index - 1]["rows"]["account"])
        saved_comments[week["period"]] = analyze(current, previous, threshold)["human_comment"]
    split_by_period = {item["period"]: item for item in split_periods}
    display_periods = []
    for week in ordered_weeks:
        start_raw, end_raw = week["period"].split("..")
        start, end = datetime.fromisoformat(start_raw), datetime.fromisoformat(end_raw)
        if (start.year, start.month) == (end.year, end.month):
            display_periods.append(week)
            continue
        parts = [item for key, item in split_by_period.items()
                 if start_raw <= key.split("..")[0] and key.split("..")[1] <= end_raw]
        display_periods.extend(sorted(parts, key=lambda item: item["period"]))

    grouped: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for period in display_periods:
        start = datetime.fromisoformat(period["period"].split("..")[0])
        grouped[(start.year, start.month)].append(period)

    client = GoogleSheetsClient(Path(args.credentials))
    metadata = client.metadata(args.spreadsheet_id)
    props = next(x["properties"] for x in metadata["sheets"] if x["properties"]["title"] == args.tab)
    sheet_id, grid = props["sheetId"], props["gridProperties"]
    if grid["columnCount"] < 13:
        client.batch_update(args.spreadsheet_id, [{"appendDimension": {
            "sheetId": sheet_id, "dimension": "COLUMNS", "length": 13 - grid["columnCount"]}}])
        grid["columnCount"] = 13

    existing_comments: dict[str, str] = {}
    for row in client.values_get(args.spreadsheet_id, f"'{args.tab}'!A1:M{grid['rowCount']}"):
        if len(row) >= 13 and re.fullmatch(r"\d{2}\.\d{2}\.\d{2}–\d{2}\.\d{2}\.\d{2}", str(row[0])):
            if str(row[12]).strip():
                existing_comments[str(row[0])] = str(row[12]).strip()

    headers = ["Период", "Расход", "Показы", "CTR", "Клики", "CPC", "CR", "Заявки", "CPA",
               "Целевые", "CPA целевой", "% целевых", "Комментарий"]
    updated_at = datetime.now(ZoneInfo(config.get("timezone", "Europe/Moscow")))
    rows = [[f"{payload['project']} — еженедельный мониторинг"],
            [f"Последнее обновление: {updated_at:%d.%m.%Y, %H:%M}"], []]
    sections = []

    def source_week(period_label: str) -> str:
        start_raw, end_raw = period_label.split("..")
        for week in ordered_weeks:
            week_start, week_end = week["period"].split("..")
            if week_start <= start_raw and end_raw <= week_end:
                return week["period"]
        return period_label

    for year_month in sorted(grouped):
        year, month = year_month
        title_row = len(rows)
        rows.extend([[f"{MONTHS[month]} {year}"], headers])
        week_rows = []
        for week in grouped[year_month]:
            values = week["rows"].get("account")
            if values is None:
                zero = Metrics()
                values = {**zero.__dict__, **zero.derived()}
            row_index = len(rows)
            visible_period = display_period(week["period"])
            comment = existing_comments.get(visible_period) or saved_comments.get(source_week(week["period"]), "")
            rows.append(week_row(week["period"], values) + [comment])
            week_rows.append(row_index)
        fact_values = exact_facts.get(year_month)
        if fact_values is None:
            total = combine(*(metric(week["rows"]["account"]) for week in grouped[year_month]))
            fact_values = {**total.__dict__, **total.derived()}
        fact_row = len(rows)
        rows.extend([["Факт"] + week_row(grouped[year_month][-1]["period"], fact_values)[1:] + [""], []])
        sections.append((title_row, title_row + 1, fact_row, week_rows))

    as_of = datetime.fromisoformat(payload["as_of"])
    plan_header = len(rows)
    rows.extend([[f"План/факт {MONTHS_GENITIVE[as_of.month]} на {as_of:%d.%m.%Y}"],
                 ["Показатель", "План месяца", "План на дату", "Факт", "Отклонение"]])
    plan_items = [("Расход", "spend"), ("Клики", "clicks"), ("Заявки", "leads"),
                  ("CPC", "cpc"), ("CR", "cr"), ("CPA", "cpa")]
    plan_start = len(rows)
    mtd = payload["month_to_date"]["rows"]["account"]
    for label, key in plan_items:
        plan_date, actual = payload["plan_to_date"][key], mtd[key]
        rows.append([label, payload["month_plan"][key], plan_date, actual,
                     actual / plan_date - 1 if plan_date else None])
    rows.append([])
    row_count = len(rows)
    if grid["rowCount"] < row_count:
        client.batch_update(args.spreadsheet_id, [{"appendDimension": {
            "sheetId": sheet_id, "dimension": "ROWS", "length": row_count - grid["rowCount"]}}])
        grid["rowCount"] = row_count

    padded = rows + [[] for _ in range(grid["rowCount"] - row_count)]
    update_rows = [{"values": [value_cell(v) for v in row + [None] * (13 - len(row))]} for row in padded]
    requests = [
        {"unmergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0,
                                      "endRowIndex": grid["rowCount"], "startColumnIndex": 0,
                                      "endColumnIndex": 13}}},
        {"updateCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0,
                                     "endRowIndex": grid["rowCount"], "startColumnIndex": 0,
                                     "endColumnIndex": 13}, "rows": update_rows, "fields": "userEnteredValue"}},
        repeat(sheet_id, 0, grid["rowCount"], 0, 13, {}, "userEnteredFormat"),
        merged(sheet_id, 0), merged(sheet_id, 1),
        repeat(sheet_id, 0, row_count, 0, 13,
               {"textFormat": {"fontFamily": "Montserrat", "fontSize": 10},
                "verticalAlignment": "MIDDLE"},
               "userEnteredFormat.textFormat,userEnteredFormat.verticalAlignment"),
        repeat(sheet_id, 0, 1, 0, 13,
               {"backgroundColor": BLUE, "horizontalAlignment": "CENTER",
                "textFormat": {"bold": True, "foregroundColor": WHITE,
                               "fontFamily": "Montserrat", "fontSize": 14}}, "userEnteredFormat"),
        repeat(sheet_id, 1, 2, 0, 13,
               {"horizontalAlignment": "LEFT", "verticalAlignment": "MIDDLE",
                "textFormat": {"foregroundColor": {"red": .25, "green": .25, "blue": .25},
                               "fontFamily": "Montserrat", "fontSize": 9}}, "userEnteredFormat"),
        {"updateSheetProperties": {"properties": {"sheetId": sheet_id,
                                                     "gridProperties": {"frozenRowCount": 0}},
                                   "fields": "gridProperties.frozenRowCount"}},
    ]
    formats = {1: '#,##0 "₽"', 2: "#,##0", 3: "0.0%", 4: "#,##0", 5: '#,##0 "₽"',
               6: "0.0%", 7: "#,##0", 8: '#,##0 "₽"', 9: "#,##0", 10: '#,##0 "₽"', 11: "0.0%"}
    for title_row, header_row, fact_row, week_rows in sections:
        requests.extend([
            merged(sheet_id, title_row),
            repeat(sheet_id, title_row, title_row + 1, 0, 13,
                   {"backgroundColor": BLUE, "horizontalAlignment": "CENTER",
                    "textFormat": {"bold": True, "foregroundColor": WHITE,
                                   "fontFamily": "Montserrat"}}, "userEnteredFormat"),
            repeat(sheet_id, header_row, header_row + 1, 0, 13,
                   {"backgroundColor": LIGHT_BLUE, "horizontalAlignment": "CENTER", "wrapStrategy": "WRAP",
                    "textFormat": {"bold": True, "fontFamily": "Montserrat"}}, "userEnteredFormat"),
            repeat(sheet_id, fact_row, fact_row + 1, 0, 13,
                   {"backgroundColor": LIGHT_BLUE,
                    "textFormat": {"bold": True, "fontFamily": "Montserrat"}},
                   "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat"),
            repeat(sheet_id, header_row + 1, fact_row + 1, 1, 12,
                   {"horizontalAlignment": "CENTER"}, "userEnteredFormat.horizontalAlignment"),
            row_height(sheet_id, title_row, header_row + 1, 32),
            row_height(sheet_id, fact_row, fact_row + 1, 26),
            repeat(sheet_id, header_row + 1, fact_row, 12, 13,
                   {"horizontalAlignment": "LEFT", "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "WRAP", "textFormat": {"fontFamily": "Montserrat", "fontSize": 9}},
                   "userEnteredFormat"),
        ])
        for week_row_index in week_rows:
            requests.append(row_height(sheet_id, week_row_index, week_row_index + 1, 88))
        for col, pattern in formats.items():
            requests.append(repeat(sheet_id, header_row + 1, fact_row + 1, col, col + 1,
                                   {"numberFormat": {"type": "NUMBER", "pattern": pattern}},
                                   "userEnteredFormat.numberFormat"))
    requests.extend([
        merged(sheet_id, plan_header),
        repeat(sheet_id, plan_header, plan_header + 1, 0, 13,
               {"backgroundColor": BLUE, "horizontalAlignment": "CENTER",
                "textFormat": {"bold": True, "foregroundColor": WHITE, "fontFamily": "Montserrat"}},
               "userEnteredFormat"),
        repeat(sheet_id, plan_header + 1, plan_header + 2, 0, 5,
               {"backgroundColor": LIGHT_BLUE, "horizontalAlignment": "CENTER",
                "textFormat": {"bold": True, "fontFamily": "Montserrat"}}, "userEnteredFormat"),
        repeat(sheet_id, plan_header + 1, plan_start + 6, 1, 5,
               {"horizontalAlignment": "CENTER"}, "userEnteredFormat.horizontalAlignment"),
        repeat(sheet_id, plan_start, plan_start + 6, 4, 5,
               {"numberFormat": {"type": "PERCENT", "pattern": "0%"}},
               "userEnteredFormat.numberFormat"),
    ])
    plan_patterns = ['#,##0 "₽"', "#,##0", "#,##0", '#,##0 "₽"', "0.0%", '#,##0 "₽"']
    for offset, pattern in enumerate(plan_patterns):
        requests.append(repeat(sheet_id, plan_start + offset, plan_start + offset + 1, 1, 4,
                               {"numberFormat": {"type": "NUMBER", "pattern": pattern}},
                               "userEnteredFormat.numberFormat"))
    directions = config.get("plan_kpi_directions", {})
    for offset, (_, key) in enumerate(plan_items):
        deviation = rows[plan_start + offset][4]
        color = plan_color(directions.get(key, "ignore"), deviation)
        if color:
            requests.append(repeat(sheet_id, plan_start + offset, plan_start + offset + 1, 4, 5,
                                   {"backgroundColor": color}, "userEnteredFormat.backgroundColor"))
    requests.extend([
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                                                   "startIndex": 0, "endIndex": 1},
                                       "properties": {"pixelSize": 145}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                                                   "startIndex": 1, "endIndex": 12},
                                       "properties": {"pixelSize": 105}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                                                   "startIndex": 12, "endIndex": 13},
                                       "properties": {"pixelSize": 460}, "fields": "pixelSize"}},
        row_height(sheet_id, 0, 1, 38), row_height(sheet_id, 1, 2, 26),
        row_height(sheet_id, plan_header, plan_header + 2, 32),
        row_height(sheet_id, plan_start, plan_start + 6, 26),
    ])
    requests.append(repeat(sheet_id, 0, row_count, 0, 13,
                           {"verticalAlignment": "MIDDLE"},
                           "userEnteredFormat.verticalAlignment"))
    if grid["rowCount"] > row_count:
        requests.append({"deleteDimension": {"range": {"sheetId": sheet_id, "dimension": "ROWS",
                                                         "startIndex": row_count,
                                                         "endIndex": grid["rowCount"]}}})
    client.batch_update(args.spreadsheet_id, requests)
    print(f"https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit#gid={sheet_id}")


if __name__ == "__main__":
    main()
