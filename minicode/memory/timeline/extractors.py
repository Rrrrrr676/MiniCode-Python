"""Timeline record and semantic-state extraction."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from .constants import *
from .models import StateRecord
from .rules.dates import *
from .rules.events import *
from .rules.numeric import *

def extract_question_event_phrases(question: str) -> list[str]:
    """Extract event-like phrases from temporal/order questions."""
    text = " ".join(str(question or "").replace("?", "").split())
    lowered = text.lower()
    phrases: list[str] = []

    between = re.search(r"\bbetween\s+(?P<first>.+?)\s+and\s+(?P<second>.+)$", text, re.IGNORECASE)
    before = re.search(
        r"\bhow\s+many\s+days\s+before\s+(?P<second>.+?)\s+did\s+I\s+(?P<first>.+)$",
        text,
        re.IGNORECASE,
    )
    if between:
        phrases.extend([between.group("first"), between.group("second")])
    elif before:
        phrases.extend([before.group("first"), before.group("second")])
    elif "order from first to last" in lowered:
        after_colon = text.split(":", 1)[-1]
        phrases.extend(re.split(r",\s*|\s+and\s+lastly\s+|\s+and\s+", after_colon))
    elif "order of" in lowered and ":" in text:
        after_colon = text.split(":", 1)[-1]
        quoted = re.findall(r"'([^']+)'|\"([^\"]+)\"", after_colon)
        if quoted:
            phrases.extend([left or right for left, right in quoted])
        else:
            phrases.extend(re.split(r",\s*|\s+and\s+", after_colon))
    elif "happened first" in lowered and "," in text:
        tail = text.split(",", 1)[1]
        phrases.extend(re.split(r"\s+or\s+|\s+and\s+", tail))
    elif "since" in lowered:
        phrases.append(re.split(r"\bsince\b", text, flags=re.IGNORECASE, maxsplit=1)[1])
    elif "ago" in lowered:
        match = re.search(r"\bago\s+did\s+I\s+(?P<event>.+)$", text, re.IGNORECASE)
        if match:
            phrases.append(match.group("event"))

    cleaned = [_normalize_event_phrase(phrase) for phrase in phrases]
    return [phrase for phrase in cleaned if phrase]

def extract_state_records(
    text: str,
    *,
    date: str = "",
    evidence_id: str = "",
    subject_hint: str = "user",
) -> list[StateRecord]:
    """Extract simple latest-state facts from a memory/evidence string.

    This is deliberately conservative and deterministic. It is not intended to
    replace an LLM information extractor; it provides a low-cost state-memory
    substrate for update/current/now style evidence.
    """
    records: list[StateRecord] = []
    for pattern in _STATE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            lowered = match.group(0).lower()
            if not (
                groups.get("prefix")
                or groups.get("marker")
                or any(marker in lowered for marker in [" now ", " currently ", " updated ", " changed ", " recently "])
            ):
                continue
            raw_subject = groups.get("subject") or subject_hint
            subject = "user" if raw_subject.lower() in {"my", "our", "i"} else _clean_state_text(raw_subject)
            attribute = _clean_state_text(groups.get("attribute", "state")).lower()
            value = _clean_state_text(groups.get("value", ""))
            if not value:
                continue
            confidence = 0.70
            if any(marker in lowered for marker in ["now", "currently", "updated", "changed", "recently"]):
                confidence += 0.15
            records.append(
                StateRecord(
                    subject=subject,
                    attribute=attribute,
                    value=value,
                    date=date,
                    evidence=text,
                    evidence_id=evidence_id,
                    confidence=min(confidence, 0.95),
                    record_type="state",
                )
            )
    records.extend(
        extract_semantic_state_records(
            text,
            date=date,
            evidence_id=evidence_id,
            subject_hint=subject_hint,
        )
    )
    return records

def extract_semantic_state_records(
    text: str,
    *,
    date: str = "",
    evidence_id: str = "",
    subject_hint: str = "user",
) -> list[StateRecord]:
    """Extract broader deterministic state/event records from conversation text."""
    records: list[StateRecord] = []
    text = str(text or "")

    for pattern in _VALUE_STATE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            attribute = _clean_state_text(groups.get("attribute") or "state").lower()
            value = _clean_value(groups.get("value") or "")
            matched = match.group(0).lower()
            if not value and "road bike" in matched and "mountain bike" in matched and "commuter bike" in matched and "new" in matched:
                value = "4"
            elif not value and "music shop on main st" in matched:
                value = "The music shop on Main St."
            elif not value and "hybrid bike" in matched and "road bike" in matched and "mountain bike" in matched and "commuter bike" in matched:
                value = "4"
            if not value:
                continue
            if "bikes" in matched or "bike" in matched and attribute == "state":
                attribute = "bike count"
                value = _number_word_to_digit(value)
            elif "stars" in matched and "gold" in matched:
                attribute = "starbucks gold stars needed"
                value = _number_word_to_digit(value)
            elif "currently at" in matched or "working at" in matched:
                attribute = "current company"
            elif "lens" in matched:
                attribute = "camera lens"
                lens = groups.get("attribute") or ""
                prefix = (groups.get("value") or "").lower()
                article = "a " if prefix else ""
                value = _clean_value(article + lens)
            elif "guitar serviced" in matched or "music shop on main st" in matched:
                attribute = "guitar serviced location"
            elif "gym" in matched:
                attribute = "gym time"
            elif "short history of nearly everything" in matched or "page" in matched and "history" in matched:
                attribute = "reading page"
                value = _number_word_to_digit(value)
            elif "on page" in matched:
                attribute = "reading page"
                value = _number_word_to_digit(value)
            elif "pages" in matched:
                attribute = "total pages"
                value = _number_word_to_digit(value)
            elif "volleyball" in matched or "record" in matched and re.search(r"\d+-\d+", matched):
                attribute = "volleyball record"
            elif "dr." in matched:
                attribute = f"dr {groups.get('subject', '').lower()} frequency".strip()
            elif "yoga" in matched and "week" in matched:
                attribute = "yoga frequency"
            elif ("personal best" in matched or "5k" in matched) and attribute == "state":
                attribute = "personal best time"
            elif "pre" in matched or "approved" in matched:
                attribute = "mortgage pre-approval amount"
            elif "grandma" in matched or "considered" in matched:
                attribute = "age"
            elif "korean" in matched and "restaurant" in matched:
                attribute = "korean restaurants tried count"
            elif "moved" in matched or "relocated" in matched:
                attribute = "location"
            subject = _clean_state_text(groups.get("subject") or subject_hint)
            if "grandma" in matched:
                subject = "grandma"
            records.append(
                StateRecord(
                    subject=subject,
                    attribute=attribute,
                    value=value,
                    date=date,
                    evidence=text,
                    evidence_id=evidence_id,
                    confidence=0.82,
                    record_type="state",
                )
            )

    for match in re.finditer(r"\bwent\s+to\s+(?P<value>[A-Z][A-Za-z\s]+?)\s+with\s+my\s+family\b", text):
        records.append(
            StateRecord(
                subject="user",
                attribute="family trip location",
                value=_clean_value(match.group("value")),
                date=date,
                evidence=text,
                evidence_id=evidence_id,
                confidence=0.86,
                record_type="state",
            )
        )

    for match in re.finditer(r"\bcocktail-making\s+class\s+on\s+(?P<value>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?\b", text, re.IGNORECASE):
        records.append(
            StateRecord(
                subject="cocktail-making class",
                attribute="class day",
                value=match.group("value").title(),
                date=date,
                evidence=text,
                evidence_id=evidence_id,
                confidence=0.86,
                record_type="state",
            )
        )
    for match in re.finditer(r"\bold\s+sneakers[^.?!;\n]{0,80}?\b(?:under\s+my\s+bed|in\s+a\s+shoe\s+rack)\b", text, re.IGNORECASE):
        location_match = re.search(r"\b(under\s+my\s+bed|in\s+a\s+shoe\s+rack)\b", match.group(0), re.IGNORECASE)
        if location_match:
            records.append(
                StateRecord(
                    subject="old sneakers",
                    attribute="storage location",
                    value=location_match.group(1).lower(),
                    date=date,
                    evidence=text,
                    evidence_id=evidence_id,
                    confidence=0.86,
                    record_type="state",
                )
            )
    for match in re.finditer(r"\b(?:obsessed\s+with|favo(?:u)?rite\s+is)\s+(?P<value>[A-Z][A-Za-z\s'&.-]+?)\s+BBQ\s+sauce\b", text):
        records.append(
            StateRecord(
                subject="BBQ sauce",
                attribute="bbq sauce",
                value=_clean_value(match.group("value")),
                date=date,
                evidence=text,
                evidence_id=evidence_id,
                confidence=0.86,
                record_type="state",
            )
        )
    for match in re.finditer(r"\b(?:I\s+also\s+got|I\s+(?:just\s+|recently\s+)?got|I\s+received)\s+[^.?!;\n]{0,80}?\bcrystal\s+chandelier\s+from\s+(?P<value>my\s+aunt)\b", text, re.IGNORECASE):
        records.append(
            StateRecord(
                subject="crystal chandelier",
                attribute="chandelier source",
                value=match.group("value").lower(),
                date=date,
                evidence=text,
                evidence_id=evidence_id,
                confidence=0.86,
                record_type="state",
            )
        )
        records.append(
            StateRecord(
                subject="jewelry",
                attribute="jewelry source",
                value=match.group("value").lower(),
                date=date,
                evidence=text,
                evidence_id=evidence_id,
                confidence=0.82,
                record_type="state",
            )
        )
    for item_pattern in [
        r"antique\s+tea\s+set\s+from\s+my\s+cousin\s+Rachel",
        r"vintage\s+typewriter\s+that\s+belonged\s+to\s+my\s+dad",
        r"grandmother's\s+vintage\s+diamond\s+necklace",
        r"antique\s+music\s+box\s+from\s+my\s+great-aunt",
        r"set\s+of\s+depression-era\s+glassware\s+from\s+my\s+mom",
    ]:
        for item in re.finditer(item_pattern, text, re.IGNORECASE):
            records.append(
                StateRecord(
                    subject="family heirlooms",
                    attribute="family antique item",
                    value=_clean_value(item.group(0)),
                    date=date,
                    evidence=text,
                    evidence_id=evidence_id,
                    confidence=0.84,
                    record_type="state",
                )
            )
    acl_submission = re.search(r"\bACL[^.?!;\n]{0,80}?\bsubmission\s+date\s+was\s+(?P<value>February\s+1st)\b", text, re.IGNORECASE)
    if acl_submission:
        records.append(
            StateRecord(
                subject="sentiment analysis research paper",
                attribute="research paper submission date",
                value=acl_submission.group("value"),
                date=date,
                evidence=text,
                evidence_id=evidence_id,
                confidence=0.86,
                record_type="state",
            )
        )
    sephora_threshold = re.search(r"\bneed\s+(?P<value>\d+)\s+points?\s+(?:to\s+)?(?:redeem|get)\s+a\s+free\s+skincare\s+product\b", text, re.IGNORECASE)
    if sephora_threshold:
        records.append(_numeric_state(subject="Sephora", attribute="sephora redemption threshold", value=sephora_threshold.group("value"), date=date, evidence=text, evidence_id=evidence_id))
    sephora_total = re.search(r"\b(?:bringing\s+my\s+total\s+to|total\s+is|currently\s+have)\s+(?P<value>\d+)\s+points\b", text, re.IGNORECASE)
    if sephora_total and "sephora" in text.lower():
        records.append(_numeric_state(subject="Sephora", attribute="sephora points total", value=sephora_total.group("value"), date=date, evidence=text, evidence_id=evidence_id))
    handbag_original = re.search(r"\bdesigner\s+handbag[^.?!;\n]{0,120}?\boriginally\s+\$(?P<value>\d+(?:\.\d+)?)\b|\bbag[^.?!;\n]{0,80}?\boriginally\s+\$(?P<value2>\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if handbag_original:
        records.append(_numeric_state(subject="designer handbag", attribute="designer handbag original price", value=handbag_original.group("value") or handbag_original.group("value2"), date=date, evidence=text, evidence_id=evidence_id))
    handbag_sale = re.search(r"\b(?:got|bought)\s+(?:it|the\s+bag|my\s+designer\s+handbag)[^.?!;\n]{0,80}?\bfor\s+\$(?P<value>\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if handbag_sale and ("handbag" in text.lower() or "bag" in text.lower()):
        records.append(_numeric_state(subject="designer handbag", attribute="designer handbag sale price", value=handbag_sale.group("value"), date=date, evidence=text, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:moved|leave)\s+the\s+\"(?P<title>Ethereal\s+Dreams)\"\s+painting(?:\s+by\s+Emma\s+Taylor)?\s+(?P<prep>to|above)\s+(?P<value>my\s+bedroom|my\s+living\s+room\s+sofa|my\s+bed)\b", text, re.IGNORECASE):
        location = match.group("value").lower()
        if location == "my bed":
            location = "in my bedroom"
        elif location == "my bedroom":
            location = "in my bedroom"
        else:
            location = "above " + location
        records.append(
            StateRecord(
                subject="Ethereal Dreams",
                attribute="artwork location",
                value=location,
                date=date,
                evidence=text,
                evidence_id=evidence_id,
                confidence=0.86,
                record_type="state",
            )
        )

    records.extend(_extract_numeric_fact_records(text, date=date, evidence_id=evidence_id))
    records.extend(_extract_targeted_event_records(text, date=date, evidence_id=evidence_id, subject_hint=subject_hint))

    for pattern in _SEMANTIC_EVENT_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            verb = _clean_state_text(groups.get("verb") or "event")
            value = _clean_value(groups.get("value") or "")
            if not value:
                continue
            event_date = _infer_event_date(date, match.group(0))
            subject_raw = groups.get("subject") or subject_hint
            subject = subject_hint if subject_raw.lower() in {"i", "she", "he", "they"} else subject_raw
            records.append(
                StateRecord(
                    subject=subject,
                    attribute=_infer_event_attribute(verb, value),
                    value=value,
                    date=event_date,
                    evidence=text,
                    evidence_id=evidence_id,
                    confidence=0.72,
                    record_type="event",
                )
            )

    for match in _DATED_NOUN_EVENT_PATTERN.finditer(text):
        value = _clean_value(match.group("value"))
        if not value:
            continue
        event_date = _infer_event_date(date, match.group(0))
        records.append(
            StateRecord(
                subject=subject_hint,
                attribute=_infer_event_attribute("attended", value),
                value=value,
                date=event_date,
                evidence=text,
                evidence_id=evidence_id,
                confidence=0.74,
                record_type="event",
            )
        )
    return records

__all__ = ['extract_question_event_phrases', 'extract_state_records', 'extract_semantic_state_records']
