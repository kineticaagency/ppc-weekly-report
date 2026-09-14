from __future__ import annotations

from dataclasses import asdict

from .models import Metrics, Period


def merge_metrics(direct: dict[str, Metrics], roistat: dict[str, Metrics]) -> dict[str, Metrics]:
    keys = set(direct) | set(roistat)
    result = {}
    for key in keys:
        d = direct.get(key, Metrics())
        r = roistat.get(key, Metrics())
        result[key] = Metrics(
            spend=d.spend, impressions=d.impressions, clicks=d.clicks,
            leads=r.leads, target_leads=r.target_leads,
            non_target_leads=r.non_target_leads,
            unprocessed_leads=r.unprocessed_leads,
            unclassified_leads=r.unclassified_leads,
        )
    return result


def serialize_period(period: Period, metrics: dict[str, Metrics], preliminary_threshold: float) -> dict:
    rows = {}
    for key, value in sorted(metrics.items()):
        derived = value.derived()
        rows[key] = {
            **asdict(value),
            **derived,
            "quality_preliminary": (derived["unprocessed_share"] or 0) >= preliminary_threshold,
        }
    return {"period": period.label, "rows": rows}


def compare(current: Metrics, previous: Metrics) -> dict[str, float | None]:
    current_values = {**asdict(current), **current.derived()}
    previous_values = {**asdict(previous), **previous.derived()}
    result = {}
    for key, value in current_values.items():
        old = previous_values[key]
        result[key] = (value / old - 1) if value is not None and old not in (None, 0) else None
    return result

