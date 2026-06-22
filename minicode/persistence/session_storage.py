"""Incremental session JSON and delta persistence."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from minicode.config import MINI_CODE_DIR
from minicode.observability.logging import log_session_event

from .session_models import *

SESSIONS_DIR = MINI_CODE_DIR / "sessions"
AUTOSAVE_INTERVAL_SECONDS = 30  # Minimum seconds between autosaves
DELTA_DIR_NAME = "deltas"        # Subdirectory for delta files
FULL_SAVE_INTERVAL = 10          # Do a full save every N delta saves
MAX_DELTA_FILES = 50             # Maximum delta files before forced consolidation

def _serialize_checkpoint(checkpoint: FileCheckpoint) -> dict[str, Any]:
    return {
        "checkpoint_id": checkpoint.checkpoint_id,
        "created_at": checkpoint.created_at,
        "file_path": checkpoint.file_path,
        "existed": checkpoint.existed,
        "previous_content": checkpoint.previous_content,
        "kind": checkpoint.kind,
        "group_id": checkpoint.group_id,
    }

def _deserialize_checkpoint(data: dict[str, Any]) -> FileCheckpoint:
    return FileCheckpoint(
        checkpoint_id=str(data["checkpoint_id"]),
        created_at=float(data["created_at"]),
        file_path=str(data["file_path"]),
        existed=bool(data["existed"]),
        previous_content=str(data.get("previous_content", "")),
        kind=str(data.get("kind", "edit") or "edit"),
        group_id=str(data.get("group_id", "")),
    )

def _session_file(session_id: str) -> Path:
    """Return path to a session JSON file."""
    return SESSIONS_DIR / f"{session_id}.json"

def _session_delta_dir(session_id: str) -> Path:
    """Return path to a session's delta directory."""
    return SESSIONS_DIR / DELTA_DIR_NAME / session_id

def _session_index_file() -> Path:
    """Return path to the session index file."""
    return MINI_CODE_DIR / "sessions_index.json"

def _load_session_index() -> dict[str, SessionMetadata]:
    """Load the session index (lightweight metadata for all sessions)."""
    index_path = _session_index_file()
    if not index_path.exists():
        return {}
    try:
        raw = index_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return {
            sid: SessionMetadata(**meta)
            for sid, meta in data.items()
        }
    except (json.JSONDecodeError, TypeError, KeyError):
        return {}

def _save_session_index(index: dict[str, SessionMetadata]) -> None:
    """Save the session index."""
    MINI_CODE_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    serializable = {
        sid: {
            "session_id": meta.session_id,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
            "first_message": meta.first_message,
            "last_message": meta.last_message,
            "message_count": meta.message_count,
            "workspace": meta.workspace,
            "runtime_summary": meta.runtime_summary,
            "checkpoint_count": meta.checkpoint_count,
            "instruction_summary": meta.instruction_summary,
            "hook_summary": meta.hook_summary,
            "delegation_summary": meta.delegation_summary,
            "extension_summary": meta.extension_summary,
            "readiness_summary": meta.readiness_summary,
        }
        for sid, meta in index.items()
    }
    _session_index_file().write_text(
        json.dumps(serializable, indent=2) + "\n",
        encoding="utf-8",
    )

def _save_delta(session: SessionData) -> None:
    """Save only the incremental changes since last full save.

    Delta files contain new messages and transcript entries appended
    since the last save point. This is much cheaper than serializing
    the entire session on every autosave.
    """
    delta_dir = _session_delta_dir(session.session_id)
    delta_dir.mkdir(parents=True, exist_ok=True)

    # Collect new messages since last save
    new_messages = session.messages[session._last_saved_msg_count:]
    new_transcripts = session.transcript_entries[session._last_saved_transcript_count:]
    new_checkpoints = session.checkpoints[session._last_saved_checkpoint_count:]

    if not new_messages and not new_transcripts and not new_checkpoints:
        return

    # Create delta entry
    delta_data: dict[str, Any] = {
        "ts": time.time(),
        "msg_offset": session._last_saved_msg_count,
        "transcript_offset": session._last_saved_transcript_count,
    }
    if new_messages:
        delta_data["messages"] = new_messages
    if new_transcripts:
        delta_data["transcripts"] = new_transcripts
    if new_checkpoints:
        delta_data["checkpoint_offset"] = session._last_saved_checkpoint_count
        delta_data["checkpoints"] = [_serialize_checkpoint(cp) for cp in new_checkpoints]

    # Write delta file with sequential numbering
    delta_num = session._delta_save_count
    delta_path = delta_dir / f"delta_{delta_num:04d}.json"
    delta_path.write_text(
        json.dumps(delta_data, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Update tracking
    session._last_saved_msg_count = len(session.messages)
    session._last_saved_transcript_count = len(session.transcript_entries)
    session._last_saved_checkpoint_count = len(session.checkpoints)
    session._delta_save_count += 1

def _consolidate_deltas(session: SessionData) -> None:
    """Merge all delta files into the full session file and clean up.

    This is called periodically to prevent unbounded delta file growth
    and to ensure the full session file stays consistent.
    """
    delta_dir = _session_delta_dir(session.session_id)
    if not delta_dir.exists():
        return

    # Deltas are already applied during load_session, so just clean up
    for delta_file in sorted(delta_dir.glob("delta_*.json")):
        try:
            delta_file.unlink()
        except OSError:
            pass

    # Try to remove empty delta directory
    try:
        delta_dir.rmdir()
        # Also try to remove parent if empty
        parent = delta_dir.parent
        if parent.name == DELTA_DIR_NAME and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass

    session._delta_save_count = 0

def save_session(session: SessionData, force_full: bool = False) -> None:
    """Persist session to disk with incremental delta support.

    Uses a hybrid strategy:
    - Delta saves: Only append new messages/transcripts (fast, small I/O)
    - Full saves: Serialize entire session (slower, but ensures consistency)
    - Consolidation: Merge deltas into full file periodically

    Args:
        session: The session to save
        force_full: Force a full save (e.g., on explicit save command)
    """
    log_session_event("save", details=f"id={session.session_id} force_full={force_full}")
    session.update_metadata()
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Decide whether to do a full save or delta save
    should_full_save = (
        force_full
        or session._delta_save_count == 0  # First save is always full
        or session._delta_save_count >= FULL_SAVE_INTERVAL
        or session._delta_save_count >= MAX_DELTA_FILES  # Safety cap
    )

    if should_full_save:
        # Full save: serialize everything
        session_path = _session_file(session.session_id)
        serializable = {
            "session_id": session.session_id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "workspace": session.workspace,
            "messages": session.messages,
            "transcript_entries": session.transcript_entries,
            "history": session.history,
            "permissions_summary": session.permissions_summary,
            "skills": session.skills,
            "mcp_servers": session.mcp_servers,
            "instruction_layers": session.instruction_layers,
            "hook_status": session.hook_status,
            "delegated_tasks": session.delegated_tasks,
            "delegation_status": session.delegation_status,
            "extension_manifests": session.extension_manifests,
            "readiness_report": session.readiness_report,
            "checkpoints": [_serialize_checkpoint(cp) for cp in session.checkpoints],
            "metadata": {
                "session_id": session.metadata.session_id,
                "created_at": session.metadata.created_at,
                "updated_at": session.metadata.updated_at,
                "first_message": session.metadata.first_message,
                "last_message": session.metadata.last_message,
                "message_count": session.metadata.message_count,
                "workspace": session.metadata.workspace,
                "runtime_summary": session.metadata.runtime_summary,
                "checkpoint_count": session.metadata.checkpoint_count,
                "instruction_summary": session.metadata.instruction_summary,
                "hook_summary": session.metadata.hook_summary,
                "delegation_summary": session.metadata.delegation_summary,
                "extension_summary": session.metadata.extension_summary,
                "readiness_summary": session.metadata.readiness_summary,
            },
        }
        session_path.write_text(
            json.dumps(serializable, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # Reset delta tracking
        session._last_saved_msg_count = len(session.messages)
        session._last_saved_transcript_count = len(session.transcript_entries)
        session._last_saved_checkpoint_count = len(session.checkpoints)
        session._last_full_save_hash = session._compute_content_hash()

        # Consolidate and clean up delta files
        _consolidate_deltas(session)
    else:
        # Delta save: only append new data
        _save_delta(session)

    # Update index (always lightweight)
    index = _load_session_index()
    index[session.session_id] = session.metadata
    _save_session_index(index)

def load_session(session_id: str) -> SessionData | None:
    """Load a session from disk, applying any pending deltas.

    Loading process:
    1. Load the base session file
    2. Scan for delta files
    3. Apply deltas in order (append new messages/transcripts)
    4. Update tracking counters
    """
    log_session_event("load", details=f"id={session_id}")
    session_path = _session_file(session_id)
    if not session_path.exists():
        return None

    try:
        raw = session_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        metadata = SessionMetadata(**data.get("metadata", {}))
        session = SessionData(
            session_id=data["session_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            workspace=data["workspace"],
            messages=data.get("messages", []),
            transcript_entries=data.get("transcript_entries", []),
            history=data.get("history", []),
            permissions_summary=data.get("permissions_summary", {}),
            skills=data.get("skills", []),
            mcp_servers=data.get("mcp_servers", []),
            instruction_layers=data.get("instruction_layers", []),
            hook_status=data.get("hook_status", {}),
            delegated_tasks=data.get("delegated_tasks", []),
            delegation_status=data.get("delegation_status", {}),
            extension_manifests=data.get("extension_manifests", []),
            readiness_report=data.get("readiness_report", {}),
            checkpoints=[
                _deserialize_checkpoint(item)
                for item in data.get("checkpoints", [])
                if isinstance(item, dict)
            ],
            metadata=metadata,
        )

        # Apply any pending deltas
        delta_dir = _session_delta_dir(session_id)
        if delta_dir.exists():
            delta_files = sorted(delta_dir.glob("delta_*.json"))
            for delta_path in delta_files:
                try:
                    delta_raw = delta_path.read_text(encoding="utf-8")
                    delta = json.loads(delta_raw)

                    # Append delta messages at the correct offset
                    if "messages" in delta:
                        offset = delta.get("msg_offset", len(session.messages))
                        # Ensure we don't duplicate messages
                        if offset >= len(session.messages):
                            session.messages.extend(delta["messages"])
                        elif offset + len(delta["messages"]) > len(session.messages):
                            # Partial overlap — append only the new part
                            overlap = len(session.messages) - offset
                            session.messages.extend(delta["messages"][overlap:])

                    # Append delta transcripts
                    if "transcripts" in delta:
                        t_offset = delta.get("transcript_offset", len(session.transcript_entries))
                        if t_offset >= len(session.transcript_entries):
                            session.transcript_entries.extend(delta["transcripts"])
                        elif t_offset + len(delta["transcripts"]) > len(session.transcript_entries):
                            overlap = len(session.transcript_entries) - t_offset
                            session.transcript_entries.extend(delta["transcripts"][overlap:])

                    if "checkpoints" in delta:
                        c_offset = delta.get("checkpoint_offset", len(session.checkpoints))
                        parsed = [
                            _deserialize_checkpoint(item)
                            for item in delta["checkpoints"]
                            if isinstance(item, dict)
                        ]
                        if c_offset >= len(session.checkpoints):
                            session.checkpoints.extend(parsed)
                        elif c_offset + len(parsed) > len(session.checkpoints):
                            overlap = len(session.checkpoints) - c_offset
                            session.checkpoints.extend(parsed[overlap:])

                    session._delta_save_count += 1
                except (json.JSONDecodeError, KeyError, TypeError):
                    # Skip corrupt delta files
                    continue

        # Update tracking counters
        session._last_saved_msg_count = len(session.messages)
        session._last_saved_transcript_count = len(session.transcript_entries)
        session._last_saved_checkpoint_count = len(session.checkpoints)
        session._last_full_save_hash = session._compute_content_hash()

        return session
    except (json.JSONDecodeError, KeyError, TypeError):
        return None

def list_sessions() -> list[SessionMetadata]:
    """List all available sessions, newest first."""
    index = _load_session_index()
    sessions = list(index.values())
    sessions.sort(key=lambda s: s.updated_at, reverse=True)
    return sessions

def delete_session(session_id: str) -> bool:
    """Delete a session from disk. Returns True if deleted."""
    session_path = _session_file(session_id)
    if not session_path.exists():
        return False

    try:
        session_path.unlink()
        # Clean up orphaned delta files
        delta_dir = _session_delta_dir(session_id)
        if delta_dir.exists():
            import shutil
            shutil.rmtree(delta_dir, ignore_errors=True)
        index = _load_session_index()
        index.pop(session_id, None)
        _save_session_index(index)
        return True
    except OSError:
        return False

def cleanup_old_sessions(max_sessions: int = 50) -> int:
    """Remove oldest sessions beyond max_sessions limit. Returns count deleted."""
    sessions = list_sessions()
    if len(sessions) <= max_sessions:
        return 0

    to_delete = sessions[max_sessions:]
    deleted = 0
    for meta in to_delete:
        if delete_session(meta.session_id):
            deleted += 1
    return deleted

def create_new_session(workspace: str) -> SessionData:
    """Create a new empty session."""
    now = time.time()
    session_id = uuid.uuid4().hex[:12]
    log_session_event("create", details=f"id={session_id} workspace={workspace}")
    return SessionData(
        session_id=session_id,
        created_at=now,
        updated_at=now,
        workspace=workspace,
    )

def get_latest_session(workspace: str | None = None) -> SessionData | None:
    """Get the most recent session, optionally filtered by workspace."""
    sessions = list_sessions()
    for meta in sessions:
        if workspace is None or meta.workspace == workspace:
            return load_session(meta.session_id)
    return None

__all__ = ["SESSIONS_DIR", "AUTOSAVE_INTERVAL_SECONDS", "DELTA_DIR_NAME", "FULL_SAVE_INTERVAL", "MAX_DELTA_FILES", "save_session", "load_session", "list_sessions", "delete_session", "cleanup_old_sessions", "create_new_session", "get_latest_session", "SessionMetadata", "FileCheckpoint", "SessionData", "_runtime_summary_from_transcript_entries"]
