"""Travel-target and duration matching rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from ..constants import *
from ..models import StateRecord

def _duration_sum_travel_targets(question: str) -> list[str]:
    lowered = str(question or "").lower().rstrip("?.! ")
    match = re.search(r"\btravel(?:ing|ling|ed)?\s+in\s+(?P<targets>.+)$", lowered)
    if not match:
        match = re.search(r"\bspent\s+in\s+(?P<targets>.+)$", lowered)
    if not match:
        return []
    raw = match.group("targets")
    raw = re.split(r"\b(?:this year|last year|today|recently)\b", raw, maxsplit=1)[0]
    parts = [part.strip(" ,") for part in re.split(r"\s+and\s+|,", raw) if part.strip(" ,")]
    targets: list[str] = []
    for part in parts:
        part = re.sub(r"^(?:in|the)\s+", "", part).strip()
        tokens = [token for token in _travel_tokenize(part) if token not in STOPWORDS and token not in {"total", "traveling", "travel"}]
        if tokens:
            targets.append(" ".join(tokens))
    return targets

def _record_haystack(record: StateRecord) -> str:
    return " ".join([record.subject, record.attribute, record.value, record.evidence]).lower()

def _record_session_id(record: StateRecord) -> str:
    return str(record.evidence_id or "").split(":", maxsplit=1)[0]

def _target_aliases(target: str) -> set[str]:
    normalized = " ".join(_travel_tokenize(target))
    aliases = {normalized}
    aliases.update(TRAVEL_LOCATION_ALIASES.get(normalized, set()))
    return aliases

def _text_matches_target(text: str, target: str) -> bool:
    lowered = str(text or "").lower()
    aliases = _target_aliases(target)
    if any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in aliases):
        return True
    target_tokens = [token for token in _travel_tokenize(target) if token not in STOPWORDS]
    return bool(target_tokens) and all(re.search(rf"\b{re.escape(token)}\b", lowered) for token in target_tokens)

def _contains_other_travel_location(text: str, target: str) -> bool:
    lowered = str(text or "").lower()
    target_aliases = _target_aliases(target)
    for location in KNOWN_TRAVEL_LOCATIONS:
        if location in target_aliases:
            continue
        if re.search(rf"\b{re.escape(location)}\b", lowered):
            return True
    return False

def _duration_target_score(record: StateRecord, target: str) -> int:
    hay = _record_haystack(record)
    score = 0
    if _text_matches_target(" ".join([record.subject, record.attribute, record.value]).lower(), target):
        score += 2
    if _text_matches_target(hay, target):
        score += 1
    return score

def _display_target(target: str) -> str:
    words = target.split()
    if target == "new york city":
        return "New York City"
    return " ".join(word.upper() if word == "nyc" else word.capitalize() for word in words)

def _extract_month_day_range_days(text: str) -> tuple[str, int] | None:
    match = re.search(
        r"\bfrom\s+(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)\s+"
        r"(?P<start>\d{1,2})(?:st|nd|rd|th)?\s+to\s+(?P<end>\d{1,2})(?:st|nd|rd|th)?\b",
        str(text or ""),
        re.IGNORECASE,
    )
    if not match:
        return None
    start = int(match.group("start"))
    end = int(match.group("end"))
    if end < start:
        return None
    return match.group("month").lower(), end - start

def _travel_tokenize(text: object) -> list[str]:
    return [
        tok.lower()
        for tok in TOKEN_RE.findall(str(text or ""))
        if len(tok) > 1 and tok.lower() not in STOPWORDS
    ]


__all__ = ['_duration_sum_travel_targets', '_record_haystack', '_record_session_id', '_target_aliases', '_text_matches_target', '_contains_other_travel_location', '_duration_target_score', '_display_target', '_extract_month_day_range_days']
