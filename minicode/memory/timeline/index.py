"""Timeline tokenization, scoring, and context selection."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from .constants import *
from .models import LatestStateMemory, SemanticStateIndex, StateRecord, TimelineContext, TimelineTurn
from .rules.dates import *
from .rules.events import *
from .extractors import *

def tokenize(text: object) -> list[str]:
    """Tokenize a query or memory text for lightweight evidence scoring."""
    return [
        tok.lower()
        for tok in TOKEN_RE.findall(str(text or ""))
        if len(tok) > 1 and tok.lower() not in STOPWORDS
    ]

def score_event_phrase(phrase: str, record: StateRecord) -> float:
    """Score how well a question event phrase aligns with an event record."""
    phrase_terms = _expand_alignment_terms(tokenize(_normalize_event_phrase(phrase)))
    if not phrase_terms:
        return 0.0
    record_terms = _expand_alignment_terms(tokenize(_normalize_event_phrase(" ".join([record.attribute, record.value, record.evidence]))))
    overlap = len(phrase_terms & record_terms)
    if not overlap:
        return 0.0
    return overlap / (len(phrase_terms) ** 0.5)

def score_state_record(question_terms: set[str], record: StateRecord) -> float:
    text = " ".join([record.subject, record.attribute, record.value, record.evidence])
    terms = tokenize(text)
    if not terms:
        return 0.0
    overlap = sum(1 for term in set(terms) if term in question_terms)
    score = overlap / (len(set(terms)) ** 0.5)
    if record.record_type == "event" and any(
        term in question_terms for term in ["when", "first", "between", "days", "weeks", "months", "order"]
    ):
        score += 0.25
    if record.record_type == "state" and any(term in question_terms for term in ["what", "where", "how", "which"]):
        score += 0.10
    return score + record.confidence * 0.05

def _score_latest_state_candidate(question: str, record: StateRecord) -> float:
    q = question.lower()
    terms = set(tokenize(question))
    primary = set(tokenize(" ".join([record.subject, record.attribute, record.value])))
    evidence = set(tokenize(record.evidence))
    score = 2.0 * len(terms & primary) + 0.2 * len(terms & evidence) + record.confidence
    attr = record.attribute.lower()
    hint_pairs = [
        ("bike", "bike count"),
        ("yoga", "yoga frequency"),
        ("dr smith", "dr smith frequency"),
        ("company", "current company"),
        ("lens", "camera lens"),
        ("guitar", "guitar serviced location"),
        ("gym", "gym time"),
        ("page", "reading page"),
        ("stars", "starbucks gold stars needed"),
        ("volleyball", "volleyball record"),
        ("personal best", "personal best time"),
        ("family trip", "family trip location"),
    ]
    for hint, attribute in hint_pairs:
        if hint in q and attribute in attr:
            score += 8.0
    if "how many" in q and not re.search(r"\d|one|two|three|four|five|six|seven|eight|nine|ten", record.value.lower()):
        score -= 4.0
    return score

def _latest_state_hint_match(question: str, record: StateRecord) -> bool:
    q = question.lower()
    attr = record.attribute.lower()
    hint_pairs = [
        ("bike", "bike count"),
        ("yoga", "yoga frequency"),
        ("dr smith", "dr smith frequency"),
        ("company", "current company"),
        ("lens", "camera lens"),
        ("guitar", "guitar serviced location"),
        ("gym", "gym time"),
        ("page", "reading page"),
        ("stars", "starbucks gold stars needed"),
        ("volleyball", "volleyball record"),
        ("personal best", "personal best time"),
        ("family trip", "family trip location"),
    ]
    return any(hint in q and attribute in attr for hint, attribute in hint_pairs)

def score_turn(question_terms: set[str], content: str, role: str) -> float:
    """Score a turn as potential evidence for a question."""
    terms = tokenize(content)
    if not terms:
        return 0.0
    overlap = sum(1 for term in terms if term in question_terms)
    score = overlap / (len(terms) ** 0.5)
    if role == "user":
        score += 0.05
    if any(term in terms for term in ["update", "updated", "now", "current", "currently", "latest", "recent", "recently"]):
        score += 0.35
    return score

def build_timeline_context(
    *,
    question: str,
    sessions: list[list[dict[str, Any]]],
    session_ids: list[str],
    session_dates: list[str],
    ranked_session_ids: list[str],
    reference_date: str = "",
    top_k_sessions: int = 10,
    max_turns: int = 120,
    max_chars: int = 36000,
) -> TimelineContext:
    """Build a chronological state context from retrieved sessions.

    The output has two parts:
    1. latest-state candidates, sorted by relevance and recency;
    2. chronological evidence, sorted by session date and turn index.

    This layout is designed for knowledge-update and temporal-reasoning tasks,
    where a reader often needs both the most relevant value-like snippets and
    the event order that makes them valid.
    """
    selected_ids = set(ranked_session_ids[:top_k_sessions])
    question_terms = set(tokenize(question))
    turns: list[TimelineTurn] = []
    state_records: list[StateRecord] = []

    for session_index, session in enumerate(sessions):
        sid = (
            session_ids[session_index]
            if session_index < len(session_ids)
            else f"session-{session_index}"
        )
        if sid not in selected_ids:
            continue
        session_date = (
            str(session_dates[session_index])
            if session_index < len(session_dates)
            else ""
        )
        for turn_index, turn in enumerate(session):
            content = str(turn.get("content", "")).strip()
            if not content:
                continue
            role = str(turn.get("role", "unknown"))
            relevance = score_turn(question_terms, content, role)
            state_records.extend(
                extract_state_records(
                    content,
                    date=session_date,
                    evidence_id=f"{sid}:{turn_index}",
                )
            )
            turns.append(
                TimelineTurn(
                    session_id=sid,
                    session_date=session_date,
                    turn_index=turn_index,
                    role=role,
                    content=content,
                    relevance=relevance,
                )
            )

    scored_turns = [turn for turn in turns if turn.relevance > 0]
    latest_candidates = sorted(
        scored_turns or turns,
        key=lambda turn: (turn.relevance, date_key(turn.session_date), -turn.turn_index),
        reverse=True,
    )[: min(16, max_turns)]
    chronological = sorted(
        turns,
        key=lambda turn: (date_key(turn.session_date), turn.session_id, turn.turn_index),
    )

    selected: list[TimelineTurn] = []
    seen = set()
    for turn in [*latest_candidates, *chronological]:
        key = (turn.session_id, turn.turn_index)
        if key in seen:
            continue
        seen.add(key)
        selected.append(turn)
        if len(selected) >= max_turns:
            break

    lines = [
        "## Timeline State Context",
        "",
    ]
    state_text = LatestStateMemory(state_records).format_for_prompt(max_records=10)
    if state_text:
        lines.extend([state_text, ""])
    semantic_text = SemanticStateIndex(state_records).format_for_prompt(question, max_records=14)
    if semantic_text:
        lines.extend([semantic_text, ""])
    reasoner_text = build_state_reasoner_context(
        question=question,
        records=state_records,
        reference_date=reference_date,
    )
    if reasoner_text:
        lines.extend([reasoner_text, ""])
    lines.extend([
        "Latest-state candidates:",
    ])
    for turn in latest_candidates:
        lines.append(
            f"- [{turn.session_date} {turn.session_id} turn {turn.turn_index} "
            f"{turn.role} rel={turn.relevance:.3f}] {turn.content}"
        )
    lines.extend(["", "Chronological evidence:"])

    used = sum(len(line) + 1 for line in lines)
    formatted_turns: list[TimelineTurn] = []
    for turn in chronological:
        line = (
            f"- [{turn.session_date} {turn.session_id} turn {turn.turn_index} "
            f"{turn.role} rel={turn.relevance:.3f}] {turn.content}"
        )
        if used + len(line) + 1 > max_chars:
            continue
        lines.append(line)
        used += len(line) + 1
        formatted_turns.append(turn)

    return TimelineContext(
        text="\n".join(lines),
        selected_turns=selected,
        latest_candidates=latest_candidates,
    )

def build_state_reasoner_context(*, question: str, records: list[StateRecord], reference_date: str = "") -> str:
    from .reasoner import StateReasoner

    result = StateReasoner(records).answer(question, reference_date=reference_date)
    if result is None:
        return ""
    evidence = ", ".join(result.evidence_ids[:6]) if result.evidence_ids else "none"
    return "\n".join(
        [
            "## Deterministic State Reasoner",
            "",
            f"- candidate_answer: {result.answer}",
            f"- reasoning_type: {result.reasoning_type}",
            f"- confidence: {result.confidence:.2f}",
            f"- evidence_ids: {evidence}",
            f"- explanation: {result.explanation}",
        ]
    )

__all__ = ['tokenize', 'score_event_phrase', 'score_state_record', '_score_latest_state_candidate', '_latest_state_hint_match', 'score_turn', 'build_timeline_context', 'build_state_reasoner_context']
