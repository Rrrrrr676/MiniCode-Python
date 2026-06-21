from __future__ import annotations

import threading

from minicode.web.broker import EventBroker


def test_broker_assigns_monotonic_sequences_and_replays_after_cursor() -> None:
    broker = EventBroker()
    first = broker.publish(
        session_id="session-1", turn_id="turn-1", event_type="turn.started"
    )
    second = broker.publish(
        session_id="session-1", turn_id="turn-1", event_type="assistant.delta"
    )

    assert (first.seq, second.seq) == (1, 2)
    assert [event.seq for event in broker.replay("session-1", after=1)] == [2]


def test_broker_waits_for_worker_thread_event_without_sleep() -> None:
    broker = EventBroker()
    published = threading.Event()

    def worker() -> None:
        broker.publish(
            session_id="session-1",
            turn_id="turn-1",
            event_type="turn.completed",
        )
        published.set()

    thread = threading.Thread(target=worker)
    thread.start()
    events = broker.wait_for_events("session-1", after=0, timeout=1)
    thread.join(timeout=1)

    assert published.is_set()
    assert [event.type for event in events] == ["turn.completed"]


def test_sequences_are_isolated_per_session() -> None:
    broker = EventBroker()
    one = broker.publish(session_id="one", turn_id="", event_type="session.snapshot")
    two = broker.publish(session_id="two", turn_id="", event_type="session.snapshot")

    assert one.seq == 1
    assert two.seq == 1


def test_sequence_can_resume_after_a_reconnecting_browser_cursor() -> None:
    broker = EventBroker()
    broker.seed_sequence("session-1", 41)
    event = broker.publish(
        session_id="session-1", turn_id="", event_type="session.snapshot"
    )

    assert event.seq == 42
