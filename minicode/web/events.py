"""Stable event protocol shared by the Web API and browser client."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal


EventType = Literal[
    "session.snapshot",
    "turn.started",
    "runtime.phase",
    "assistant.delta",
    "assistant.completed",
    "tool.started",
    "tool.completed",
    "permission.requested",
    "permission.resolved",
    "diff.updated",
    "turn.failed",
    "turn.incomplete",
    "turn.completed",
    "turn.cancelled",
]


@dataclass(frozen=True, slots=True)
class WebEvent:
    seq: int
    session_id: str
    turn_id: str
    type: EventType
    timestamp: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {
            "seq": data["seq"],
            "sessionId": data["session_id"],
            "turnId": data["turn_id"],
            "type": data["type"],
            "timestamp": data["timestamp"],
            "payload": data["payload"],
        }


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
