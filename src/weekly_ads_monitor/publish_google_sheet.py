from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .google_sheets import GoogleSheetsClient


BLUE = {"red": 0.043, "green": 0.353, "blue": 0.557}
MID_BLUE = {"red": 0.090, "green": 0.412, "blue": 0.608}
LIGHT_BLUE = {"red": 0.851, "green": 0.918, "blue": 0.961}
YELLOW = {"red": 1.0, "green": 0.949, "blue": 0.800}
GREEN = {"red": 0.886, "green": 0.941, "blue": 0.851}
RED = {"red": 0.988, "green": 0.894, "blue": 0.839}
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}


def change(current, previous):
    return current / previous - 1 if current is not None and previous not in (None, 0) else None


def display_period(value: str) -> str:
    start, end = value.split("..")
    return (
        f"{datetime.strptime(start, '%Y-%m-%d'):%d.%m.%y}–"
        f"{datetime.strptime(end, '%Y-%m-%d'):%d.%m.%y}"
    )


def quality_color(metric: str, delta: float | None):
    if delta is None or abs(delta) < 0.10:
        return None
    if abs(delta) <= 0.15:
        return YELLOW
    higher_is_better = metric in {"leads", "cr", "target_leads", "target_share"}
    good = delta > 0 if higher_is_better else delta < 0
    return GREEN if good else RED


def status_for(diagnostics: dict) -> str:
    bad = {
        "leads": -1, "cr": -1, "target_leads": -1, "target_share": -1,
        "cpc": 1, "cpa": 1, "target_cpa": 1,
    }
    for metric, direction in bad.items():
        value = diagnostics["changes"].get(metric)
        if value is not None and abs(value) > 0.15 and value * direction > 0:
            return "Требует проверки"
    if diagnostics.get("quality_preliminary") or any(
        abs(value) >= 0.10 for value in diagnostics["changes"].values() if value is not None
    ):
        return "Внимание"
    return "Норма"


def cell_format(sheet_id: int, row: int, col: int, color: dict) -> dict:
    return {"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": row - 1, "endRowIndex": row,
                  "startColumnIndex": col - 1, "endColumnIndex": col},
        "cell": {"userEnteredFormat": {"backgroundColor": color}},
        "fields": "userEnteredFormat.backgroundColor",
    }}


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish weekly monitor to Google Sheets")
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--tab", default="reduktor40.ru")
    parser.add_argument("--payload", default="output/reduktor40-report.json")
    parser.add_argument("--credentials", default=".secrets/google-service-account.json")
    args = parser.parse_args()

    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    client = GoogleSheetsClient(Path(args.credentials))
    metadata = client.metadata(args.spreadsheet_id)
    sheets = {item["properties"]["title"]: item["properties"] for item in metadata["sheets"]}
    requests = []
    if args.tab not in sheets:
        if "Лист1" in sheets:
            requests.append({"updateSheetProperties": {
                "properties": {"sheetId": sheets["Лист1"]["sheetId"], "title": args.tab},
                "fields": "title",
            }})
        else:
            requests.append({"addSheet": {"properties": {"title": args.tab}}})
    for technical in ("_history", "_runs"):
        if technical not in sheets:
            requests.append({"addSheet": {"properties": {"title": technical, "hidden": True}}})
    if requests:
        client.batch_update(args.spreadsheet_id, requests)
        metadata = client.metadata(args.spreadsheet_id)
        sheets = {item["properties"]["title"]: item["properties"] for item in metadata["sheets"]}

    sheet_id = sheets[args.tab]["sheetId"]
    current = payload["latest_week"]["rows"]["account"]
    previous = payload["previous_week"]["rows"]["account"]
    diagnostics = payload["diagnostics"]
    rows = [[None] * 7 for _ in range(41)]
    rows[0][0] = f"{payload['project']} — еженедельный мониторинг"
    rows[1][:4] = ["Период", display_period(payload["latest_week"]["period"]), "Статус", status_for(diagnostics)]
    rows[2][:4] = ["Сравнение", display_period(payload["previous_week"]["period"]), "Обновлено", datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M")]
    rows[4][:4] = ["Показатель", "Текущая неделя", "Предыдущая неделя", "Изменение"]
    metrics = [
        ("Расход", "spend"), ("Показы", "impressions"), ("Клики", "clicks"), ("CTR", "ctr"),
        ("CPC", "cpc"), ("Заявки Roistat", "leads"), ("CPA", "cpa"), ("CR", "cr"),
        ("Целевые заявки", "target_leads"), ("CPA целевой заявки", "target_cpa"),
        ("% целевых", "target_share"),
    ]
    for index, (label, key) in enumerate(metrics, start=5):
        rows[index][:4] = [label, current.get(key), previous.get(key), diagnostics["changes"].get(key)]
    rows[17][0] = "Комментарий"
    rows[18][0] = diagnostics["human_comment"]

    rows[23][0] = "Поиск / РСЯ"
    rows[24][:7] = ["Показатель", "Поиск: текущая", "Поиск: предыдущая", "Изменение",
                     "РСЯ: текущая", "РСЯ: предыдущая", "Изменение"]
    network_metrics = [("Расход", "spend"), ("Клики", "clicks"), ("CPC", "cpc"),
                       ("CR", "cr"), ("Заявки", "leads"), ("CPA", "cpa")]
    search_now = payload["latest_week"]["rows"].get("network:search", {})
    search_old = payload["previous_week"]["rows"].get("network:search", {})
    context_now = payload["latest_week"]["rows"].get("network:context", {})
    context_old = payload["previous_week"]["rows"].get("network:context", {})
    for index, (label, key) in enumerate(network_metrics, start=25):
        rows[index][:7] = [label, search_now.get(key), search_old.get(key), change(search_now.get(key), search_old.get(key)),
                           context_now.get(key), context_old.get(key), change(context_now.get(key), context_old.get(key))]

    rows[32][0] = "План/факт текущего месяца"
    rows[33][:5] = ["Показатель", "План месяца", "План на дату", "Факт", "Отклонение"]
    plan_metrics = [("Расход", "spend"), ("Клики", "clicks"), ("Заявки", "leads"),
                    ("CPC", "cpc"), ("CR", "cr"), ("CPA", "cpa")]
    mtd = payload["month_to_date"]["rows"]["account"]
    for index, (label, key) in enumerate(plan_metrics, start=34):
        fact = mtd.get(key)
        plan_date = payload["plan_to_date"].get(key)
        rows[index][:5] = [label, payload["month_plan"].get(key), plan_date, fact, change(fact, plan_date)]
    rows[40][0] = "Качество заявок оценивается по текущим статусам Roistat; при высокой доле необработанных лидов вывод предварительный."

    client.request("POST", f"https://sheets.googleapis.com/v4/spreadsheets/{args.spreadsheet_id}/values/"
                   f"{urllib_quote(args.tab + '!A1:G60')}:clear", {})
    client.values_batch_update(args.spreadsheet_id, [{"range": f"'{args.tab}'!A1:G41", "values": rows}])

    fmt = [
        {"unmergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 41,
                                      "startColumnIndex": 0, "endColumnIndex": 7}}},
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                                    "startColumnIndex": 0, "endColumnIndex": 7}, "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 17, "endRowIndex": 18,
                                    "startColumnIndex": 0, "endColumnIndex": 7}, "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 18, "endRowIndex": 22,
                                    "startColumnIndex": 0, "endColumnIndex": 7}, "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 23, "endRowIndex": 24,
                                    "startColumnIndex": 0, "endColumnIndex": 7}, "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 32, "endRowIndex": 33,
                                    "startColumnIndex": 0, "endColumnIndex": 7}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 41,
                                    "startColumnIndex": 0, "endColumnIndex": 7},
                         "cell": {"userEnteredFormat": {"textFormat": {"fontFamily": "Montserrat", "fontSize": 10},
                                                          "verticalAlignment": "MIDDLE"}},
                         "fields": "userEnteredFormat.textFormat,userEnteredFormat.verticalAlignment"}},
    ]
    for row in (1, 18, 24, 33):
        fmt.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": row - 1, "endRowIndex": row,
                                               "startColumnIndex": 0, "endColumnIndex": 7},
                                   "cell": {"userEnteredFormat": {"backgroundColor": BLUE,
                                                                    "textFormat": {"foregroundColor": WHITE, "bold": True},
                                                                    "horizontalAlignment": "CENTER"}},
                                   "fields": "userEnteredFormat"}})
    for row in (5, 25, 34):
        fmt.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": row - 1, "endRowIndex": row,
                                               "startColumnIndex": 0, "endColumnIndex": 7},
                                   "cell": {"userEnteredFormat": {"backgroundColor": LIGHT_BLUE,
                                                                    "textFormat": {"bold": True},
                                                                    "horizontalAlignment": "CENTER"}},
                                   "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.bold,userEnteredFormat.horizontalAlignment"}})
    fmt.extend([
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 18, "endRowIndex": 22,
                                    "startColumnIndex": 0, "endColumnIndex": 7},
                         "cell": {"userEnteredFormat": {"backgroundColor": YELLOW, "wrapStrategy": "WRAP",
                                                          "verticalAlignment": "TOP"}},
                         "fields": "userEnteredFormat"}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                                                   "startIndex": 0, "endIndex": 1},
                                       "properties": {"pixelSize": 210}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                                                   "startIndex": 1, "endIndex": 7},
                                       "properties": {"pixelSize": 145}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "ROWS",
                                                   "startIndex": 18, "endIndex": 22},
                                       "properties": {"pixelSize": 32}, "fields": "pixelSize"}},
        {"updateSheetProperties": {"properties": {"sheetId": sheet_id,
                                                     "gridProperties": {"frozenRowCount": 0}},
                                   "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 41,
                                    "startColumnIndex": 1, "endColumnIndex": 7},
                         "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                         "fields": "userEnteredFormat.horizontalAlignment"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 41,
                                    "startColumnIndex": 0, "endColumnIndex": 1},
                         "cell": {"userEnteredFormat": {"horizontalAlignment": "LEFT"}},
                         "fields": "userEnteredFormat.horizontalAlignment"}},
    ])
    number_formats = {
        6: "#,##0 \"₽\"", 7: "#,##0", 8: "#,##0", 9: "0.0%", 10: "#,##0 \"₽\"",
        11: "#,##0", 12: "#,##0 \"₽\"", 13: "0.0%", 14: "#,##0", 15: "#,##0 \"₽\"", 16: "0.0%",
    }
    for row, pattern in number_formats.items():
        fmt.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": row - 1, "endRowIndex": row,
                                               "startColumnIndex": 1, "endColumnIndex": 3},
                                   "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": pattern}}},
                                   "fields": "userEnteredFormat.numberFormat"}})
    fmt.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 5, "endRowIndex": 16,
                                           "startColumnIndex": 3, "endColumnIndex": 4},
                               "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0%"}}},
                               "fields": "userEnteredFormat.numberFormat"}})

    traffic_formats = ["#,##0 \"₽\"", "#,##0", "#,##0 \"₽\"", "0.0%", "#,##0", "#,##0 \"₽\""]
    for row, pattern in enumerate(traffic_formats, start=26):
        for start_col, end_col in ((1, 3), (4, 6)):
            fmt.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": row - 1, "endRowIndex": row,
                                                   "startColumnIndex": start_col, "endColumnIndex": end_col},
                                       "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": pattern}}},
                                       "fields": "userEnteredFormat.numberFormat"}})
    for col in (3, 6):
        fmt.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 25, "endRowIndex": 31,
                                               "startColumnIndex": col, "endColumnIndex": col + 1},
                                   "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0%"}}},
                                   "fields": "userEnteredFormat.numberFormat"}})

    plan_formats = ["#,##0 \"₽\"", "#,##0", "#,##0.0", "#,##0 \"₽\"", "0.0%", "#,##0 \"₽\""]
    for row, pattern in enumerate(plan_formats, start=35):
        fmt.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": row - 1, "endRowIndex": row,
                                               "startColumnIndex": 1, "endColumnIndex": 4},
                                   "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": pattern}}},
                                   "fields": "userEnteredFormat.numberFormat"}})
    fmt.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 34, "endRowIndex": 40,
                                           "startColumnIndex": 4, "endColumnIndex": 5},
                               "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0%"}}},
                               "fields": "userEnteredFormat.numberFormat"}})
    for offset, (_, key) in enumerate(metrics, start=6):
        color = quality_color(key, diagnostics["changes"].get(key)) if key in {
            "cpc", "leads", "cpa", "cr", "target_leads", "target_cpa", "target_share"
        } else None
        if color:
            fmt.append(cell_format(sheet_id, offset, 4, color))
    plan_keys = ["spend", "clicks", "leads", "cpc", "cr", "cpa"]
    for row, key in enumerate(plan_keys, start=35):
        delta = rows[row - 1][4]
        color = None
        if key in {"leads", "cr", "cpc", "cpa"} and delta is not None:
            if abs(delta) >= 0.10:
                if abs(delta) <= 0.20:
                    color = YELLOW
                else:
                    good = delta > 0 if key in {"leads", "cr"} else delta < 0
                    color = GREEN if good else RED
        elif key == "spend" and delta is not None:
            lead_delta = rows[36][4]
            if (delta < -0.20 and lead_delta < -0.10) or (delta > 0.20 and lead_delta < 0.10):
                color = RED
        if color:
            fmt.append(cell_format(sheet_id, row, 5, color))
    for row in (5, 18, 24, 25, 33, 34):
        fmt.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": row - 1, "endRowIndex": row,
                                               "startColumnIndex": 0, "endColumnIndex": 7},
                                   "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                                   "fields": "userEnteredFormat.horizontalAlignment"}})
    fmt.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 41,
                                           "startColumnIndex": 0, "endColumnIndex": 7},
                               "cell": {"userEnteredFormat": {"textFormat": {"fontFamily": "Montserrat"}}},
                               "fields": "userEnteredFormat.textFormat.fontFamily"}})
    grid = sheets[args.tab].get("gridProperties", {})
    if grid.get("rowCount", 41) > 41:
        fmt.append({"deleteDimension": {"range": {"sheetId": sheet_id, "dimension": "ROWS",
                                                    "startIndex": 41, "endIndex": grid["rowCount"]}}})
    if grid.get("columnCount", 7) > 7:
        fmt.append({"deleteDimension": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                                                    "startIndex": 7, "endIndex": grid["columnCount"]}}})
    client.batch_update(args.spreadsheet_id, fmt)

    history_header = [["project_id", "period_start", "period_end", "level", "entity_id", "metric", "value", "loaded_at"]]
    if not client.values_get(args.spreadsheet_id, "_history!A1:H1"):
        client.values_batch_update(args.spreadsheet_id, [{"range": "_history!A1:H1", "values": history_header}])
    existing = client.values_get(args.spreadsheet_id, "_history!A2:H")
    existing_keys = {tuple(row[:6]) for row in existing if len(row) >= 6}
    start, end = payload["latest_week"]["period"].split("..")
    loaded_at = datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds")
    history_rows = []
    for entity_id, values in payload["latest_week"]["rows"].items():
        level = "account" if entity_id == "account" else entity_id.split(":", 1)[0]
        for metric in ("spend", "impressions", "clicks", "leads", "target_leads", "cpc", "cr", "cpa", "target_cpa", "target_share"):
            key = (payload["project"], start, end, level, entity_id, metric)
            if key not in existing_keys and values.get(metric) is not None:
                history_rows.append([*key, values[metric], loaded_at])
    if history_rows:
        client.values_append(args.spreadsheet_id, "_history!A:H", history_rows)
    if not client.values_get(args.spreadsheet_id, "_runs!A1:E1"):
        client.values_batch_update(args.spreadsheet_id, [{"range": "_runs!A1:E1", "values": [[
            "project_id", "started_at", "status", "period", "message"
        ]]}])
    client.values_append(args.spreadsheet_id, "_runs!A:E", [[
        payload["project"], loaded_at, "success", payload["latest_week"]["period"], "Обновление выполнено"
    ]])
    print(f"https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit")


def urllib_quote(value: str) -> str:
    import urllib.parse
    return urllib.parse.quote(value, safe="")


if __name__ == "__main__":
    main()
