from __future__ import annotations

import argparse
import calendar
import csv
import io
import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .env import load_env
from .google_sheets import GoogleSheetsClient
from .http import request_json
from .models import Period
from .plans import MONTHS_RU, _number
from .publish_google_sheet import BLUE, GREEN, LIGHT_BLUE, RED, WHITE, YELLOW, display_period
from .publish_accumulated_sheet import plan_color, repeat, row_height, value_cell
from .yandex_direct import YandexDirectClient


MONTHS = {1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
          7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"}
MONTHS_GENITIVE = {1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
                   7: "июля", 8: "августа", 9: "сентября", 10: "октября",
                   11: "ноября", 12: "декабря"}
HEADERS = ["Период", "Расход", "Показы", "CTR", "Клики", "CPC", "Обращения", "CR", "CPA"]


def _empty() -> dict:
    return {"spend": 0.0, "impressions": 0, "clicks": 0, "leads": 0}


def _derived(raw: dict) -> dict:
    return {
        **raw,
        "ctr": raw["clicks"] / raw["impressions"] if raw["impressions"] else None,
        "cpc": raw["spend"] / raw["clicks"] if raw["clicks"] else None,
        "cr": raw["leads"] / raw["clicks"] if raw["leads"] is not None and raw["clicks"] else None,
        "cpa": raw["spend"] / raw["leads"] if raw["leads"] else None,
    }


def _sum(items: list[dict]) -> dict:
    result = _empty()
    for item in items:
        for key in result:
            result[key] += item.get(key, 0)
    result["impressions"] = int(result["impressions"])
    result["clicks"] = int(result["clicks"])
    result["leads"] = int(result["leads"])
    return _derived(result)


def _change(current, previous):
    return current / previous - 1 if current is not None and previous not in (None, 0) else None


def _fmt_pct(value: float | None) -> str:
    return "н/д" if value is None else f"{abs(value):.1%}".replace(".", ",")


def _comment(current: dict, previous: dict, conversion_note: str) -> str:
    cpa = _change(current["cpa"], previous["cpa"])
    leads = _change(current["leads"], previous["leads"])
    cr = _change(current["cr"], previous["cr"])
    cpc = _change(current["cpc"], previous["cpc"])
    if cpa is None:
        first = "Динамику CPA пока нельзя корректно оценить."
    elif abs(cpa) < .10:
        first = f"CPA изменился на {_fmt_pct(cpa)} и остался в пределах нормальной динамики"
        if leads is not None and abs(leads) >= .10:
            first += f", количество обращений {'выросло' if leads > 0 else 'сократилось'} на {_fmt_pct(leads)}"
        first += "."
    else:
        first = f"CPA {'вырос' if cpa > 0 else 'снизился'} на {_fmt_pct(cpa)}"
        if leads is not None:
            first += f", количество обращений {'увеличилось' if leads > 0 else 'сократилось'} на {_fmt_pct(leads)}"
        first += "."
    factors = [("CR", cr, -1), ("CPC", cpc, 1)]
    useful = [(name, value, effect) for name, value, effect in factors if value is not None and abs(value) >= .10]
    sentences = [first]
    if cpa is not None and abs(cpa) >= .10 and useful:
        supporting = [x for x in useful if x[1] * x[2] * cpa > 0]
        name, value, _ = max(supporting or useful, key=lambda x: abs(x[1]))
        sentences.append(
            f"Основной причиной стало {'снижение' if value < 0 else 'увеличение'} {name} на {_fmt_pct(value)}."
        )
    if conversion_note:
        sentences.append(conversion_note)
    return " ".join(sentences)


def _fetch_metrika(token: str, config: dict, start: date, end: date) -> dict[date, int]:
    metrika = config["yandex_metrika"]
    metrics = ",".join(f"ym:s:goal{goal_id}visits" for goal_id in metrika["goal_ids"])
    params = urllib.parse.urlencode({
        "ids": str(metrika["counter_id"]), "date1": start.isoformat(), "date2": end.isoformat(),
        "metrics": metrics,
        "dimensions": (
            "ym:s:date,ym:s:cross_device_last_significantTrafficSource,"
            "ym:s:cross_device_last_significantSourceEngine"
        ),
        "accuracy": "full", "attribution": metrika["attribution"], "lang": "ru", "limit": 100000,
    })
    request = urllib.request.Request(
        f"https://api-metrika.yandex.net/stat/v1/data?{params}",
        headers={"Authorization": f"OAuth {token}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get("sampled"):
        raise RuntimeError("Metrika returned sampled data")
    result: dict[date, int] = defaultdict(int)
    for row in payload.get("data", []):
        dimensions = row["dimensions"]
        if dimensions[1].get("name") != metrika["traffic_source"]:
            continue
        if dimensions[2].get("name") not in metrika["source_engines"]:
            continue
        result[date.fromisoformat(dimensions[0]["name"])] += round(sum(row["metrics"]))
    return dict(result)


def _fetch_unique_calls(api_key: str, project_id: int, source_marker: str, period: Period) -> int:
    response = request_json(
        f"https://cloud.roistat.com/api/v1/project/analytics/data?project={project_id}",
        headers={"Api-key": api_key, "Content-Type": "application/json"},
        body={
            "period": {
                "from": f"{period.start.isoformat()}T00:00:00+0300",
                "to": f"{period.end.isoformat()}T23:59:59+0300",
            },
            "metrics": ["uniqueCalls"], "dimensions": [],
            "filters": [{"field": "marker_level_1", "operation": "=", "value": source_marker}],
        },
    )
    if response.get("status") != "success":
        raise RuntimeError(f"Roistat error for {period.label}: {response}")
    items = response.get("data", [{}])[0].get("items", [])
    return round(items[0]["metrics"][0]["value"]) if items else 0


def _fetch_plan(url: str, month: date) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:
        rows = list(csv.reader(io.StringIO(response.read().decode("utf-8-sig"))))
    column = rows[0].index(f"{MONTHS_RU[month.month]} {month.year}")
    def find(*needles: str) -> float:
        candidates = [row for row in rows if row and all(x in row[0] for x in needles)]
        if len(candidates) > 1 and "KPI: Конверсия" in needles:
            candidates = [row for row in candidates if "с учётом услуги" not in row[0]]
        if len(candidates) != 1:
            raise ValueError(f"Plan row is ambiguous or missing: {needles}")
        return _number(candidates[0][column])
    spend = find("Яндекс.Директ", "Бюджет", "ПЛАН")
    clicks = find("Яндекс.Директ", "Сеансов. ПЛАН")
    leads = find("Яндекс.Директ", "Цель: Продажи", "ПЛАН", "KPI: Конверсия")
    cpc = find("Яндекс.Директ", "Цена за переход. ПЛАН")
    cpa = find("Яндекс.Директ", "Цель: Продажи", "ПЛАН", "Цена конверсии")
    return {"spend": spend, "clicks": clicks, "leads": leads, "cpc": cpc,
            "cr": leads / clicks if clicks else None, "cpa": cpa}


def _period_raw(daily: dict[date, dict], period: Period) -> dict:
    return _sum([value for day, value in daily.items() if period.start <= day <= period.end])


def _write_sheet(client: GoogleSheetsClient, spreadsheet_id: str, tab: str, config: dict,
                 periods: list[tuple[Period, dict]], latest: dict, previous: dict,
                 month_facts: dict[int, dict], plan: dict, fact: dict, as_of: date) -> int:
    metadata = client.metadata(spreadsheet_id)
    existing = next((x["properties"] for x in metadata["sheets"] if x["properties"]["title"] == tab), None)
    if existing is None:
        reply = client.batch_update(spreadsheet_id, [{"addSheet": {"properties": {
            "title": tab, "gridProperties": {"rowCount": 60, "columnCount": 9}}}}])
        sheet_id = reply["replies"][0]["addSheet"]["properties"]["sheetId"]
        grid_rows = 60
    else:
        sheet_id = existing["sheetId"]
        grid_rows = existing["gridProperties"]["rowCount"]

    updated_at = datetime.now(ZoneInfo(config["timezone"]))
    rows = [[f"{config['project']} — еженедельный мониторинг"],
            [f"Последнее обновление: {updated_at:%d.%m.%Y, %H:%M}"], []]
    sections = []
    grouped: dict[int, list[tuple[Period, dict]]] = defaultdict(list)
    for period, values in periods:
        grouped[period.start.month].append((period, values))
    for month in sorted(grouped):
        title = len(rows)
        rows.extend([[f"{MONTHS[month]} 2026"], HEADERS])
        for period, values in grouped[month]:
            rows.append([display_period(period.label), values["spend"], values["impressions"], values["ctr"],
                         values["clicks"], values["cpc"], values["leads"], values["cr"], values["cpa"]])
        monthly = month_facts[month]
        fact_row = len(rows)
        rows.extend([["Факт", monthly["spend"], monthly["impressions"], monthly["ctr"], monthly["clicks"],
                      monthly["cpc"], monthly["leads"], monthly["cr"], monthly["cpa"]], []])
        sections.append((title, title + 1, fact_row))

    comment_header = len(rows)
    latest_period = Period(as_of - timedelta(days=6), as_of)
    rows.extend([[f"Комментарий за {display_period(latest_period.label)}"],
                 [_comment(latest, previous, config.get("conversion_note", ""))], [], []])
    plan_header = len(rows)
    rows.extend([[f"План/факт {MONTHS_GENITIVE[as_of.month]} на {as_of:%d.%m.%Y}"],
                 ["Показатель", "План месяца", "План на дату", "Факт", "Отклонение"]])
    progress = as_of.day / calendar.monthrange(as_of.year, as_of.month)[1]
    plan_date = {"spend": plan["spend"] * progress, "clicks": plan["clicks"] * progress,
                 "leads": plan["leads"] * progress, "cpc": plan["cpc"], "cr": plan["cr"], "cpa": plan["cpa"]}
    plan_items = [("Расход", "spend"), ("Клики", "clicks"), ("Обращения", "leads"),
                  ("CPC", "cpc"), ("CR", "cr"), ("CPA", "cpa")]
    plan_start = len(rows)
    for label, key in plan_items:
        deviation = _change(fact[key], plan_date[key])
        rows.append([label, plan[key], plan_date[key], fact[key], deviation])
    rows.append([])
    row_count = len(rows)
    if grid_rows < row_count:
        client.batch_update(spreadsheet_id, [{"appendDimension": {
            "sheetId": sheet_id, "dimension": "ROWS", "length": row_count - grid_rows}}])
        grid_rows = row_count
    padded = rows + [[] for _ in range(grid_rows - row_count)]
    update_rows = [{"values": [value_cell(v) for v in row + [None] * (9 - len(row))]} for row in padded]
    def merge(row: int, height: int = 1):
        return {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": row,
            "endRowIndex": row + height, "startColumnIndex": 0, "endColumnIndex": 9}, "mergeType": "MERGE_ALL"}}
    requests = [
        {"unmergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": grid_rows,
                                      "startColumnIndex": 0, "endColumnIndex": 9}}},
        {"updateCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": grid_rows,
                                     "startColumnIndex": 0, "endColumnIndex": 9}, "rows": update_rows,
                         "fields": "userEnteredValue"}},
        repeat(sheet_id, 0, grid_rows, 0, 9, {}, "userEnteredFormat"),
        merge(0), merge(1),
        repeat(sheet_id, 0, row_count, 0, 9, {"textFormat": {"fontFamily": "Montserrat", "fontSize": 10},
               "verticalAlignment": "MIDDLE"}, "userEnteredFormat.textFormat,userEnteredFormat.verticalAlignment"),
        repeat(sheet_id, 0, 1, 0, 9, {"backgroundColor": BLUE, "horizontalAlignment": "CENTER",
               "textFormat": {"bold": True, "foregroundColor": WHITE, "fontFamily": "Montserrat", "fontSize": 14}},
               "userEnteredFormat"),
        repeat(sheet_id, 1, 2, 0, 9, {"horizontalAlignment": "LEFT", "textFormat": {
            "foregroundColor": {"red": .25, "green": .25, "blue": .25}, "fontFamily": "Montserrat", "fontSize": 9}},
            "userEnteredFormat"),
        {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 0}},
                                    "fields": "gridProperties.frozenRowCount"}},
    ]
    formats = {1: '#,##0 "₽"', 2: "#,##0", 3: "0.0%", 4: "#,##0", 5: '#,##0 "₽"',
               6: "#,##0", 7: "0.0%", 8: '#,##0 "₽"'}
    for title, header, fact_row in sections:
        requests.extend([merge(title), repeat(sheet_id, title, title + 1, 0, 9,
            {"backgroundColor": BLUE, "horizontalAlignment": "CENTER", "textFormat": {"bold": True,
             "foregroundColor": WHITE, "fontFamily": "Montserrat"}}, "userEnteredFormat"),
            repeat(sheet_id, header, header + 1, 0, 9, {"backgroundColor": LIGHT_BLUE,
            "horizontalAlignment": "CENTER", "wrapStrategy": "WRAP", "textFormat": {"bold": True,
            "fontFamily": "Montserrat"}}, "userEnteredFormat"),
            repeat(sheet_id, fact_row, fact_row + 1, 0, 9, {"backgroundColor": LIGHT_BLUE,
            "textFormat": {"bold": True, "fontFamily": "Montserrat"}},
            "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat"),
            repeat(sheet_id, header + 1, fact_row + 1, 1, 9, {"horizontalAlignment": "CENTER"},
                   "userEnteredFormat.horizontalAlignment"), row_height(sheet_id, title, header + 1, 32),
            row_height(sheet_id, header + 1, fact_row + 1, 26)])
        for col, pattern in formats.items():
            requests.append(repeat(sheet_id, header + 1, fact_row + 1, col, col + 1,
                {"numberFormat": {"type": "NUMBER", "pattern": pattern}}, "userEnteredFormat.numberFormat"))
    requests.extend([merge(comment_header), merge(comment_header + 1, 3),
        repeat(sheet_id, comment_header, comment_header + 1, 0, 9, {"backgroundColor": BLUE,
        "horizontalAlignment": "CENTER", "textFormat": {"bold": True, "foregroundColor": WHITE,
        "fontFamily": "Montserrat"}}, "userEnteredFormat"),
        repeat(sheet_id, comment_header + 1, comment_header + 4, 0, 9, {"backgroundColor": YELLOW,
        "wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE", "textFormat": {"fontFamily": "Montserrat"}},
        "userEnteredFormat"), merge(plan_header),
        repeat(sheet_id, plan_header, plan_header + 1, 0, 9, {"backgroundColor": BLUE,
        "horizontalAlignment": "CENTER", "textFormat": {"bold": True, "foregroundColor": WHITE,
        "fontFamily": "Montserrat"}}, "userEnteredFormat"),
        repeat(sheet_id, plan_header + 1, plan_header + 2, 0, 5, {"backgroundColor": LIGHT_BLUE,
        "horizontalAlignment": "CENTER", "textFormat": {"bold": True, "fontFamily": "Montserrat"}},
        "userEnteredFormat"), repeat(sheet_id, plan_header + 1, plan_start + 6, 1, 5, {"horizontalAlignment": "CENTER"},
        "userEnteredFormat.horizontalAlignment"), repeat(sheet_id, plan_start, plan_start + 6, 4, 5,
        {"numberFormat": {"type": "PERCENT", "pattern": "0%"}}, "userEnteredFormat.numberFormat")])
    plan_patterns = ['#,##0 "₽"', "#,##0", "#,##0", '#,##0 "₽"', "0.0%", '#,##0 "₽"']
    for offset, pattern in enumerate(plan_patterns):
        requests.append(repeat(sheet_id, plan_start + offset, plan_start + offset + 1, 1, 4,
            {"numberFormat": {"type": "NUMBER", "pattern": pattern}}, "userEnteredFormat.numberFormat"))
    for offset, (_, key) in enumerate(plan_items):
        deviation = rows[plan_start + offset][4]
        color = plan_color(config["plan_kpi_directions"][key], deviation)
        if color:
            requests.append(repeat(sheet_id, plan_start + offset, plan_start + offset + 1, 4, 5,
                {"backgroundColor": color}, "userEnteredFormat.backgroundColor"))
    requests.extend([{"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
        "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 145}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
        "startIndex": 1, "endIndex": 9}, "properties": {"pixelSize": 105}, "fields": "pixelSize"}},
        row_height(sheet_id, 0, 1, 38), row_height(sheet_id, 1, 2, 26),
        row_height(sheet_id, comment_header, comment_header + 1, 32),
        row_height(sheet_id, comment_header + 1, comment_header + 4, 30),
        row_height(sheet_id, plan_header, plan_header + 2, 32), row_height(sheet_id, plan_start, plan_start + 6, 26),
        repeat(sheet_id, 0, row_count, 0, 9, {"verticalAlignment": "MIDDLE"},
               "userEnteredFormat.verticalAlignment")])
    if grid_rows > row_count:
        requests.append({"deleteDimension": {"range": {"sheetId": sheet_id, "dimension": "ROWS",
            "startIndex": row_count, "endIndex": grid_rows}}})
    client.batch_update(spreadsheet_id, requests)
    return sheet_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/asko-hall.json")
    parser.add_argument("--credentials", default=".secrets/google-service-account.json")
    parser.add_argument("--as-of", type=date.fromisoformat,
                        default=date.today() - timedelta(days=date.today().weekday() + 1))
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    secrets = load_env(Path(".env.local"))
    history_start, history_end = date(2026, 1, 1), args.as_of
    segments = []
    cursor = history_start
    while cursor <= history_end:
        sunday = cursor + timedelta(days=6 - cursor.weekday())
        month_end = cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1])
        end = min(sunday, month_end, history_end)
        segments.append(Period(cursor, end))
        cursor = end + timedelta(days=1)
    yd = config["yandex_direct"]
    direct_rows = YandexDirectClient(secrets["YANDEX_DIRECT_OAUTH_TOKEN"], yd["client_login"],
        yd["campaign_ids"], yd["include_vat"]).fetch(Period(history_start, history_end))
    daily: dict[date, dict] = defaultdict(_empty)
    for row in direct_rows:
        day = date.fromisoformat(row["Date"])
        daily[day]["spend"] += float(row["Cost"])
        daily[day]["impressions"] += int(row["Impressions"])
        daily[day]["clicks"] += int(row["Clicks"])
    metrika = {}
    for month in range(1, history_end.month + 1):
        month_start = date(history_end.year, month, 1)
        month_finish = min(
            date(history_end.year, month, calendar.monthrange(history_end.year, month)[1]), history_end
        )
        metrika.update(_fetch_metrika(
            secrets["YANDEX_METRIKA_OAUTH_TOKEN"], config, month_start, month_finish
        ))
    for day, count in metrika.items():
        daily[day]["leads"] += count
    ro = config["roistat"]
    values = []
    for period in segments:
        raw = _period_raw(daily, period)
        try:
            raw["leads"] += _fetch_unique_calls(
                secrets["ROISTAT_API_KEY"], ro["project_id"], ro["source_marker"], period
            )
        except RuntimeError as exc:
            if "option_not_paid" not in str(exc):
                raise
            raw["leads"] = None
        raw = _derived({key: raw[key] for key in _empty()})
        values.append((period, raw))
    latest_period = Period(history_end - timedelta(days=6), history_end)
    previous_period = Period(history_end - timedelta(days=13), history_end - timedelta(days=7))
    previous = _period_raw(daily, previous_period)
    previous["leads"] += _fetch_unique_calls(
        secrets["ROISTAT_API_KEY"], ro["project_id"], ro["source_marker"], previous_period
    )
    previous = _derived({key: previous[key] for key in _empty()})
    latest = _period_raw(daily, latest_period)
    latest["leads"] = sum(metrika.get(day, 0) for day in daily
                          if latest_period.start <= day <= latest_period.end)
    latest["leads"] += _fetch_unique_calls(
        secrets["ROISTAT_API_KEY"], ro["project_id"], ro["source_marker"], latest_period
    )
    latest = _derived({key: latest[key] for key in _empty()})
    plan = _fetch_plan(config["plan"]["csv_url"], history_end.replace(day=1))
    month_facts = {}
    for month in range(1, history_end.month + 1):
        month_end = calendar.monthrange(history_end.year, month)[1]
        period = Period(date(history_end.year, month, 1),
                        min(date(history_end.year, month, month_end), history_end))
        month_fact = _period_raw(daily, period)
        try:
            month_fact["leads"] += _fetch_unique_calls(
                secrets["ROISTAT_API_KEY"], ro["project_id"], ro["source_marker"], period
            )
        except RuntimeError as exc:
            if "option_not_paid" not in str(exc):
                raise
            month_fact["leads"] = None
        month_facts[month] = _derived({key: month_fact[key] for key in _empty()})
    fact = month_facts[history_end.month]
    client = GoogleSheetsClient(Path(args.credentials))
    sheet_id = _write_sheet(client, config["google_sheets"]["spreadsheet_id"],
        config["google_sheets"]["tab_name"], config, values, latest, previous, month_facts,
        plan, fact, history_end)
    print(f"https://docs.google.com/spreadsheets/d/{config['google_sheets']['spreadsheet_id']}/edit#gid={sheet_id}")


if __name__ == "__main__":
    main()
