from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

import minicode.session as session_module
from minicode.web.app import create_app
from minicode.web.diff import read_workspace_diff, read_workspace_diff_file
from minicode.web.runner import WebSessionRunner
from minicode.web.security import sanitize_for_web


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    home = tmp_path / "home"
    monkeypatch.setattr(session_module, "MINI_CODE_DIR", home)
    monkeypatch.setattr(session_module, "SESSIONS_DIR", home / "sessions")

    def execute(context):
        context.callbacks.on_assistant_message("done")
        return [*context.session.messages, {"role": "assistant", "content": "done"}]

    runner = WebSessionRunner(tmp_path, executor=execute)
    with TestClient(create_app(runner=runner, frontend_dir=tmp_path / "missing")) as client:
        yield client, runner


def test_session_creation_message_submission_and_missing_session(api_client) -> None:
    client, _runner = api_client
    created = client.post("/api/sessions", json={"title": ""})
    assert created.status_code == 201
    session_id = created.json()["sessionId"]

    accepted = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "Inspect this project"},
    )
    assert accepted.status_code == 202
    assert accepted.json()["turnId"].startswith("turn-")

    missing = client.get("/api/sessions/not-real")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SESSION_NOT_FOUND"
    assert missing.json()["error"]["traceId"].startswith("trace-")


def test_api_validation_uses_stable_error_envelope(api_client) -> None:
    client, _runner = api_client
    created = client.post("/api/sessions", json={}).json()
    response = client.post(f"/api/sessions/{created['sessionId']}/messages", json={"content": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_websocket_replays_events_and_emits_a_fresh_snapshot(api_client) -> None:
    client, _runner = api_client
    session_id = client.post("/api/sessions", json={}).json()["sessionId"]

    with client.websocket_connect(f"/api/sessions/{session_id}/events?after=0") as socket:
        first = socket.receive_json()
        second = socket.receive_json()

    assert [first["seq"], second["seq"]] == [1, 2]
    assert first["type"] == "session.snapshot"
    assert second["type"] == "session.snapshot"


def test_session_snapshot_never_serializes_inline_secret(api_client) -> None:
    client, _runner = api_client
    session_id = client.post("/api/sessions", json={}).json()["sessionId"]
    secret = "sk-this-must-never-reach-the-browser"
    client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": f"API_KEY={secret}"},
    )

    snapshot_text = client.get(f"/api/sessions/{session_id}").text
    assert secret not in snapshot_text
    assert "[REDACTED]" in snapshot_text


def test_secret_redaction_covers_keys_bearer_tokens_and_inline_keys() -> None:
    value = sanitize_for_web(
        {
            "apiKey": "sk-super-secret-value",
            "nested": ["Authorization: Bearer abc.def.ghi", "API_KEY=visible-no-more"],
        }
    )

    serialized = str(value)
    assert "super-secret" not in serialized
    assert "abc.def.ghi" not in serialized
    assert "visible-no-more" not in serialized
    assert serialized.count("[REDACTED]") >= 3


def test_workspace_diff_includes_tracked_and_untracked_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=MiniCode Test", "-c", "user.email=test@example.invalid",
            "commit", "-q", "-m", "base",
        ],
        cwd=tmp_path,
        check=True,
    )
    tracked.write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")

    diff = read_workspace_diff(tmp_path)
    paths = {item.path for item in diff.files}

    assert paths == {"tracked.txt", "new.txt"}
    assert diff.additions >= 2
    assert all(not hasattr(item, "patch") for item in diff.files)
    assert diff.revision

    tracked_patch = read_workspace_diff_file(tmp_path, "tracked.txt")
    assert "two" in tracked_patch.patch
    assert tracked_patch.revision == diff.revision

    untracked_patch = read_workspace_diff_file(tmp_path, "new.txt")
    assert "new" in untracked_patch.patch


def test_workspace_diff_rejects_paths_outside_workspace(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    with pytest.raises(ValueError):
        read_workspace_diff_file(tmp_path, "../outside.txt")
    with pytest.raises(ValueError):
        read_workspace_diff_file(tmp_path, str((tmp_path / "absolute.txt").resolve()))


def test_workspace_diff_truncates_text_and_handles_binary_and_symlink(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "large.txt").write_text("line\n" * 1_000, encoding="utf-8")
    (tmp_path / "binary.dat").write_bytes(b"before\0after")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (tmp_path / "escape.txt").symlink_to(outside)

    summary = read_workspace_diff(tmp_path)
    by_path = {item.path: item for item in summary.files}
    assert by_path["binary.dat"].isBinary is True
    assert "escape.txt" not in by_path

    large_patch = read_workspace_diff_file(tmp_path, "large.txt", max_bytes=64)
    assert large_patch.truncated is True
    assert large_patch.patch

    binary_patch = read_workspace_diff_file(tmp_path, "binary.dat")
    assert binary_patch.isBinary is True
    assert binary_patch.patch == ""

    with pytest.raises(ValueError):
        read_workspace_diff_file(tmp_path, "escape.txt")


def test_diff_api_returns_summary_and_lazy_patch(api_client, tmp_path: Path) -> None:
    client, _runner = api_client
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "lazy.txt").write_text("lazy patch\n", encoding="utf-8")
    session_id = client.post("/api/sessions", json={}).json()["sessionId"]

    summary = client.get(f"/api/sessions/{session_id}/diff")
    assert summary.status_code == 200
    body = summary.json()
    lazy_summary = next(item for item in body["files"] if item["path"] == "lazy.txt")
    assert "patch" not in lazy_summary

    patch = client.get(f"/api/sessions/{session_id}/diff/files/lazy.txt")
    assert patch.status_code == 200
    assert "lazy patch" in patch.json()["patch"]

    escaped = client.get(f"/api/sessions/{session_id}/diff/files/%2E%2E%2Foutside.txt")
    assert escaped.status_code == 400
