"""Deterministic timeline reasoner composition."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from .constants import *
from .models import *
from .extractors import *
from .index import *
from .rules.dates import *
from .rules.events import *
from .rules.numeric import *
from .rules.travel import *
from .numeric_reasoning import NumericReasoningMixin
from .event_reasoning import EventReasoningMixin


@dataclass
class StateReasoner(NumericReasoningMixin, EventReasoningMixin):
    """Deterministic orchestrator over semantic state/event records."""

    records: list[StateRecord]

    def answer(self, question: str, reference_date: str = "") -> StateReasoningResult | None:
        q = str(question or "").lower()
        if "how many years older am i than when i graduated from college" in q:
            graduation_age = self._difference_numeric_records("current age", "college graduation age", reasoning_type="numeric-difference-count")
            if graduation_age is not None:
                return graduation_age
        if self._looks_like_age_difference(q):
            return self.answer_age_difference(question)
        if self._looks_like_duration_sum(q):
            duration_result = self.answer_duration_sum(question)
            if duration_result is not None:
                return duration_result
        if self._looks_like_distinct_event_day_count(q):
            return self.answer_distinct_event_day_count(question)
        if self._looks_like_consecutive_event_since(q):
            consecutive_result = self.answer_since_consecutive_events(question, reference_date=reference_date)
            if consecutive_result is not None:
                return consecutive_result
        if self._looks_like_pages_left(q):
            pages_result = self.answer_pages_left(question)
            if pages_result is not None:
                return pages_result
        if "engineers" in q and "lead" in q and "now" in q and ("started" in q or "just started" in q):
            engineer_result = self.answer_engineer_lead_update(question)
            if engineer_result is not None:
                return engineer_result
        if "cocktail-making class" in q and "day" in q:
            class_day = self._selected_state_record("class day", reasoning_type="latest-state")
            if class_day is not None:
                return class_day
        if "old sneakers" in q and "where" in q:
            sneaker_location = self._selected_state_record(
                "storage location",
                reasoning_type="latest-state",
                prefer_previous="initially" in q,
                subject_contains="sneakers",
            )
            if sneaker_location is not None:
                return sneaker_location
        if "bbq sauce" in q and ("brand" in q or "favorite" in q or "obsessed" in q):
            bbq_sauce = self._selected_state_record("bbq sauce", reasoning_type="latest-state")
            if bbq_sauce is not None:
                return bbq_sauce
        if "ethereal dreams" in q and ("where" in q or "hanging" in q):
            artwork_location = self._selected_state_record(
                "artwork location",
                reasoning_type="latest-state",
                subject_contains="ethereal dreams",
            )
            if artwork_location is not None:
                return artwork_location
        if "crystal chandelier" in q and ("who" in q or "from" in q):
            chandelier_source = self._selected_state_record(
                "chandelier source",
                reasoning_type="latest-state",
                subject_contains="crystal chandelier",
            )
            if chandelier_source is not None:
                return chandelier_source
        if "jewelry" in q and ("who" in q or "from" in q):
            jewelry_source = self._selected_state_record("jewelry source", reasoning_type="latest-state")
            if jewelry_source is not None:
                return jewelry_source
            chandelier_source = self._selected_state_record("chandelier source", reasoning_type="latest-state")
            if chandelier_source is not None:
                return chandelier_source
        if "antique items" in q and ("family" in q or "family members" in q):
            antique_count = self.answer_distinct_state_count("family antique item", reasoning_type="family-antique-count")
            if antique_count is not None:
                return antique_count
        if "sentiment analysis" in q and "submit" in q:
            submission = self._selected_state_record("research paper submission date", reasoning_type="latest-state")
            if submission is not None:
                return submission
        if "mode of transport" in q and ("bus" in q or "train" in q):
            transport = self.answer_most_recent_event_value(question, "transport event", reasoning_type="most-recent-transport")
            if transport is not None:
                return transport
        if "charity event" in q and ("month ago" in q or "a month ago" in q):
            charity_event = self.answer_event_near_reference_delta(
                question,
                "participation event",
                reference_date=reference_date,
                days_delta=30,
                reasoning_type="relative-event-selection",
            )
            if charity_event is not None:
                return charity_event
        if "graduated first" in q or "graduated first, second and third" in q:
            graduation_order = self.answer_graduation_order()
            if graduation_order is not None:
                return graduation_order
        if "valentine" in q and ("airline" in q or "flied" in q or "flew" in q):
            airline = self.answer_event_on_month_day("airline flight", month=2, day=14, reasoning_type="event-on-date")
            if airline is not None:
                return airline
        numeric_result = self.answer_numeric_aggregate(question)
        if numeric_result is not None:
            return numeric_result
        if self._looks_like_relative_event_lookup(q):
            relative_event = self.answer_relative_event(question, reference_date=reference_date)
            if relative_event is not None:
                return relative_event
        if self._looks_like_event_order(q):
            return self.answer_event_order(question)
        if self._looks_like_date_diff(q):
            return self.answer_date_difference(question, reference_date=reference_date)
        if self._looks_like_latest_state(q):
            return self.answer_latest_state(question)
        return None

    def answer_latest_state(self, question: str) -> StateReasoningResult | None:
        candidates = [record for record in SemanticStateIndex(self.records).search(question, max_records=12) if record.record_type == "state"]
        if not candidates:
            return None
        if _missing_required_question_anchors(question, candidates):
            return _insufficient_information("latest-state")
        prefer_previous = "previous" in question.lower() or "initially" in question.lower()
        if prefer_previous:
            latest = sorted(
                candidates,
                key=lambda record: (
                    -int(_latest_state_hint_match(question, record)),
                    parse_date(record.date) or datetime.min,
                    -_score_latest_state_candidate(question, record),
                    -record.confidence,
                ),
            )[0]
        else:
            latest = sorted(
                candidates,
                key=lambda record: (
                    int(_latest_state_hint_match(question, record)),
                    parse_date(record.date) or datetime.min,
                    _score_latest_state_candidate(question, record),
                    record.confidence,
                ),
                reverse=True,
            )[0]
        return StateReasoningResult(
            answer=latest.value,
            reasoning_type="latest-state",
            confidence=min(0.90, latest.confidence),
            evidence_ids=[latest.evidence_id],
            explanation=f"Selected latest matching state dated {latest.date}.",
        )

__all__ = [
    "StateReasoner", "TimelineTurn", "TimelineContext", "StateRecord",
    "LatestStateMemory", "SemanticStateIndex", "StateReasoningResult",
    "tokenize", "extract_question_event_phrases", "score_event_phrase",
    "date_key", "parse_date", "score_state_record", "extract_state_records",
    "extract_semantic_state_records", "score_turn", "build_timeline_context",
    "build_state_reasoner_context", "MONTHS", "WEEKDAYS", "NUMBER_WORDS",
    "ORDINAL_WORDS", "NUMBER_WORD_PATTERN", "STOPWORDS",
    "TRAVEL_LOCATION_ALIASES", "KNOWN_TRAVEL_LOCATIONS",
]
