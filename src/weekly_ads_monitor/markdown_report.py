from __future__ import annotations

from pathlib import Path


def _num(value, digits=0):
    if value is None:
        return "—"
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def _pct(value):
    return "—" if value is None else f"{value:.1%}".replace(".", ",")


def _money(value):
    return "—" if value is None else f"{_num(value, 0)} ₽"


def write_markdown(payload: dict, path: Path) -> None:
    current = payload["latest_week"]["rows"]["account"]
    previous = payload["previous_week"]["rows"]["account"]
    diagnostics = payload["diagnostics"]
    lines = [
        f"# {payload['project']}: еженедельный мониторинг",
        "",
        f"Период: **{payload['latest_week']['period']}**, сравнение с **{payload['previous_week']['period']}**.",
        "",
        "| Показатель | Текущая неделя | Предыдущая неделя | Изменение |",
        "|---|---:|---:|---:|",
    ]
    specs = [
        ("Расход", "spend", _money), ("Показы", "impressions", _num),
        ("Клики", "clicks", _num), ("CTR", "ctr", _pct), ("CPC", "cpc", _money),
        ("Заявки", "leads", _num), ("CPA", "cpa", _money), ("CR", "cr", _pct),
        ("Целевые заявки", "target_leads", _num), ("CPA целевой", "target_cpa", _money),
        ("% целевых", "target_share", _pct),
    ]
    for label, key, formatter in specs:
        lines.append(
            f"| {label} | {formatter(current[key])} | {formatter(previous[key])} | {_pct(diagnostics['changes'][key])} |"
        )
    lines.extend(["", "## Комментарий", "", diagnostics["human_comment"]])
    plan = payload["month_plan"]
    plan_date = payload["plan_to_date"]
    mtd = payload["month_to_date"]["rows"]["account"]
    lines.extend([
        "", "## План/факт месяца на дату", "",
        "| Показатель | План месяца | План на дату | Факт |",
        "|---|---:|---:|---:|",
        f"| Расход | {_money(plan['spend'])} | {_money(plan_date['spend'])} | {_money(mtd['spend'])} |",
        f"| Клики | {_num(plan['clicks'])} | {_num(plan_date['clicks'], 1)} | {_num(mtd['clicks'])} |",
        f"| Заявки | {_num(plan['leads'])} | {_num(plan_date['leads'], 1)} | {_num(mtd['leads'])} |",
        f"| CPC | {_money(plan['cpc'])} | {_money(plan_date['cpc'])} | {_money(mtd['cpc'])} |",
        f"| CR | {_pct(plan['cr'])} | {_pct(plan_date['cr'])} | {_pct(mtd['cr'])} |",
        f"| CPA | {_money(plan['cpa'])} | {_money(plan_date['cpa'])} | {_money(mtd['cpa'])} |",
        "",
        "Планы качества заявок отсутствуют; целевые показатели показаны только по факту.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
