"""Thread-safe event sequencing, replay, and long-poll subscription."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any

from minicode.web.events import EventType, WebEvent, utc_timestamp


class EventBroker:
    """Owns event ordering for every Web session.

    Agent callbacks may run on worker threads. The broker is therefore the only
    object allowed to assign sequence numbers or mutate event history.
    """

    def __init__(self, *, history_limit: int = 2_000) -> None:
        self._history_limit = max(10, history_limit)
        self._events: dict[str, deque[WebEvent]] = defaultdict(
            lambda: deque(maxlen=self._history_limit)
        )
        self._sequences: dict[str, int] = defaultdict(int)
        self._condition = threading.Condition(threading.RLock())

    def publish(
        self,
        *,
        session_id: str,
        turn_id: str,
        event_type: EventType,
        payload: dict[str, Any] | None = None,
    ) -> WebEvent:
        with self._condition:
            self._sequences[session_id] += 1
            event = WebEvent(
                seq=self._sequences[session_id],
                session_id=session_id,
                turn_id=turn_id,
                type=event_type,
                timestamp=utc_timestamp(),
                payload=payload or {},
            )
            self._events[session_id].append(event)
            self._condition.notify_all()
            return event

    def current_seq(self, session_id: str) -> int:
        with self._condition:
            return self._sequences[session_id]

    def replay(self, session_id: str, *, after: int = 0) -> list[WebEvent]:
        with self._condition:
            return [event for event in self._events[session_id] if event.seq > after]

    def wait_for_events(
        self,
        session_id: str,
        *,
        after: int,
        timeout: float = 1.0,
    ) -> list[WebEvent]:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            while True:
                events = [event for event in self._events[session_id] if event.seq > after]
                if events:
                    return events
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self._condition.wait(remaining)

    def seed_sequence(self, session_id: str, sequence: int) -> None:
        """Restore a known sequence without allowing it to move backwards."""
        with self._condition:
            self._sequences[session_id] = max(self._sequences[session_id], sequence)
