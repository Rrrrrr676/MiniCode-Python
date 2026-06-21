from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import minicode.session as session_module
from minicode.web.runner import PermissionResolutionError, WebSessionRunner


@pytest.fixture
def isolated_sessions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    sessions = home / "sessions"
    monkeypatch.setattr(session_module, "MINI_CODE_DIR", home)
    monkeypatch.setattr(session_module, "SESSIONS_DIR", sessions)
    return tmp_path


def _wait_for_terminal(runner: WebSessionRunner, session_id: str, timeout: float = 2) -> list:
    deadline = time.monotonic() + timeout
    cursor = 0
    collected = []
    while time.monotonic() < deadline:
        events = runner.broker.wait_for_events(session_id, after=cursor, timeout=0.2)
        collected.extend(events)
        if events:
            cursor = events[-1].seq
        if any(event.type in {"turn.completed", "turn.failed", "turn.cancelled"} for event in collected):
            return collected
    raise AssertionError("Web turn did not reach a terminal event")


def test_runner_maps_callbacks_and_persists_completed_turn(isolated_sessions: Path) -> None:
    def execute(context):
        context.callbacks.on_tool_start("read_file", {"path": "README.md"})
        context.callbacks.on_tool_result("read_file", "contents", False)
        context.callbacks.on_stream_chunk("Hello")
        context.callbacks.on_assistant_message("Hello from MiniCode")
        return [*context.session.messages, {"role": "assistant", "content": "Hello from MiniCode"}]

    runner = WebSessionRunner(isolated_sessions, executor=execute)
    snapshot = runner.create_session()
    runner.submit_message(snapshot.sessionId, "Inspect this project")
    events = _wait_for_terminal(runner, snapshot.sessionId)

    assert [event.type for event in events][-1] == "turn.completed"
    assert "tool.started" in [event.type for event in events]
    assert "tool.completed" in [event.type for event in events]
    assert runner.snapshot(snapshot.sessionId).status == "completed"
    assert runner.snapshot(snapshot.sessionId).messages[-1]["content"] == "Hello from MiniCode"
    runner.close()


def test_runner_maps_background_exception_to_sticky_failure(isolated_sessions: Path) -> None:
    def execute(_context):
        raise NameError("injected")

    runner = WebSessionRunner(isolated_sessions, executor=execute)
    snapshot = runner.create_session()
    runner.submit_message(snapshot.sessionId, "Fail visibly")
    events = _wait_for_terminal(runner, snapshot.sessionId)
    failure = next(event for event in events if event.type == "turn.failed")

    assert failure.payload["errorType"] == "NameError"
    assert failure.payload["traceId"].startswith("trace-")
    assert runner.snapshot(snapshot.sessionId).status == "failed"
    assert not any(event.type == "turn.completed" for event in events)
    runner.close()


def test_permission_can_be_approved_and_duplicate_resolution_is_rejected(
    isolated_sessions: Path,
) -> None:
    permission_seen = threading.Event()

    def execute(context):
        permission_seen.set()
        response = context.permission_prompt(
            {
                "kind": "edit",
                "summary": "Edit file",
                "details": ["target: demo.py"],
                "scope": "demo.py",
                "choices": [],
            }
        )
        assert response["decision"] == "allow_once"
        return [*context.session.messages, {"role": "assistant", "content": "approved"}]

    runner = WebSessionRunner(isolated_sessions, executor=execute, permission_timeout=2)
    snapshot = runner.create_session()
    runner.submit_message(snapshot.sessionId, "Make an edit")
    assert permission_seen.wait(1)
    requested = runner.broker.wait_for_events(snapshot.sessionId, after=2, timeout=1)
    permission = next(event for event in requested if event.type == "permission.requested")
    runner.resolve_permission(permission.payload["requestId"], decision="allow_once")
    with pytest.raises(PermissionResolutionError, match="already resolved"):
        runner.resolve_permission(permission.payload["requestId"], decision="allow_once")

    events = _wait_for_terminal(runner, snapshot.sessionId)
    assert any(
        event.type == "permission.resolved" and event.payload["decision"] == "allow_once"
        for event in events
    )
    runner.close()


def test_permission_timeout_is_explicit_and_unblocks_worker(isolated_sessions: Path) -> None:
    def execute(context):
        response = context.permission_prompt(
            {"kind": "command", "summary": "Run command", "scope": "python demo.py"}
        )
        assert response["decision"] == "deny_once"
        return [*context.session.messages, {"role": "assistant", "content": "denied"}]

    runner = WebSessionRunner(isolated_sessions, executor=execute, permission_timeout=0.05)
    snapshot = runner.create_session()
    runner.submit_message(snapshot.sessionId, "Run it")
    events = _wait_for_terminal(runner, snapshot.sessionId)

    resolved = next(event for event in events if event.type == "permission.resolved")
    assert resolved.payload == {
        "requestId": resolved.payload["requestId"],
        "decision": "deny_once",
        "reason": "timeout",
    }
    runner.close()
