"""Checkpoint creation, selection, preview, and rewind."""
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

from .session_models import FileCheckpoint, SessionData
from .formatters import _fmt_ts, _format_checkpoint_type
from .session_storage import load_session, save_session

def create_file_checkpoint(
    session: SessionData | None,
    *,
    file_path: str,
    existed: bool,
    previous_content: str,
) -> FileCheckpoint | None:
    """Record a durable rewind snapshot before a file mutation."""
    if session is None:
        return None

    checkpoint = FileCheckpoint(
        checkpoint_id=uuid.uuid4().hex[:12],
        created_at=time.time(),
        file_path=file_path,
        existed=existed,
        previous_content=previous_content,
    )
    session.checkpoints.append(checkpoint)
    save_session(session, force_full=False)
    return checkpoint

def _select_checkpoints_to_rewind(
    session: SessionData,
    *,
    steps: int = 1,
    checkpoint_id: str | None = None,
) -> list[FileCheckpoint]:
    if not session.checkpoints:
        return []
    if checkpoint_id:
        for index in range(len(session.checkpoints) - 1, -1, -1):
            checkpoint = session.checkpoints[index]
            if checkpoint.checkpoint_id == checkpoint_id:
                group_id = checkpoint.group_id
                if group_id:
                    while index > 0 and session.checkpoints[index - 1].group_id == group_id:
                        index -= 1
                return session.checkpoints[index:]
        return []
    if steps <= 0:
        return []
    start_index = max(len(session.checkpoints) - steps, 0)
    tail_group_id = session.checkpoints[-1].group_id
    if tail_group_id:
        group_start = len(session.checkpoints) - 1
        while group_start > 0 and session.checkpoints[group_start - 1].group_id == tail_group_id:
            group_start -= 1
        start_index = min(start_index, group_start)
    return session.checkpoints[start_index:]

def rewind_session_data(
    session: SessionData,
    *,
    steps: int = 1,
    checkpoint_id: str | None = None,
) -> list[FileCheckpoint]:
    """Restore checkpoints against an in-memory session and persist the result."""
    selected = _select_checkpoints_to_rewind(
        session,
        steps=steps,
        checkpoint_id=checkpoint_id,
    )
    if not selected:
        return []

    rewind_group_id = uuid.uuid4().hex[:12]
    rewind_created_at = time.time()
    reverse_checkpoints: list[FileCheckpoint] = []
    captured_paths: set[str] = set()
    for checkpoint in reversed(selected):
        if checkpoint.file_path in captured_paths:
            continue
        target = Path(checkpoint.file_path)
        existed = target.exists()
        previous_content = target.read_text(encoding="utf-8") if existed else ""
        reverse_checkpoints.append(
            FileCheckpoint(
                checkpoint_id=uuid.uuid4().hex[:12],
                created_at=rewind_created_at,
                file_path=checkpoint.file_path,
                existed=existed,
                previous_content=previous_content,
                kind="rewind",
                group_id=rewind_group_id,
            )
        )
        captured_paths.add(checkpoint.file_path)

    for checkpoint in reversed(selected):
        target = Path(checkpoint.file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if checkpoint.existed:
            target.write_text(checkpoint.previous_content, encoding="utf-8")
        elif target.exists():
            target.unlink()

    del session.checkpoints[-len(selected):]
    session.checkpoints.extend(reverse_checkpoints)
    save_session(session, force_full=True)
    return selected

def rewind_session(
    session_id: str,
    *,
    steps: int = 1,
    checkpoint_id: str | None = None,
) -> tuple[SessionData | None, list[FileCheckpoint]]:
    """Restore the latest checkpointed file edits for a saved session."""
    session = load_session(session_id)
    if session is None:
        return session, []

    selected = rewind_session_data(
        session,
        steps=steps,
        checkpoint_id=checkpoint_id,
    )
    return session, selected

def format_rewind_preview(
    session: SessionData,
    *,
    steps: int = 1,
    checkpoint_id: str | None = None,
) -> str:
    """Format a dry-run view of which checkpoints a rewind would restore."""
    selected = _select_checkpoints_to_rewind(
        session,
        steps=steps,
        checkpoint_id=checkpoint_id,
    )
    if not selected:
        return f"No checkpoints available to rewind for session {session.session_id[:8]}."

    unique_files: list[str] = []
    seen_paths: set[str] = set()
    for checkpoint in reversed(selected):
        if checkpoint.file_path not in seen_paths:
            unique_files.append(checkpoint.file_path)
            seen_paths.add(checkpoint.file_path)

    lines = [
        f"Rewind preview for session {session.session_id[:8]}:",
        "",
        f"Would restore {len(selected)} checkpoint(s) across {len(unique_files)} file(s).",
    ]
    if checkpoint_id:
        lines.append(f"Target checkpoint: {checkpoint_id[:8]}")

    if any(checkpoint.kind == "rewind" for checkpoint in selected):
        lines.append("Mode: undo prior rewind safety checkpoints.")
    else:
        lines.append("Mode: restore pre-edit file snapshots.")

    lines.extend(["", "Planned restores:"])
    for index, checkpoint in enumerate(reversed(selected), 1):
        created = _fmt_ts(checkpoint.created_at, "%Y-%m-%d %H:%M:%S")
        status = "existing file" if checkpoint.existed else "new file"
        checkpoint_type = _format_checkpoint_type(checkpoint)
        lines.append(
            f"  {index}. [{checkpoint.checkpoint_id[:8]}] {created} - {checkpoint.file_path}"
        )
        lines.append(f"     Restores: {status}")
        lines.append(f"     Type: {checkpoint_type}")

    return "\n".join(lines)

__all__ = ["create_file_checkpoint", "format_rewind_preview", "rewind_session", "rewind_session_data"]
