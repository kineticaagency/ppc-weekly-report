from __future__ import annotations

import calendar
from datetime import date, timedelta

from .models import Period


def completed_weeks(as_of: date) -> tuple[Period, Period]:
    latest_end = as_of if as_of.weekday() == 6 else as_of - timedelta(days=as_of.weekday() + 1)
    latest = Period(latest_end - timedelta(days=6), latest_end)
    previous_end = latest.start - timedelta(days=1)
    previous = Period(previous_end - timedelta(days=6), previous_end)
    return latest, previous


def month_to_date(as_of: date) -> Period:
    return Period(as_of.replace(day=1), as_of)


def calendar_progress(as_of: date) -> float:
    return as_of.day / calendar.monthrange(as_of.year, as_of.month)[1]
