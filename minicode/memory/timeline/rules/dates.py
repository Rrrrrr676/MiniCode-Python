"""Date parsing and temporal inference rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from ..constants import *

def date_key(value: str) -> tuple[int, str]:
    """Return a sortable date key while tolerating non-ISO dataset dates."""
    if not value:
        return (0, "")
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return (1, datetime.strptime(text[: len(fmt)], fmt).isoformat())
        except ValueError:
            pass
    return (1, text)

def parse_date(value: str) -> datetime | None:
    """Parse dataset dates such as YYYY/MM/DD (Tue) into datetimes."""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    match = re.search(r"\d{4}[-/]\d{2}[-/]\d{2}", text)
    if match:
        normalized = match.group(0).replace("/", "-")
        try:
            return datetime.strptime(normalized, "%Y-%m-%d")
        except ValueError:
            return None
    return None

def _format_inferred_date(value: datetime, base_date: str) -> str:
    if "/" in str(base_date):
        return value.strftime("%Y/%m/%d")
    return value.strftime("%Y-%m-%d")

def _black_friday(year: int) -> datetime:
    november_first = datetime(year, 11, 1)
    days_until_friday = (4 - november_first.weekday()) % 7
    first_friday = november_first + timedelta(days=days_until_friday)
    return first_friday + timedelta(days=21)

def _infer_event_date(base_date: str, text: str) -> str:
    """Infer an event date from explicit or relative dates in a turn."""
    base = parse_date(base_date)
    if base is None:
        return base_date
    lowered = str(text or "").lower()

    explicit = re.search(
        r"\b(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)\s+"
        r"(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,\s*(?P<year>\d{4}))?",
        lowered,
        re.IGNORECASE,
    )
    if explicit:
        month = MONTHS[explicit.group("month").lower()]
        day = int(explicit.group("day"))
        year = int(explicit.group("year")) if explicit.group("year") else base.year
        if explicit.group("year") is None and month > base.month + 1:
            year -= 1
        try:
            return _format_inferred_date(datetime(year, month, day), base_date)
        except ValueError:
            return base_date

    day_of_month = re.search(
        r"\b(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+of\s+"
        r"(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)\b",
        lowered,
        re.IGNORECASE,
    )
    if day_of_month:
        month = MONTHS[day_of_month.group("month").lower()]
        day = int(day_of_month.group("day"))
        year = base.year
        if month > base.month + 1:
            year -= 1
        try:
            return _format_inferred_date(datetime(year, month, day), base_date)
        except ValueError:
            return base_date

    numeric_explicit = re.search(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})(?:/(?P<year>\d{2,4}))?\b", lowered)
    if numeric_explicit:
        month = int(numeric_explicit.group("month"))
        day = int(numeric_explicit.group("day"))
        raw_year = numeric_explicit.group("year")
        year = int(raw_year) if raw_year else base.year
        if raw_year and year < 100:
            year += 2000
        if raw_year is None and month > base.month + 1:
            year -= 1
        try:
            return _format_inferred_date(datetime(year, month, day), base_date)
        except ValueError:
            return base_date

    if "yesterday" in lowered:
        return _format_inferred_date(base - timedelta(days=1), base_date)
    if "today" in lowered:
        return base_date
    if "tomorrow" in lowered:
        return _format_inferred_date(base + timedelta(days=1), base_date)
    if "a couple of days ago" in lowered:
        return _format_inferred_date(base - timedelta(days=2), base_date)
    if "last week" in lowered:
        return _format_inferred_date(base - timedelta(days=7), base_date)
    if "last month" in lowered:
        return _format_inferred_date(base - timedelta(days=30), base_date)
    if "last weekend" in lowered or "past weekend" in lowered:
        return _format_inferred_date(_previous_weekday(base, WEEKDAYS["saturday"]), base_date)
    weekday_match = re.search(
        r"\blast\s+(?P<weekday>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        lowered,
    )
    if weekday_match:
        return _format_inferred_date(_previous_weekday(base, WEEKDAYS[weekday_match.group("weekday")]), base_date)

    if "black friday" in lowered:
        year = base.year
        if base.month < 11:
            year -= 1
        black_friday = _black_friday(year)
        if "week before black friday" in lowered or "a week before black friday" in lowered:
            black_friday -= timedelta(days=7)
        return _format_inferred_date(black_friday, base_date)

    rel = re.search(
        r"\b(?P<num>a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
        r"(?P<unit>days?|weeks?|months?)\s+ago\b",
        lowered,
    )
    if rel:
        raw = rel.group("num")
        amount = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 0)
        unit = rel.group("unit")
        days = amount
        if unit.startswith("week"):
            days = amount * 7
        elif unit.startswith("month"):
            days = amount * 30
        return _format_inferred_date(base - timedelta(days=days), base_date)

    past_duration = re.search(
        r"\bfor\s+(?:the\s+)?past\s+(?P<num>a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
        r"(?P<unit>days?|weeks?|months?)\b",
        lowered,
    )
    if past_duration:
        raw = past_duration.group("num")
        amount = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 0)
        unit = past_duration.group("unit")
        days = amount
        if unit.startswith("week"):
            days = amount * 7
        elif unit.startswith("month"):
            days = amount * 30
        return _format_inferred_date(base - timedelta(days=days), base_date)

    return base_date

def _extract_duration_days(text: str) -> int:
    lowered = str(text or "").lower()
    compact = re.search(
        r"\b(?P<num>one|two|three|four|five|six|seven|eight|nine|ten|\d+)[-\s]+day\b",
        lowered,
    )
    if compact:
        raw = compact.group("num")
        return int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 0)
    duration = re.search(
        r"\bfor\s+(?P<num>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+days?\b",
        lowered,
    )
    if duration:
        raw = duration.group("num")
        return int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 0)
    return 0

def _previous_weekday(base: datetime, target_weekday: int) -> datetime:
    delta = (base.weekday() - target_weekday) % 7
    if delta == 0:
        delta = 7
    return base - timedelta(days=delta)

def _relative_target_date(question: str, reference_date: str) -> datetime | None:
    ref = parse_date(reference_date)
    if ref is None:
        return None
    q = question.lower()
    if "a couple of days ago" in q:
        return ref - timedelta(days=2)
    weekday_match = re.search(
        r"\blast\s+(?P<weekday>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        q,
    )
    if weekday_match:
        return _previous_weekday(ref, WEEKDAYS[weekday_match.group("weekday")])
    if "last weekend" in q or "past weekend" in q:
        return _previous_weekday(ref, WEEKDAYS["saturday"])
    rel = re.search(
        r"\b(?P<num>a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
        r"(?P<unit>days?|weeks?|months?)\s+ago\b",
        q,
    )
    if rel:
        raw = rel.group("num")
        amount = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 0)
        unit = rel.group("unit")
        days = amount
        if unit.startswith("week"):
            days = amount * 7
        elif unit.startswith("month"):
            days = amount * 30
        return ref - timedelta(days=days)
    return None

__all__ = ['date_key', 'parse_date', '_format_inferred_date', '_black_friday', '_infer_event_date', '_extract_duration_days', '_previous_weekday', '_relative_target_date']
