"""Stable intent data models shared by runtime and control layers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    CODE = "code"
    DEBUG = "debug"
    REFACTOR = "refactor"
    EXPLAIN = "explain"
    SEARCH = "search"
    REVIEW = "review"
    TEST = "test"
    DOCUMENT = "document"
    CONFIGURE = "configure"
    QUESTION = "question"
    CHAT = "chat"
    MEMORY = "memory"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    ANALYZE = "analyze"
    COMPARE = "compare"
    MERGE = "merge"
    SPLIT = "split"
    MOVE = "move"
    RENAME = "rename"
    UNKNOWN = "unknown"


@dataclass
class ParsedIntent:
    raw_input: str
    intent_type: IntentType
    action_type: ActionType
    confidence: float
    entities: dict[str, list[str]] = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)
    complexity_hint: str = "moderate"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_input": self.raw_input,
            "intent_type": self.intent_type.value,
            "action_type": self.action_type.value,
            "confidence": self.confidence,
            "entities": self.entities,
            "keywords": self.keywords,
            "complexity_hint": self.complexity_hint,
            "timestamp": self.timestamp,
        }

    def is_code_related(self) -> bool:
        return self.intent_type in {
            IntentType.CODE,
            IntentType.DEBUG,
            IntentType.REFACTOR,
            IntentType.REVIEW,
            IntentType.TEST,
        }

    def is_read_only(self) -> bool:
        return self.action_type in {ActionType.READ, ActionType.ANALYZE}


__all__ = ["ActionType", "IntentType", "ParsedIntent"]
