"""Timeline and semantic-state data models."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from .rules.dates import date_key

@dataclass(frozen=True)
class StateRecord:
    """A lightweight extracted state fact with dated evidence."""

    subject: str
    attribute: str
    value: str
    date: str
    evidence: str
    evidence_id: str = ""
    confidence: float = 0.5
    record_type: str = "state"

    @property
    def key(self) -> tuple[str, str]:
        return (self.subject.lower(), self.attribute.lower())

@dataclass
class LatestStateMemory:
    """Small latest-value index over extracted state records."""

    records: list[StateRecord]

    def latest_by_key(self) -> dict[tuple[str, str], StateRecord]:
        latest: dict[tuple[str, str], StateRecord] = {}
        for record in self.records:
            current = latest.get(record.key)
            if current is None or date_key(record.date) >= date_key(current.date):
                latest[record.key] = record
        return latest

    def format_for_prompt(self, max_records: int = 12) -> str:
        latest = sorted(
            self.latest_by_key().values(),
            key=lambda record: (date_key(record.date), record.confidence),
            reverse=True,
        )[:max_records]
        if not latest:
            return ""
        lines = ["## Latest State Memory", ""]
        for record in latest:
            lines.append(
                f"- [{record.date}] {record.record_type}: {record.subject} / {record.attribute} = "
                f"{record.value} (conf={record.confidence:.2f}; evidence={record.evidence_id})"
            )
        return "\n".join(lines)

@dataclass(frozen=True)
class StateReasoningResult:
    """A deterministic answer candidate derived from state/event records."""

    answer: str
    reasoning_type: str
    confidence: float
    evidence_ids: list[str]
    explanation: str

@dataclass(frozen=True)
class TimelineTurn:
    """One dated turn selected for timeline memory construction."""

    session_id: str
    session_date: str
    turn_index: int
    role: str
    content: str
    relevance: float

@dataclass(frozen=True)
class TimelineContext:
    """Formatted timeline context plus debug metadata."""

    text: str
    selected_turns: list[TimelineTurn]
    latest_candidates: list[TimelineTurn]

    @property
    def selected_count(self) -> int:
        return len(self.selected_turns)

@dataclass
class SemanticStateIndex:
    """Question-aware index over extracted state and event records."""

    records: list[StateRecord]

    def search(self, question: str, max_records: int = 16) -> list[StateRecord]:
        from .index import score_state_record, tokenize

        q_terms = set(tokenize(question))
        scored = [
            (score_state_record(q_terms, record), record)
            for record in self.records
        ]
        ranked = sorted(
            [item for item in scored if item[0] > 0],
            key=lambda item: (item[0], date_key(item[1].date), item[1].confidence),
            reverse=True,
        )
        return [record for _, record in ranked[:max_records]]

    def format_for_prompt(self, question: str, max_records: int = 16) -> str:
        records = self.search(question, max_records=max_records)
        if not records:
            return ""
        lines = ["## Semantic State/Event Memory", ""]
        for record in records:
            lines.append(
                f"- [{record.date}] {record.record_type}: {record.subject} / "
                f"{record.attribute} = {record.value} "
                f"(conf={record.confidence:.2f}; evidence={record.evidence_id})"
            )
        return "\n".join(lines)

__all__ = ['LatestStateMemory', 'SemanticStateIndex', 'StateReasoningResult', 'StateRecord', 'TimelineContext', 'TimelineTurn']
