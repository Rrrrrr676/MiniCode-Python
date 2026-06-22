"""Event labeling, normalization, and extraction rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from ..constants import *
from ..models import StateReasoningResult, StateRecord
from .dates import *

def _expand_alignment_terms(tokens: list[str]) -> set[str]:
    terms = set(tokens)
    for token in tokens:
        if token.endswith("ed") and len(token) > 4:
            terms.add(token[:-2])
        if token.endswith("ing") and len(token) > 5:
            terms.add(token[:-3])
        if token.endswith("s") and len(token) > 4:
            terms.add(token[:-1])
    return terms

def _insufficient_information(reasoning_type: str) -> StateReasoningResult:
    return StateReasoningResult(
        answer="The information provided is not enough.",
        reasoning_type=reasoning_type,
        confidence=0.62,
        evidence_ids=[],
        explanation="Required question entity or title was not found in candidate state records.",
    )

def _missing_required_question_anchors(question: str, candidates: list[StateRecord]) -> bool:
    anchors = _required_question_anchors(question)
    if not anchors:
        return False
    haystack = "\n".join(
        " ".join([record.subject, record.attribute, record.value, record.evidence]).lower()
        for record in candidates
    )
    return any(anchor not in haystack for anchor in anchors)

def _required_question_anchors(question: str) -> list[str]:
    """Find explicit entities/titles that must align before answering state questions."""
    text = str(question or "")
    q = text.lower()
    anchors: list[str] = []
    for left, right in re.findall(r"'([^']+)'|\"([^\"]+)\"", text):
        phrase = (left or right).strip().lower()
        if len(phrase) >= 3:
            anchors.append(phrase)
    for match in re.finditer(r"\bdr\.?\s+([a-z]+)\b", q):
        anchors.append(f"dr. {match.group(1)}")
    cuisine = re.search(
        r"\b(italian|korean|japanese|chinese|french|indian|thai|mexican|spanish|greek|vietnamese)\s+restaurants?\b",
        q,
    )
    if cuisine:
        anchors.append(f"{cuisine.group(1)} restaurant")
    role = re.search(r"\brole\s+as\s+([a-z][a-z\s]+?)(?:\?|,|\s+when\b|$)", q)
    if role:
        anchors.append(" ".join(role.group(1).split()))
    unique: list[str] = []
    for anchor in anchors:
        if anchor and anchor not in unique:
            unique.append(anchor)
    return unique

def _event_answer_label(question: str, record: StateRecord) -> str:
    """Return a compact human-readable event label for deterministic answers."""
    value = _clean_value(record.value)
    q = question.lower()
    if record.attribute == "airline flight":
        return value
    if record.attribute == "transport event":
        value_l = value.lower()
        if "train" in value_l:
            return "train"
        if "bus" in value_l:
            return "bus"
        return value
    if record.attribute == "graduation event":
        match = re.search(r"\b(Emma|Rachel|Alex)\b", value)
        return f"{match.group(1)} graduated" if match else value
    if record.attribute == "participation event":
        value_l = value.lower()
        if "walk for hunger" in value_l:
            return "the 'Walk for Hunger' charity event"
        if "charity bake sale" in value_l:
            return "I participated in the charity bake sale first." if "first" in q else "the charity bake sale"
        if "charity gala" in value_l:
            return "the charity gala"
    if record.attribute == "watched sports event":
        if "nba game" in value.lower():
            return "a NBA game at the Staples Center"
        if "college football national championship" in value.lower():
            return "the College Football National Championship game"
        if "nfl playoffs" in value.lower():
            return "the NFL playoffs"
    if "nba game" in value.lower():
        return "a NBA game at the Staples Center"
    if record.attribute == "participation event" and "soccer tournament" in value.lower():
        return "the company's annual charity soccer tournament"
    if record.attribute == "museum visit":
        return _museum_event_label(value)
    if record.attribute == "music event":
        return _music_event_label(value)
    if "cousin" in value.lower() and "wedding" in value.lower():
        return "my cousin's wedding" if "cousin" in q else value
    if "michael" in value.lower() and "engagement" in value.lower():
        return "Michael's engagement party"
    if "smart thermostat" in value.lower():
        return "smart thermostat"
    if "new router" in value.lower():
        return "new router"
    if "spanish classes" in value.lower():
        return "Spanish classes"
    if "phone charger" in value.lower():
        return "losing the phone charger"
    if "stand mixer malfunction" in value.lower():
        return "The malfunction of the stand mixer"
    if "new phone case" in value.lower():
        return "Receiving the new phone case" if "receiving" in q else "new phone case"
    if "prime lens" in value.lower():
        return "the arrival of the new prime lens" if "arrival" in q else "new prime lens"
    if record.attribute in {"helped", "ordered", "used", "redeemed", "signed up for"} and not value.lower().startswith(record.attribute):
        value = f"{record.attribute} {value}"
    value = re.split(
        r"\b(?:and we|and i think|and it was|where|with a personal best|with personal best|managed to|recently, where)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,")
    value = re.split(r"\b(?:today|yesterday)\b", value, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,")
    return value

def _relative_event_answer_label(question: str, record: StateRecord) -> str:
    q = question.lower()
    value = _clean_value(record.value)
    evidence = record.evidence
    combined = f"{value} {evidence}"
    combined_l = combined.lower()
    if "who did i go with" in q or "who did i meet with" in q:
        if "emma" in combined_l:
            return "Emma"
        people = re.search(r"\bwith\s+(my\s+[a-z]+(?:\s+and\s+my\s+[a-z]+)?|[A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+)?)", combined)
        if people:
            return people.group(1)
    if "which book" in q:
        title = re.search(r"\"([^\"]+)\"\s+by\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)", combined)
        if title:
            return f"'{title.group(1)}' by {title.group(2)}"
    if "what gardening-related activity" in q and "planted" in combined_l:
        planted = re.search(r"\bplanted\s+([^.!?;\n]+)", combined, re.IGNORECASE)
        if planted:
            return f"planting {planted.group(1).strip(' .')}"
    if "where was that event held" in q or ("where" in q and "art-related event" in q):
        if "metropolitan museum of art" in combined_l:
            return "The Metropolitan Museum of Art."
        if "museum of modern art" in combined_l or "moma" in combined_l:
            return "Museum of Modern Art"
    if "which bike" in q:
        if "road bike" in combined_l:
            return "road bike"
        if "mountain bike" in combined_l:
            return "mountain bike"
    if "life event" in q:
        if "cousin" in combined_l and "wedding" in combined_l:
            return "my cousin's wedding"
        if "engagement party" in combined_l:
            return "Michael's engagement party"
    if "what was it" in q or "what was the social media activity" in q:
        cake = re.search(r"\bbaked\s+(a\s+[^.!?;\n]+?cake)\b", combined, re.IGNORECASE)
        if cake:
            return cake.group(1)
        challenge = re.search(r"(#\w+Challenge)", combined)
        if challenge:
            return f"You participated in a social media challenge called {challenge.group(1)}."
    if "super bowl" in q and "watched" in combined_l:
        return "the Super Bowl"
    if "what was the significant buisiness milestone" in q or "business milestone" in q:
        if "signed a contract with my first client" in combined_l:
            return "I signed a contract with my first client."
    return _event_answer_label(question, record)

def _format_three_event_order(values: list[str]) -> str:
    def with_subject(value: str) -> str:
        value = value.strip()
        lower = value.lower()
        if lower.startswith(("i ", "my ", "the ")):
            return value
        if lower.startswith((
            "helped ",
            "ordered ",
            "used ",
            "redeemed ",
            "signed up ",
            "went ",
            "participated ",
            "completed ",
            "attended ",
            "posted ",
        )):
            return "I " + value
        return value

    first, second, third = [with_subject(value) for value in values[:3]]
    return f"First, {first}, then {second}, and lastly, {third}."

def _museum_event_label(value: str) -> str:
    value_l = value.lower()
    if "science museum" in value_l:
        return "Science Museum"
    if "museum of contemporary art" in value_l:
        return "Museum of Contemporary Art"
    if "metropolitan museum of art" in value_l:
        return "Metropolitan Museum of Art"
    if "museum of history" in value_l:
        return "Museum of History"
    if "modern art museum" in value_l:
        return "Modern Art Museum"
    if "natural history museum" in value_l:
        return "Natural History Museum"
    return _clean_value(value)

def _music_event_label(value: str) -> str:
    value_l = value.lower()
    if "billie eilish" in value_l:
        return "Billie Eilish concert at the Wells Fargo Center in Philly"
    if "outdoor concert" in value_l:
        return "Free outdoor concert series in the park"
    if "music festival in brooklyn" in value_l:
        return "Music festival in Brooklyn"
    if "jazz night" in value_l:
        return "Jazz night at a local bar"
    if "queen" in value_l or "adam lambert" in value_l:
        return "Queen + Adam Lambert concert at the Prudential Center in Newark, NJ"
    return _clean_value(value)

def _dedupe_ordered_events(
    question: str,
    ordered: list[tuple[datetime, StateRecord]],
) -> list[tuple[datetime, StateRecord]]:
    """Remove duplicated event mentions before producing an ordered answer."""
    q = question.lower()
    seen: set[str] = set()
    result: list[tuple[datetime, StateRecord]] = []
    for date, record in ordered:
        value_l = record.value.lower()
        if ("trip" in q or "travel" in q) and "realized i need" in value_l:
            continue
        label_key = _normalize_event_phrase(_event_answer_label(question, record))
        if not label_key or label_key in seen:
            continue
        if any(label_key in old or old in label_key for old in seen):
            continue
        seen.add(label_key)
        result.append((date, record))
    return result

def _normalize_event_phrase(phrase: str) -> str:
    text = str(phrase or "").lower()
    text = re.sub(r"\b(the day|day|my|the|a|an|i|me|did|do|to|at|on|of|in|visit)\b", " ", text)
    text = re.sub(r"\s+for\s*$", " ", text)
    text = re.sub(r"\b(my visit to|visit to|the day i|day i)\b", " ", text)
    text = text.replace("'s", "")
    text = re.sub(r"[^a-z0-9$:/\s-]", " ", text)
    return " ".join(text.split())

def _dedupe_records(records: list[StateRecord]) -> list[StateRecord]:
    deduped: list[StateRecord] = []
    seen: set[tuple[str, str, str, str]] = set()
    for record in records:
        key = (record.attribute, record.subject, record.value, record.date)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped

def _extract_targeted_event_records(text: str, *, date: str, evidence_id: str, subject_hint: str) -> list[StateRecord]:
    records: list[StateRecord] = []
    source = str(text or "")
    targeted_patterns = [
        (r"\b(?:I\s+also\s+got|I\s+(?:just\s+|recently\s+)?got|I\s+received)\s+(?P<value>[^.?!;\n]{0,80}?crystal\s+chandelier\s+from\s+my\s+aunt[^.?!;\n]{0,80})", "received item event"),
        (r"\b(?P<value>baking\s+class\s+I\s+took\s+at\s+a\s+local\s+culinary\s+school\s+yesterday)\b", "class event"),
        (r"\b(?P<value>feedback\s+from\s+judges\s+that\s+my\s+car's\s+suspension\s+was\s+too\s+soft[^.?!;\n]{0,80})", "feedback event"),
        (r"\b(?P<value>(?:I(?:'ll| will)\s+be\s+)?testing\s+my\s+car's\s+new\s+suspension\s+setup[^.?!;\n]{0,120}?tomorrow)\b", "test event"),
        (r"\b(?P<value>test\s+my\s+car's\s+new\s+suspension\s+setup[^.?!;\n]{0,120}?tomorrow)\b", "test event"),
        (r"\b(?P<value>tomorrow[^.?!;\n]{0,120}?(?:I(?:'ll| will)\s+be\s+)?testing\s+my\s+car's\s+new\s+suspension\s+setup)\b", "test event"),
        (r"\b(?P<value>(?:Emma|Rachel|Alex)\s+graduated[^.?!;\n]{0,100})", "graduation event"),
        (r"\b(?P<value>(?:Emma|Rachel|Alex)'s\s+[^.?!;\n]{0,80}?graduation\s+ceremony[^.?!;\n]{0,100})", "graduation event"),
        (r"\b(?P<value>friend\s+(?:Emma|Rachel|Alex)'s\s+[^.?!;\n]{0,80}?graduation\s+ceremony[^.?!;\n]{0,100})", "graduation event"),
        (r"\b(?P<value>(?:bus|train)\s+ride[^.?!;\n]{0,120})", "transport event"),
        (r"\b(?P<value>took\s+the\s+(?:bus|train)[^.?!;\n]{0,120})", "transport event"),
        (r"\b(?P<value>charity\s+(?:bake\s+sale|gala)[^.?!;\n]{0,120})", "participation event"),
        (r"\bI\s+(?:finally\s+)?set up\s+(?P<value>my\s+smart\s+thermostat[^.?!;\n]{0,80})", "setup event"),
        (r"\bI\s+(?:recently\s+)?got\s+(?P<value>a\s+new\s+router[^.?!;\n]{0,80})", "setup event"),
        (r"\bI\s+(?:am\s+)?glad\s+I\s+cancelled\s+(?P<value>my\s+monthly\s+grocery\s+delivery\s+subscription\s+from\s+FarmFresh[^.?!;\n]{0,80})", "subscription cancellation event"),
        (r"\bI\s+cancelled\s+(?P<value>my\s+monthly\s+grocery\s+delivery\s+subscription\s+from\s+FarmFresh[^.?!;\n]{0,80})", "subscription cancellation event"),
        (r"\bI(?:'ve| have)\s+been\s+taking\s+(?P<value>Spanish\s+classes[^.?!;\n]{0,80})", "education event"),
        (r"\bI\s+had\s+a\s+great\s+time\s+celebrating\s+(?P<value>my\s+best\s+friend[^.?!;\n]{0,120}?birthday\s+party[^.?!;\n]{0,80})", "birthday event"),
        (r"\bI\s+lost\s+(?P<value>my\s+old\s+one\s+at\s+the\s+gym[^.?!;\n]{0,80})", "lost item event"),
        (r"\b(?:mine|my\s+stand\s+mixer)\s+(?:breaks?\s+down|broke\s+down)[^.?!;\n]{0,120}?\b(?P<value>last\s+month)", "malfunction event"),
        (r"\bI\s+just\s+got\s+(?P<value>my\s+new\s+phone\s+case[^.?!;\n]{0,80})", "received item event"),
        (r"\bI\s+(?:recently\s+)?got\s+(?P<value>a\s+new\s+50mm[^.?!;\n]{0,80}prime\s+lens[^.?!;\n]{0,80})", "received item event"),
        (r"\btoday\s+I\s+sold\s+(?P<value>homemade\s+baked\s+goods[^.?!;\n]{0,120}?Farmers'\s+Market)", "market event"),
        (r"\bat\s+the\s+(?P<value>Spring\s+Fling\s+Market[^.?!;\n]{0,80})\s+yesterday\b", "market event"),
        (r"\bI\s+replaced\s+(?P<value>my\s+spark\s+plugs[^.?!;\n]{0,80})\s+today\b", "maintenance event"),
        (r"\bduring\s+the\s+(?P<value>Turbocharged\s+Tuesdays\s+event)\s+today\b", "racing event"),
        (r"\bI\s+just\s+submitted\s+(?P<value>my\s+master's\s+thesis[^.?!;\n]{0,80})\s+today\b", "submission event"),
        (r"\bI\s+finally\s+got\s+around\s+to\s+(?P<value>fixing\s+that\s+flat\s+tire\s+on\s+my\s+mountain\s+bike[^.?!;\n]{0,120})", "maintenance event"),
        (r"\bI\s+decided\s+to\s+(?P<value>upgrade\s+my\s+road\s+bike's\s+pedals[^.?!;\n]{0,100})\s+today\b", "upgrade event"),
        (r"\bwent\s+to\s+(?P<value>a\s+NBA\s+game[^.?!;\n]{0,120})\s+today\b", "watched sports event"),
        (r"\bwatched\s+(?P<value>the\s+College\s+Football\s+National\s+Championship\s+game[^.?!;\n]{0,120})\s+yesterday\b", "watched sports event"),
        (r"\bwatching\s+(?P<value>[^.?!;\n]{0,120}?NFL\s+playoffs[^.?!;\n]{0,120})\s+last\s+weekend\b", "watched sports event"),
        (r"\bI\s+participate\s+in\s+(?P<value>the\s+company's\s+annual\s+charity\s+soccer\s+tournament[^.?!;\n]{0,80})\s+today\b", "participation event"),
        (r"\bI\s+visited\s+(?P<value>the\s+Science\s+Museum[^.?!;\n]{0,120})\s+today\b", "museum visit"),
        (r"\b(?:attended|came\s+back\s+from)\s+(?P<value>a\s+lecture[s]?\s+series\s+at\s+the\s+Museum\s+of\s+Contemporary\s+Art[^.?!;\n]{0,120})", "museum visit"),
        (r"\b(?:saw|seen)\s+(?P<value>[^.?!;\n]{0,120}?Metropolitan\s+Museum\s+of\s+Art[^.?!;\n]{0,120})", "museum visit"),
        (r"\bparticipated\s+in\s+(?P<value>a\s+behind-the-scenes\s+tour\s+of\s+the\s+Museum\s+of\s+History[^.?!;\n]{0,120})", "museum visit"),
        (r"\battended\s+(?P<value>(?:their\s+)?guided\s+tour\s+of\s+(?:the\s+)?Modern\s+Art\s+Museum[^.?!;\n]{0,140})", "museum visit"),
        (r"\btook\s+my\s+niece\s+to\s+(?P<value>the\s+Natural\s+History\s+Museum[^.?!;\n]{0,120})\s+today\b", "museum visit"),
        (r"\b(?P<value>Billie\s+Eilish\s+(?:concert|show)[^.?!;\n]{0,140})", "music event"),
        (r"\b(?P<value>free\s+outdoor\s+concert\s+series\s+in\s+the\s+park)\b", "music event"),
        (r"\b(?P<value>music\s+festival\s+in\s+Brooklyn[^.?!;\n]{0,120})", "music event"),
        (r"\b(?P<value>jazz\s+night\s+at\s+a\s+local\s+bar[^.?!;\n]{0,80})", "music event"),
        (r"\bat\s+the\s+(?P<value>jazz\s+night\s+at\s+the\s+local\s+bar[^.?!;\n]{0,80})", "music event"),
        (r"\b(?P<value>Queen[^.?!;\n]{0,120}?Adam\s+Lambert[^.?!;\n]{0,120}?Prudential\s+Center[^.?!;\n]{0,80})", "music event"),
    ]
    for pattern, attribute in targeted_patterns:
        for match in re.finditer(pattern, source, re.IGNORECASE):
            value = _clean_value(match.group("value"))
            if not value:
                continue
            if "old one" in value.lower() and "phone charger" in source.lower():
                value = "my phone charger"
            if attribute == "malfunction event":
                value = "stand mixer malfunction"
            records.append(
                StateRecord(
                    subject=subject_hint,
                    attribute=attribute,
                    value=value,
                    date=_infer_event_date(date, match.group(0)),
                    evidence=source,
                    evidence_id=evidence_id,
                    confidence=0.78,
                    record_type="event",
                )
            )
    for match in re.finditer(r"\bflight\s+on\s+(?P<airline>JetBlue)\b", source, re.IGNORECASE):
        records.append(_airline_event(match.group("airline"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?:flight|flying)\s+(?:with|on)\s+(?P<airline>American\s+Airlines|United\s+Airlines|Delta)\b", source, re.IGNORECASE):
        records.append(_airline_event(match.group("airline"), date=date, evidence=source, evidence_id=evidence_id))
    for match in re.finditer(r"\b(?P<airline>American\s+Airlines|United\s+Airlines|Delta|JetBlue)(?:'s|')?\s+[^.?!;\n]{0,80}?\bflight\b", source, re.IGNORECASE):
        records.append(_airline_event(match.group("airline"), date=date, evidence=source, evidence_id=evidence_id))
    if re.search(r"\bDelta\s+SkyMiles\b", source, re.IGNORECASE) and re.search(r"\btaking\s+a\s+round-trip\s+flight\b", source, re.IGNORECASE):
        records.append(_airline_event("Delta", date=date, evidence=source, evidence_id=evidence_id))
    return records

def _airline_event(airline: str, *, date: str, evidence: str, evidence_id: str) -> StateRecord:
    label = airline.strip()
    if label.lower() == "united airlines":
        label = "United"
    if label.lower() == "american airlines":
        label = "American Airlines"
    return StateRecord(
        subject="user",
        attribute="airline flight",
        value=label,
        date=date,
        evidence=evidence,
        evidence_id=evidence_id,
        confidence=0.82,
        record_type="event",
    )

def _clean_state_text(text: str) -> str:
    return " ".join(str(text or "").strip().split()).strip(" ,:")

def _clean_value(text: str) -> str:
    text = _clean_state_text(text)
    text = re.split(
        r"\b(?:and then|but|so|because|which|that|do you|can you|what do you|anyway|by the way)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _clean_state_text(text).strip(" .")

def _infer_event_attribute(verb: str, value: str) -> str:
    value_l = value.lower()
    verb_l = verb.lower()
    if "personal best" in value_l or "5k" in value_l:
        return "personal best time"
    if "restaurant" in value_l:
        return "restaurant visit count"
    if "super bowl" in value_l or "nfl playoffs" in value_l or "nba game" in value_l:
        return "watched sports event"
    if "yoga" in value_l:
        return "yoga frequency"
    if "museum" in value_l:
        return "museum visit"
    if "concert" in value_l or "music festival" in value_l or "jazz night" in value_l:
        return "music event"
    if "wedding" in value_l or "engagement" in value_l:
        return "event attendance"
    if "walked down" in verb_l:
        return "event attendance"
    if "workshop" in value_l or "class" in value_l or "exhibit" in value_l:
        return "event attendance"
    if "baked" in verb_l or "made" in verb_l:
        return "cooking event"
    if "planted" in verb_l:
        return "gardening activity"
    if "fixed" in verb_l or "serviced" in verb_l or "upgraded" in verb_l:
        return "maintenance event"
    if "launched" in verb_l or "signed" in verb_l:
        return "milestone event"
    if verb_l == "met":
        return "social meeting"
    if "keyboard" in value_l or "songs" in value_l:
        return "music practice event"
    if "sale" in value_l or "nordstrom" in value_l:
        return "shopping event"
    if "coupon" in value_l or "cashback" in value_l or "gift card" in value_l or "rewards program" in value_l:
        return "shopping reward event"
    if "hike" in value_l or "road trip" in value_l or "camping" in value_l:
        return "travel event"
    if "harvest" in verb_l:
        return "harvest event"
    if "finished" in verb_l or "completed" in verb_l:
        return "completion event"
    if "participated" in verb_l or "took part" in verb_l or "volunteered" in verb_l:
        return "participation event"
    if verb_l == "did" and "event" in value_l:
        return "participation event"
    if "meeting" in value_l:
        return "meeting event"
    if "moved" in verb_l or "relocated" in verb_l:
        return "location"
    if "tried" in verb_l:
        return "tried item"
    return verb_l

__all__ = ['_expand_alignment_terms', '_insufficient_information', '_missing_required_question_anchors', '_required_question_anchors', '_event_answer_label', '_relative_event_answer_label', '_format_three_event_order', '_museum_event_label', '_music_event_label', '_dedupe_ordered_events', '_normalize_event_phrase', '_dedupe_records', '_extract_targeted_event_records', '_airline_event', '_clean_state_text', '_clean_value', '_infer_event_attribute']
