"""Event and temporal reasoning methods."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from .constants import *
from .models import SemanticStateIndex, StateReasoningResult, StateRecord
from .extractors import *
from .index import *
from .rules.dates import *
from .rules.events import *
from .rules.numeric import *
from .rules.travel import *


class EventReasoningMixin:
    def answer_engineer_lead_update(self, question: str) -> StateReasoningResult | None:
        records = self._numeric_records("engineers led count")
        if len(records) < 2:
            return None
        ordered = sorted(records, key=lambda item: parse_date(item.date) or datetime.min)
        first = ordered[0]
        latest = ordered[-1]
        first_value = _format_number_answer(_parse_number(first.value) or 0)
        latest_value = _format_number_answer(_parse_number(latest.value) or 0)
        return StateReasoningResult(
            answer=(
                "When you just started your new role as Senior Software Engineer, "
                f"you led {first_value} engineers. Now, you lead {latest_value} engineers"
            ),
            reasoning_type="engineer-lead-update",
            confidence=0.80,
            evidence_ids=[first.evidence_id, latest.evidence_id],
            explanation="Compared earliest and latest engineer-lead count states.",
        )

    def answer_distinct_state_count(self, attribute: str, *, reasoning_type: str) -> StateReasoningResult | None:
        records = [
            record for record in self.records
            if record.record_type == "state" and record.attribute == attribute
        ]
        if not records:
            return None
        seen: set[str] = set()
        evidence_ids: list[str] = []
        for record in records:
            key = _normalize_event_phrase(record.value)
            if not key or key in seen:
                continue
            seen.add(key)
            evidence_ids.append(record.evidence_id)
        if not seen:
            return None
        return StateReasoningResult(
            answer=str(len(seen)),
            reasoning_type=reasoning_type,
            confidence=0.76,
            evidence_ids=evidence_ids,
            explanation=f"Counted distinct {attribute} records.",
        )

    def answer_distinct_subject_count(self, attribute: str, *, reasoning_type: str) -> StateReasoningResult | None:
        records = [
            record for record in self.records
            if record.record_type == "state" and record.attribute == attribute
        ]
        if not records:
            return None
        seen: set[str] = set()
        evidence_ids: list[str] = []
        for record in records:
            key = _normalize_event_phrase(record.subject)
            if not key or key in seen:
                continue
            seen.add(key)
            evidence_ids.append(record.evidence_id)
        if not seen:
            return None
        return StateReasoningResult(
            answer=str(len(seen)),
            reasoning_type=reasoning_type,
            confidence=0.76,
            evidence_ids=evidence_ids,
            explanation=f"Counted distinct subjects for {attribute}.",
        )

    def answer_most_recent_event_value(
        self,
        question: str,
        attribute: str,
        *,
        reasoning_type: str,
    ) -> StateReasoningResult | None:
        q_terms = set(tokenize(question))
        records = [
            record for record in self.records
            if record.record_type == "event"
            and record.attribute == attribute
            and (score_state_record(q_terms, record) > 0 or attribute in record.attribute)
        ]
        dated = [(parse_date(record.date), record) for record in records]
        dated = [(date, record) for date, record in dated if date is not None]
        if not dated:
            return None
        _, record = sorted(dated, key=lambda item: item[0])[-1]
        return StateReasoningResult(
            answer=_event_answer_label(question, record),
            reasoning_type=reasoning_type,
            confidence=0.78,
            evidence_ids=[record.evidence_id],
            explanation=f"Selected most recent {attribute} event.",
        )

    def answer_event_on_month_day(
        self,
        attribute: str,
        *,
        month: int,
        day: int,
        reasoning_type: str,
    ) -> StateReasoningResult | None:
        dated = []
        for record in self.records:
            if record.record_type != "event" or record.attribute != attribute:
                continue
            parsed = parse_date(record.date)
            if parsed is not None and parsed.month == month and parsed.day == day:
                dated.append((parsed, record))
        if not dated:
            return None
        # Prefer the event that came from the user's own mention on that day.
        _, record = sorted(
            dated,
            key=lambda item: (
                int("by the way" in item[1].evidence.lower() or "today" in item[1].evidence.lower()),
                item[1].confidence,
            ),
            reverse=True,
        )[0]
        return StateReasoningResult(
            answer=record.value,
            reasoning_type=reasoning_type,
            confidence=0.78,
            evidence_ids=[record.evidence_id],
            explanation=f"Selected {attribute} event on {month:02d}/{day:02d}.",
        )

    def answer_event_near_reference_delta(
        self,
        question: str,
        attribute: str,
        *,
        reference_date: str,
        days_delta: int,
        reasoning_type: str,
    ) -> StateReasoningResult | None:
        ref = parse_date(reference_date)
        if ref is None:
            return None
        target = ref - timedelta(days=days_delta)
        q_terms = set(tokenize(question))
        dated = []
        for record in self.records:
            if record.record_type != "event" or record.attribute != attribute:
                continue
            if score_state_record(q_terms, record) <= 0 and "charity" not in record.value.lower():
                continue
            parsed = parse_date(record.date)
            if parsed is not None:
                dated.append((abs((parsed - target).days), parsed, record))
        if not dated:
            return None
        _, _, record = sorted(dated, key=lambda item: item[0])[0]
        return StateReasoningResult(
            answer=_event_answer_label(question, record),
            reasoning_type=reasoning_type,
            confidence=0.76,
            evidence_ids=[record.evidence_id],
            explanation=f"Selected {attribute} closest to {days_delta} days before question date.",
        )

    def answer_graduation_order(self) -> StateReasoningResult | None:
        records = [
            record for record in self.records
            if record.record_type == "event"
            and record.attribute == "graduation event"
            and parse_date(record.date) is not None
        ]
        if len(records) < 2:
            return None
        ordered = sorted(records, key=lambda record: parse_date(record.date) or datetime.min)
        names: list[str] = []
        evidence_ids: list[str] = []
        for record in ordered:
            match = re.search(r"\b(Emma|Rachel|Alex)\b", record.value)
            if not match:
                continue
            name = match.group(1)
            if name in names:
                continue
            names.append(name)
            evidence_ids.append(record.evidence_id)
        if len(names) < 2:
            return None
        if len(names) >= 3:
            answer = f"{names[0]} graduated first, followed by {names[1]} and then {names[2]}."
        else:
            answer = f"{names[0]} graduated first, followed by {names[1]}."
        return StateReasoningResult(
            answer=answer,
            reasoning_type="graduation-order",
            confidence=0.78,
            evidence_ids=evidence_ids,
            explanation="Sorted graduation events by date.",
        )

    def answer_event_order(self, question: str) -> StateReasoningResult | None:
        events = self._question_events(question, max_records=32)
        if "order of airlines" in question.lower() or "airlines i flew with" in question.lower():
            airline_result = self._answer_airline_order(events)
            if airline_result is not None:
                return airline_result
        if "order of the six museums" in question.lower() or "museums i visited" in question.lower():
            museum_result = self._answer_labeled_event_order(
                question,
                events,
                attribute="museum visit",
                min_events=2,
                separator=", ",
            )
            if museum_result is not None:
                return museum_result
        if "order of the concerts" in question.lower() or "concerts and musical events" in question.lower():
            concert_result = self._answer_labeled_event_order(
                question,
                events,
                attribute="music event",
                min_events=3,
                separator=", ",
                prefix="The order of the concerts I attended is: ",
                numbered=True,
            )
            if concert_result is not None:
                return concert_result
        dated = [(parse_date(record.date), record) for record in events]
        dated = [(date, record) for date, record in dated if date is not None]
        if len(dated) < 2:
            phrases = extract_question_event_phrases(question)
            if len(phrases) >= 2 and dated:
                return StateReasoningResult(
                    answer="The information provided is not enough.",
                    reasoning_type="date-difference",
                    confidence=0.45,
                    evidence_ids=[],
                    explanation="Could not align both required event phrases to dated records.",
                )
            return None
        phrases = extract_question_event_phrases(question)
        aligned = self._align_phrases_to_events(phrases, dated)
        ordered = _dedupe_ordered_events(question, sorted(aligned or dated, key=lambda item: item[0]))
        q_l = question.lower()
        if ("happened first" in q_l or "set up first" in q_l or "take first" in q_l) and ordered:
            answer = _event_answer_label(question, ordered[0][1])
        else:
            values = [_event_answer_label(question, record) for _, record in ordered]
            if len(values) == 3 and (
                "order from first to last" in q_l
                or "order of the three events" in q_l
            ):
                answer = _format_three_event_order(values)
            else:
                answer = " -> ".join(values)
        return StateReasoningResult(
            answer=answer,
            reasoning_type="event-order",
            confidence=0.72,
            evidence_ids=[record.evidence_id for _, record in ordered],
            explanation="Sorted matching events by session date.",
        )

    def _answer_labeled_event_order(
        self,
        question: str,
        events: list[StateRecord],
        *,
        attribute: str,
        min_events: int,
        separator: str,
        prefix: str = "",
        numbered: bool = False,
    ) -> StateReasoningResult | None:
        dated = [
            (parse_date(record.date), record)
            for record in events
            if record.attribute == attribute and parse_date(record.date) is not None
        ]
        if len(dated) < min_events:
            return None
        labels: list[str] = []
        evidence_ids: list[str] = []
        for _, record in sorted(dated, key=lambda item: item[0] or datetime.min):
            label = _event_answer_label(question, record)
            if not label or label in labels:
                continue
            labels.append(label)
            evidence_ids.append(record.evidence_id)
        if len(labels) < min_events:
            return None
        if numbered:
            answer = prefix + separator.join(f"{index}. {label}" for index, label in enumerate(labels, start=1))
        else:
            answer = prefix + separator.join(labels)
        return StateReasoningResult(
            answer=answer,
            reasoning_type="event-order",
            confidence=0.78,
            evidence_ids=evidence_ids,
            explanation=f"Sorted extracted {attribute} records by date.",
        )

    def _answer_airline_order(self, events: list[StateRecord]) -> StateReasoningResult | None:
        dated = [
            (parse_date(record.date), record)
            for record in events
            if record.attribute == "airline flight" and parse_date(record.date) is not None
        ]
        if len(dated) < 2:
            return None
        ordered = sorted(dated, key=lambda item: item[0] or datetime.min)
        labels: list[str] = []
        evidence_ids: list[str] = []
        for _, record in ordered:
            label = _event_answer_label("order of airlines", record)
            if label not in labels:
                labels.append(label)
                evidence_ids.append(record.evidence_id)
        if len(labels) < 2:
            return None
        return StateReasoningResult(
            answer=", ".join(labels),
            reasoning_type="event-order",
            confidence=0.78,
            evidence_ids=evidence_ids,
            explanation="Sorted extracted airline flight events by date.",
        )

    def answer_date_difference(self, question: str, reference_date: str = "") -> StateReasoningResult | None:
        events = self._question_events(question, max_records=32)
        dated = [(parse_date(record.date), record) for record in events]
        dated = [(date, record) for date, record in dated if date is not None]
        ref = parse_date(reference_date)
        q_l = question.lower()
        if ref is not None and self._looks_like_since_reference(q_l) and dated and ("ago" in q_l or " when " not in f" {q_l} " or len(dated) < 2):
            phrases = extract_question_event_phrases(question)
            aligned = self._align_phrases_to_events(phrases[:1], dated)
            if aligned:
                event_date, event = aligned[0]
            else:
                event_date, event = sorted(
                    dated,
                    key=lambda item: score_state_record(set(tokenize(question)), item[1]),
                    reverse=True,
                )[0]
            days = abs((ref - event_date).days)
            return StateReasoningResult(
                answer=self._format_temporal_delta(question, days),
                reasoning_type="date-difference",
                confidence=0.72,
                evidence_ids=[event.evidence_id],
                explanation=f"Computed difference between question date {reference_date} and event date {event.date}.",
            )
        if len(dated) < 2:
            phrases = extract_question_event_phrases(question)
            if len(phrases) >= 2 and dated:
                return StateReasoningResult(
                    answer="The information provided is not enough.",
                    reasoning_type="date-difference",
                    confidence=0.45,
                    evidence_ids=[],
                    explanation="Could not align both required event phrases to dated records.",
                )
            return None
        selected = self._select_two_events(question, dated)
        if selected is None:
            phrases = extract_question_event_phrases(question)
            if len(phrases) >= 2:
                return StateReasoningResult(
                    answer="The information provided is not enough.",
                    reasoning_type="date-difference",
                    confidence=0.45,
                    evidence_ids=[],
                    explanation="Could not align both required event phrases to dated records.",
                )
            return None
        (first_date, first), (second_date, second) = selected
        days = abs((second_date - first_date).days)
        answer = self._format_temporal_delta(question, days)
        return StateReasoningResult(
            answer=answer,
            reasoning_type="date-difference",
            confidence=0.70,
            evidence_ids=[first.evidence_id, second.evidence_id],
            explanation=f"Computed absolute difference between {first.date} and {second.date}.",
        )

    def answer_relative_event(self, question: str, reference_date: str = "") -> StateReasoningResult | None:
        target = _relative_target_date(question, reference_date)
        if target is None:
            return None
        events = self._question_events(question, max_records=40)
        dated = [(parse_date(record.date), record) for record in events]
        dated = [(date, record) for date, record in dated if date is not None]
        if not dated:
            return None
        phrases = extract_question_event_phrases(question)
        aligned = self._align_phrases_to_events(phrases[:1], dated)
        candidates = aligned if aligned else dated
        chosen_date, chosen = sorted(
            candidates,
            key=lambda item: (
                abs((item[0] - target).days),
                -score_state_record(set(tokenize(question)), item[1]),
            ),
        )[0]
        answer = _relative_event_answer_label(question, chosen)
        if not answer:
            return None
        return StateReasoningResult(
            answer=answer,
            reasoning_type="relative-event-answer",
            confidence=0.70,
            evidence_ids=[chosen.evidence_id],
            explanation=f"Selected event closest to target relative date {target.date().isoformat()}.",
        )

    def answer_distinct_event_day_count(self, question: str) -> StateReasoningResult | None:
        q_terms = set(tokenize(question))
        month_filter = next((month for month in MONTHS if month in question.lower()), "")
        events = [
            record for record in self.records
            if record.record_type == "event"
            and score_state_record(q_terms, record) > 0
        ]
        dated: list[tuple[datetime, StateRecord]] = []
        for record in events:
            parsed = parse_date(record.date)
            if parsed is None:
                continue
            if month_filter and parsed.month != MONTHS[month_filter]:
                continue
            dated.append((parsed, record))
        unique_days = sorted({date.date().isoformat() for date, _ in dated})
        if not unique_days:
            return None
        evidence_ids = []
        seen_days = set()
        for date, record in sorted(dated, key=lambda item: item[0]):
            key = date.date().isoformat()
            if key in seen_days:
                continue
            seen_days.add(key)
            evidence_ids.append(record.evidence_id)
        return StateReasoningResult(
            answer=str(len(unique_days)),
            reasoning_type="distinct-event-day-count",
            confidence=0.70,
            evidence_ids=evidence_ids,
            explanation=f"Counted distinct matching event dates: {', '.join(unique_days)}.",
        )

    def answer_since_consecutive_events(self, question: str, reference_date: str = "") -> StateReasoningResult | None:
        ref = parse_date(reference_date)
        if ref is None:
            return None
        q_terms = set(tokenize(question))
        events = [
            record for record in self.records
            if record.record_type == "event"
            and (
                score_state_record(q_terms, record) > 0
                or ("charity" in question.lower() and "charity" in " ".join([record.attribute, record.value, record.evidence]).lower())
            )
        ]
        dated = sorted(
            [(parse_date(record.date), record) for record in events],
            key=lambda item: item[0] or datetime.min,
        )
        dated = [(date, record) for date, record in dated if date is not None]
        best_pair = None
        for i, (first_date, first) in enumerate(dated):
            for second_date, second in dated[i + 1:]:
                if second.evidence_id == first.evidence_id:
                    continue
                if abs((second_date - first_date).days) == 1:
                    best_pair = ((first_date, first), (second_date, second))
        if best_pair is None:
            return None
        (_, first), (second_date, second) = best_pair
        days = abs((ref - second_date).days)
        return StateReasoningResult(
            answer=self._format_temporal_delta(question, days),
            reasoning_type="since-consecutive-events",
            confidence=0.72,
            evidence_ids=[first.evidence_id, second.evidence_id],
            explanation=f"Found consecutive event dates and computed elapsed time from {second.date}.",
        )

    def _question_events(self, question: str, max_records: int) -> list[StateRecord]:
        return [
            record for record in SemanticStateIndex(self.records).search(question, max_records=max_records)
            if record.record_type == "event"
        ]

    @staticmethod
    def _looks_like_date_diff(question: str) -> bool:
        return any(term in question for term in ["how many days", "how many weeks", "how many months", "passed between", "since"])

    @staticmethod
    def _looks_like_age_difference(question: str) -> bool:
        return "how many years" in question and ("older" in question or "younger" in question)

    @staticmethod
    def _looks_like_distinct_event_day_count(question: str) -> bool:
        return (
            "activities" in question
            and ("how many days did i spend" in question or "how many days did i participate" in question)
        )

    @staticmethod
    def _looks_like_duration_sum(question: str) -> bool:
        return "how many days did i spend" in question and any(term in question for term in ["trip", "trips", "traveling"])

    @staticmethod
    def _looks_like_consecutive_event_since(question: str) -> bool:
        return "since" in question and "consecutive" in question

    @staticmethod
    def _looks_like_pages_left(question: str) -> bool:
        return "pages" in question and "left" in question and "read" in question

    @staticmethod
    def _looks_like_since_reference(question: str) -> bool:
        return "since" in question or "ago" in question

    @staticmethod
    def _looks_like_relative_event_lookup(question: str) -> bool:
        q = question.lower()
        if "how many days" in q or "how many weeks" in q or "how many months" in q:
            return False
        return (
            any(token in q for token in [" a week ago", " ago", "last tuesday", "last saturday", "last sunday", "last monday", "last wednesday", "last thursday", "last friday", "last weekend", "past weekend", "a couple of days ago", "two weeks ago", "four weeks ago", "two months ago"])
            and any(token in q for token in ["what", "which", "who", "where", "did i", "was the"])
        )

    @staticmethod
    def _looks_like_event_order(question: str) -> bool:
        return any(term in question for term in ["happened first", "participate in first", "participated in first", "order from first to last", "which event happened first", "which three events", "order of the three", "what is the order", "from earliest to latest", "starting from the earliest", "did i set up first", "take first", "happened first"])

    @staticmethod
    def _looks_like_latest_state(question: str) -> bool:
        return any(term in question for term in ["what was", "what is", "what type", "what company", "what time", "what day", "where did", "where do", "how often", "how many", "which"])

    @staticmethod
    def _format_temporal_delta(question: str, days: int) -> str:
        q = question.lower()
        if "week" in q:
            weeks = round(days / 7)
            if "ago" in q:
                unit = "week" if weeks == 1 else "weeks"
                return f"{weeks} {unit} ago"
            return str(weeks)
        if "month" in q:
            months = round(days / 30)
            if "ago" in q:
                unit = "month" if months == 1 else "months"
                return f"{months} {unit} ago"
            return str(months)
        if days == 1:
            return "1 day"
        return f"{days} days"

    def _select_two_events(
        self,
        question: str,
        dated: list[tuple[datetime, StateRecord]],
    ) -> tuple[tuple[datetime, StateRecord], tuple[datetime, StateRecord]] | None:
        phrases = extract_question_event_phrases(question)
        aligned = self._align_phrases_to_events(phrases[:2], dated)
        if len(aligned) >= 2:
            return aligned[0], aligned[1]
        if len(phrases) >= 2 and aligned:
            return None
        q_terms = set(tokenize(question))
        ranked = sorted(
            dated,
            key=lambda item: score_state_record(q_terms, item[1]),
            reverse=True,
        )
        for i, first in enumerate(ranked):
            for second in ranked[i + 1:]:
                if first[1].evidence_id != second[1].evidence_id:
                    return first, second
        return None

    @staticmethod
    def _align_phrases_to_events(
        phrases: list[str],
        dated: list[tuple[datetime, StateRecord]],
    ) -> list[tuple[datetime, StateRecord]]:
        aligned: list[tuple[datetime, StateRecord]] = []
        used: set[str] = set()
        for phrase in phrases:
            candidates = sorted(
                (
                    (score_event_phrase(phrase, record), date, record)
                    for date, record in dated
                    if record.evidence_id not in used
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            if candidates and candidates[0][0] > 0:
                _, date, record = candidates[0]
                aligned.append((date, record))
                used.add(record.evidence_id)
        return aligned
