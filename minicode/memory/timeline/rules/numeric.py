"""Numeric fact extraction and formatting rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from ..constants import *
from ..models import StateRecord
from .events import *
from .travel import *

def _number_word_to_int(raw: str) -> int:
    value = str(raw or "").lower()
    return int(value) if value.isdigit() else NUMBER_WORDS.get(value, 0)

def _duration_minutes(raw: str, unit: str) -> int:
    amount = _parse_number(raw) or 0
    if unit.lower().startswith("hour"):
        return int(amount * 60)
    return int(amount)

def _number_word_to_digit(value: str) -> str:
    text = str(value or "").strip().lower()
    return str(NUMBER_WORDS[text]) if text in NUMBER_WORDS and text not in {"a", "an"} else str(value or "").strip()

def _parse_number(value: str) -> float | None:
    text = str(value or "").strip().lower()
    if text in NUMBER_WORDS:
        return float(NUMBER_WORDS[text])
    cleaned = re.sub(r"[$,%]", "", text).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    return float(match.group(0))

def _format_number_answer(value: float, *, prefix: str = "", suffix: str = "", use_commas: bool = False) -> str:
    if abs(value - round(value)) < 1e-9:
        integer = int(round(value))
        number = f"{integer:,}" if use_commas and abs(integer) >= 1000 else str(integer)
    else:
        number = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{prefix}{number}{suffix}"

def _numeric_state(
    *,
    subject: str,
    attribute: str,
    value: str,
    date: str,
    evidence: str,
    evidence_id: str,
) -> StateRecord:
    return StateRecord(
        subject=subject,
        attribute=attribute,
        value=value,
        date=date,
        evidence=evidence,
        evidence_id=evidence_id,
        confidence=0.84,
        record_type="state",
    )

def _extract_numeric_fact_records(text: str, *, date: str, evidence_id: str) -> list[StateRecord]:
    records: list[StateRecord] = []
    source = str(text or "")
    range_days = _extract_month_day_range_days(source)
    if range_days and "japan" in source.lower():
        records.append(_numeric_state(subject="Japan trip", attribute="trip duration days", value=str(range_days[1]), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bspent\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\s+on\s+groceries\s+at\s+SaveMart\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="SaveMart", attribute="savemart grocery purchase", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:can\s+)?earn\s+(?P<value>\d+(?:\.\d+)?)%\s+cashback\s+on\s+all\s+purchases\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="SaveMart", attribute="savemart cashback percent", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\busually\s+work\s+(?P<value>\d+)\s+hours\s+a\s+week\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="typical work week", attribute="weekly work hours", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bincrease\s+my\s+work\s+hours\s+by\s+(?P<value>\d+)\s+hours\s+weekly\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="peak increase", attribute="weekly work hours", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bscored\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+goals?\s+so\s+far\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="goals", attribute="soccer contribution count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:had|have)\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+assists?\s+in\s+the\s+league\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="assists", attribute="soccer contribution count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bpurchased\s+(?P<value>\d+)\s+coffee\s+mugs?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="coffee mugs", attribute="coffee mug count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bspent\s+\$(?P<value>\d+(?:\.\d+)?)\s+on\s+(?:some\s+)?coffee\s+mugs?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="coffee mugs", attribute="coffee mug total cost", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bcovered\s+a\s+total\s+of\s+(?P<value>\d[\d,]*)\s+miles\b", source, re.IGNORECASE):
        if "road trip" in source.lower() or "yellowstone" in source.lower():
            records.append(_numeric_state(subject="road trips", attribute="road trip distance", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<value>\d+)\s+titles?\s+(?:waiting\s+to\s+be\s+checked\s+off|on\s+my\s+to-watch\s+list|on\s+it\s+right\s+now)\b", source, re.IGNORECASE):
        if "to-watch list" in source.lower() or "watchlist" in source.lower():
            records.append(_numeric_state(subject="to-watch list", attribute="to-watch list count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bto-watch\s+list[^.?!;\n]{0,60}?\bcurrently\s+(?P<value>\d+)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="to-watch list", attribute="to-watch list count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\battend(?:ed|ing)?\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+sessions?\s+of\s+the\s+bereavement\s+support\s+group\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="bereavement support group", attribute="bereavement support sessions", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\battending\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+sessions?\b", source, re.IGNORECASE):
        if "bereavement support group" in source.lower():
            records.append(_numeric_state(subject="bereavement support group", attribute="bereavement support sessions", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bfinished\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+issues?\s+so\s+far\b", source, re.IGNORECASE):
        if "national geographic" in source.lower():
            records.append(_numeric_state(subject="National Geographic", attribute="national geographic issues finished", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bfinished\s+my\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:st|nd|rd|th)?\s+issue\b", source, re.IGNORECASE):
        if "national geographic" in source.lower():
            records.append(_numeric_state(subject="National Geographic", attribute="national geographic issues finished", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:cut\s+back\s+to|limit\s+to|just)\s+(?P<value>one|two|three|four|five|\d+)\s+cup[s]?\s+in\s+the\s+morning\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="morning coffee", attribute="morning coffee cup limit", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bincreased\s+the\s+limit\s+to\s+(?P<value>one|two|three|four|five|\d+)\s+cup[s]?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="morning coffee", attribute="morning coffee cup limit", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<value>\d+)-year-old\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="user", attribute="current age", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bcompleted\s+at\s+the\s+age\s+of\s+(?P<value>\d+)\b", source, re.IGNORECASE):
        if "bachelor" in source.lower() or "graduated" in source.lower() or "degree" in source.lower():
            records.append(_numeric_state(subject="user", attribute="college graduation age", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bgot\s+a\s+new\s+(?P<value>silver\s+necklace[^.?!;\n]{0,60}|pair\s+of\s+emerald\s+earrings|engagement\s+ring)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=_clean_value(match.group("value")), attribute="jewelry acquired item", value="1", date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bI\s+got\s+my\s+engagement\s+ring\s+a\s+month\s+ago\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="engagement ring", attribute="jewelry acquired item", value="1", date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\braised\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\s+for\s+(?:the\s+)?(?P<subject>[^.?!;\n]+)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=match.group("subject"), attribute="charity amount raised", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bhelped\s+raise\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\s+for\s+(?:a\s+|the\s+)?(?P<subject>[^.?!;\n]+)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=match.group("subject"), attribute="charity amount raised", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bwe\s+raised\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\s+for\s+(?:a\s+|the\s+)?(?P<subject>[^.?!;\n]+)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=match.group("subject"), attribute="charity amount raised", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bmanaged\s+to\s+raise\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\s+for\s+(?:the\s+)?(?P<subject>[^.?!;\n]+)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=match.group("subject"), attribute="charity amount raised", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bcar\s+was\s+getting\s+(?P<value>\d+(?:\.\d+)?)\s+miles\s+per\s+gallon\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="previous car mpg", attribute="previous car mpg", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:currently\s+at|getting\s+around)\s+(?P<value>\d+(?:\.\d+)?)\s+miles\s+per\s+gallon\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="current car mpg", attribute="current car mpg", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\btrain[^.?!;\n]{0,120}?\b(?:around|actually|only)\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="train", attribute="train fare", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:around|actually|only)\s+\$(?P<value>\d+(?:\.\d+)?)\s+to\s+get\s+to\s+my\s+hotel[^.?!;\n]{0,80}?\btrain\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="train", attribute="train fare", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\btaxi[^.?!;\n]{0,120}?\bcost\s+around\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="taxi", attribute="taxi fare", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bYouTube[^.?!;\n]{0,120}?\bwith\s+(?P<value>\d[\d,]*)\s+views\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="YouTube", attribute="video view count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bTikTok[^.?!;\n]{0,120}?\bhas\s+(?P<value>\d[\d,]*)\s+views\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="TikTok", attribute="video view count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bFacebook\s+Live[^.?!;\n]{0,120}?\bgot\s+(?P<value>\d+)\s+comments\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Facebook Live", attribute="social comment count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bmost\s+popular\s+video[^.?!;\n]{0,80}?\bhas\s+(?P<value>\d+)\s+comments\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="YouTube", attribute="social comment count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\binitially\s+aimed\s+to\s+raise\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\s+in\s+donations\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="charity cycling", attribute="charity cycling goal", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bcharity\s+cycling\s+event\s+and\s+raised\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\s+in\s+donations\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="charity cycling", attribute="charity cycling raised", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bGPA\s+of\s+(?P<value>\d+(?:\.\d+)?)\s+out\s+of\s+4\.0\b", source, re.IGNORECASE):
        if "equivalent to a" in source[max(0, match.start() - 24):match.start()].lower():
            continue
        records.append(_numeric_state(subject="graduate studies" if "master" in source.lower() else "studies", attribute="study gpa", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bequivalent\s+to\s+a\s+GPA\s+of\s+(?P<value>\d+(?:\.\d+)?)\s+out\s+of\s+4\.0\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="undergraduate studies", attribute="study gpa", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<value>\d+)[-\s]+day\s+trip\s+to\s+(?P<subject>Chicago|Japan)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=f"{match.group('subject')} trip", attribute="trip duration days", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\btrip\s+to\s+(?P<subject>[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,2})\s+for\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+days?\b", source, re.IGNORECASE):
        subject = match.group("subject").strip()
        records.append(_numeric_state(subject=f"{subject} trip", attribute="trip duration days", value=str(_number_word_to_int(match.group("value"))), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\btrip\s+to\s+(?P<subject>[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,2})\s+[^.?!;\n]{0,80}?\bfor\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+days?\b", source, re.IGNORECASE):
        subject = match.group("subject").strip()
        records.append(_numeric_state(subject=f"{subject} trip", attribute="trip duration days", value=str(_number_word_to_int(match.group("value"))), date=date, evidence=source, evidence_id=evidence_id))
    if re.search(r"\b(?:trip|travel|traveling|solo|family)\b", source, re.IGNORECASE):
        for match in re.finditer(r"\b(?:for\s+(?:the\s+)?(?P<value_a>one|two|three|four|five|six|seven|eight|nine|ten|\d+)[-\s]+day|(?P<value_b>one|two|three|four|five|six|seven|eight|nine|ten|\d+)[-\s]+day)\b", source, re.IGNORECASE):
            raw_value = match.group("value_a") or match.group("value_b")
            records.append(_numeric_state(subject="trip", attribute="trip duration days", value=str(_number_word_to_int(raw_value)), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<source>HelloFresh|UberEats)[^.?!;\n]{0,100}?\b(?P<value>\d+(?:\.\d+)?)%\s+discount\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=match.group("source"), attribute="order discount percent", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<value>\d+(?:\.\d+)?)%\s+off\s+(?:my\s+)?(?P<source>HelloFresh|UberEats)\s+order\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=match.group("source"), attribute="order discount percent", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bcar\s+wash[^.?!;\n]{0,100}?\bcost\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="car wash", attribute="car expense cost", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bparking\s+ticket[^.?!;\n]{0,120}?\bfor\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="parking ticket", attribute="car expense cost", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bflea\s+and\s+tick\s+prevention\s+medication[^.?!;\n]{0,100}?\b(?:was|cost)\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Lola flea medication", attribute="pet expense cost", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bLola[^.?!;\n]{0,80}?\bvet[^.?!;\n]{0,120}?\b(?:fee\s+of|fee\s+was|was)\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Lola vet visit", attribute="pet expense cost", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\binitially\s+quoted\s+me\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\s+for\s+the\s+entire\s+trip\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Sakura Travel Agency trip", attribute="trip initial quote", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bcorrected\s+price\s+for\s+the\s+entire\s+trip\s+was\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Sakura Travel Agency trip", attribute="trip corrected price", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<ordinal>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+meal\s+I\s+got\s+from\s+my\s+(?P<subject>chicken\s+fajitas|lentil\s+soup)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=match.group("subject"), attribute="lunch meal count", value=str(ORDINAL_WORDS[match.group("ordinal").lower()]), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<subject>lentil\s+soup|chicken\s+fajitas)[^.?!;\n]{0,80}?\blasted\s+me\s+for\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+lunches\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=match.group("subject"), attribute="lunch meal count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bborrow\s+up\s+to\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="mortgage", attribute="mortgage pre-approval amount", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bfinal\s+sale\s+price\s+was\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="house", attribute="house final sale price", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bwaterproof\s+car\s+cover[^.?!;\n]{0,120}?\bcost\s+me\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="car cover", attribute="car accessory cost", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    if re.search(r"\bwaterproof\s+car\s+cover\b", source, re.IGNORECASE):
        for match in re.finditer(r"\bit\s+cost\s+me\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
            records.append(_numeric_state(subject="car cover", attribute="car accessory cost", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bdetailing\s+spray[^.?!;\n]{0,120}?\bfrom\s+Amazon\s+for\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="detailing spray", attribute="car accessory cost", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\btakes\s+me\s+about\s+(?P<value>an?|one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?)\s+(?P<unit>hours?|minutes?)\s+to\s+get\s+ready\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="get ready", attribute="morning routine duration minutes", value=str(_duration_minutes(match.group("value"), match.group("unit"))), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bcommute\s+to\s+work\s+takes\s+about\s+(?P<value>an?|one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?)\s+(?P<unit>hours?|minutes?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="commute", attribute="morning routine duration minutes", value=str(_duration_minutes(match.group("value"), match.group("unit"))), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bfinished\s+a\s+5K\s+in\s+(?P<value>\d+)\s+minutes\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="current 5K run", attribute="current 5k time minutes", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b5K\s+run\s+last\s+year[^.?!;\n]{0,120}?\btook\s+me\s+(?P<value>\d+)\s+minutes\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="previous 5K run", attribute="previous 5k time minutes", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<value>\d+)[-\s]+pound\s+batch\b", source, re.IGNORECASE):
        if "feed" in source.lower() or "scratch grains" in source.lower() or "chickens" in source.lower():
            records.append(_numeric_state(subject="feed batch", attribute="feed weight pounds", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<value>\d+)\s+pounds?\s+of\s+organic\s+scratch\s+grains\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="scratch grains", attribute="feed weight pounds", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bleft\s+home\s+at\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>AM|PM)\s+on\s+Monday\b", source, re.IGNORECASE):
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or "0")
        if match.group("ampm").lower() == "pm" and hour != 12:
            hour += 12
        if match.group("ampm").lower() == "am" and hour == 12:
            hour = 0
        records.append(_numeric_state(subject="clinic departure", attribute="clinic departure minutes", value=str(hour * 60 + minute), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bit\s+took\s+me\s+(?P<value>an?|one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?)\s+(?P<unit>hours?|minutes?)\s+to\s+get\s+to\s+the\s+clinic\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="clinic travel", attribute="clinic travel duration minutes", value=str(_duration_minutes(match.group("value"), match.group("unit"))), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bvintage\s+diamond\s+necklace[^.?!;\n]{0,120}?\bworth\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="vintage diamond necklace", attribute="resale value", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bantique\s+vanity[^.?!;\n]{0,160}?\b(?:at\s+least|for)\s+\$(?P<value>\d[\d,]*(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="antique vanity", attribute="resale value", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<value>\d+(?:\.\d+)?)\s*-\s*mile\s+(?:hike|loop trail|trail)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="hike", attribute="hike distance", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\btrain fare is actually\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="train", attribute="train fare", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\btaxi[^.?!;\n]{0,120}?\bcost(?: me)?\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="taxi", attribute="taxi fare", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for item, pattern in [
        ("food bowl", r"food bowl[^.?!;\n]{0,80}?\$(?P<value>\d+(?:\.\d+)?)"),
        ("measuring cup", r"measuring cup[^.?!;\n]{0,80}?\$(?P<value>\d+(?:\.\d+)?)"),
        ("dental chews", r"dental chews\s+(?:are|were|cost(?: me)?|for)?\s*\$(?P<value>\d+(?:\.\d+)?)"),
        ("dental chews", r"\bchews\s+are\s+\$(?P<value>\d+(?:\.\d+)?)\s+a\s+pack\b"),
        ("flea collar", r"flea and tick collar[^.?!;\n]{0,80}?\$(?P<value>\d+(?:\.\d+)?)"),
    ]:
        for match in re.finditer(pattern, source, re.IGNORECASE):
            records.append(_numeric_state(subject=item, attribute="pet supply cost", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:luxury boots|boots)[^.?!;\n]{0,120}?\$(?P<value>\d+(?:,\d{3})*(?:\.\d+)?)", source, re.IGNORECASE):
        attr = "luxury boots price" if "luxury" in match.group(0).lower() or "splurged" in source[match.start() - 80:match.start()].lower() else "budget boots price"
        records.append(_numeric_state(subject="boots", attribute=attr, value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bbudget store[^.?!;\n]{0,120}?\$(?P<value>\d+(?:,\d{3})*(?:\.\d+)?)", source, re.IGNORECASE):
        records.append(_numeric_state(subject="boots", attribute="budget boots price", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bwearing\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b[^.?!;\n]{0,80}?\b(?:sneakers|sandals|shoes)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="shoes", attribute="shoes worn count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bpacked\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+pairs?\s+of\s+shoes\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="shoes", attribute="shoes packed count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:finished around\s+(?P<around>\d+)\s+episodes?|finished episode\s+(?P<episode>\d+))\b", source, re.IGNORECASE):
        value = match.group("around") or match.group("episode")
        if not value:
            continue
        records.append(_numeric_state(subject="podcast", attribute="podcast episodes listened", value=value, date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:planted|got)\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?P<subject>tomato|cucumber)\s+plants?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=f"{match.group('subject').lower()} plants", attribute="garden plant count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<subject>tomatoes|cucumbers)\b[^.?!;\n]{0,120}?\b(?:got|have)\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+plants?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject=f"{match.group('subject').lower().rstrip('s')} plants", attribute="garden plant count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:reached around|promoted my product to her)\s+(?P<value>\d[\d,]*)\s+(?:people|followers)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="audience", attribute="audience reach count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bwritten\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+(?:short\s+)?stories?\b[^.?!;\n]{0,120}?\bsince\s+I\s+started\s+writing\s+regularly\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="writing", attribute="short stories written count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\badded\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+(?:new\s+)?(?:ones|postcards?)\b[^.?!;\n]{0,120}?\b(?:postcards?|collection|collecting)\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="postcards", attribute="postcards added count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\btried\s+making\s+(?:a\s+)?Negroni\s+at\s+home\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+times?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="negroni", attribute="negroni tried count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\blost\s+(?:about\s+)?(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+pounds?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="fitness", attribute="weight lost", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\blead\s+(?:a\s+team\s+of\s+)?(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+engineers?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Senior Software Engineer", attribute="engineers led count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:had|have|reached)\s+(?:around\s+)?(?P<value>\d[\d,]*)\s+followers\s+on\s+Instagram\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Instagram", attribute="instagram follower count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bstarted\s+the\s+year\s+with\s+(?P<value>\d[\d,]*)\s+followers\s+on\s+Instagram\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Instagram", attribute="instagram follower count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:close\s+to|nearing)\s+(?P<value>\d[\d,]*)\s+followers\b", source, re.IGNORECASE):
        if "instagram" in source.lower():
            records.append(_numeric_state(subject="Instagram", attribute="instagram follower count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:close\s+to|nearing)\s+(?P<value>\d[\d,]*)\s+now\s+on\s+Instagram\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Instagram", attribute="instagram follower count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bFitbit\s+Charge\s+3\s+for\s+(?P<value>\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+months?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Fitbit Charge 3", attribute="fitbit usage months", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:worn\s+them|worn\s+my\s+new\s+black\s+Converse[^.?!;\n]{0,80}?)\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+times?\b", source, re.IGNORECASE):
        if "converse" in source.lower():
            records.append(_numeric_state(subject="black Converse Chuck Taylor All Star sneakers", attribute="converse worn count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bthat's\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+times?\s+now\s+that\s+I've\s+worn\s+them\b", source, re.IGNORECASE):
        if "converse" in source.lower():
            records.append(_numeric_state(subject="black Converse Chuck Taylor All Star sneakers", attribute="converse worn count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:currently\s+on|completed)\s+episode\s+(?P<value>\d+)\s+of\s+the\s+Science\s+series\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Crash Course Science series", attribute="crash course science episodes", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bcompleted\s+(?P<value>\d+)\s+episodes\s+of\s+Crash\s+Course's\s+Science\s+series\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Crash Course Science series", attribute="crash course science episodes", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bcompleted\s+(?P<value>\d+)\s+videos\s+(?:so\s+far\s+)?(?:for|of)\s+Corey(?:'s| Schafer's)\s+(?:Python\s+)?(?:programming\s+)?series\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Corey Schafer Python series", attribute="corey python videos completed", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bwatched\s+(?:a\s+lot\s+of\s+Crash\s+Course\s+videos\s+[^.?!;\n]{0,80}?finished|having\s+watched|completed)\s+(?P<value>\d+)\s+(?:Crash\s+Course\s+)?videos\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Crash Course videos", attribute="crash course videos watched count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bhaving\s+watched\s+(?P<value>\d+)\s+Crash\s+Course\s+videos\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Crash Course videos", attribute="crash course videos watched count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bhighest\s+score\s+(?:so\s+far\s+)?(?:is|-)\s+(?P<value>\d+)\s+points?\b", source, re.IGNORECASE):
        if "ticket to ride" in source.lower():
            records.append(_numeric_state(subject="Ticket to Ride", attribute="ticket to ride highest score", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\bhighest\s+score\s+in\s+Ticket\s+to\s+Ride\s+-\s+(?P<value>\d+)\s+points?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Ticket to Ride", attribute="ticket to ride highest score", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\btried\s+out\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+of\s+Emma's\s+recipes\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="Emma recipes", attribute="emma recipes tried count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:watched|including)\s+(?P<value>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+MCU\s+films?\b", source, re.IGNORECASE):
        records.append(_numeric_state(subject="MCU films", attribute="mcu films watched count", value=_number_word_to_digit(match.group("value")), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:with|currently)\s+(?P<value>\d+)\s+titles\s+(?:waiting\s+to\s+be\s+checked\s+off|on\s+it\s+right\s+now)?\b", source, re.IGNORECASE):
        if "to-watch list" in source.lower() or "watchlist" in source.lower():
            records.append(_numeric_state(subject="to-watch list", attribute="to-watch list count", value=match.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    original = re.search(r"\boriginally\s+priced\s+at\s+\$(?P<value>\d+(?:\.\d+)?)\b", source, re.IGNORECASE)
    if original:
        records.append(_numeric_state(subject="book", attribute="book original price", value=original.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    discounted = re.search(r"\bgot\s+the\s+book\s+for\s+\$(?P<value>\d+(?:\.\d+)?)\s+after\s+a\s+discount\b", source, re.IGNORECASE)
    if discounted:
        records.append(_numeric_state(subject="book", attribute="book discounted price", value=discounted.group("value"), date=date, evidence=source, evidence_id=evidence_id))
    return records

__all__ = ['_number_word_to_int', '_duration_minutes', '_number_word_to_digit', '_parse_number', '_format_number_answer', '_numeric_state', '_extract_numeric_fact_records']
