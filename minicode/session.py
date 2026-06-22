"""Compatibility facade for :mod:`minicode.persistence.session_storage`."""

from __future__ import annotations

from typing import Any

from minicode.persistence import autosave as _autosave
from minicode.persistence import rewind as _rewind
from minicode.persistence import session_storage as _storage
from minicode.persistence.formatters import (
    format_checkpoint_summary_line,
    format_session_checkpoints,
    format_session_inspect,
    format_session_list,
    format_session_replay,
    format_session_resume,
)
from minicode.persistence.rewind import format_rewind_preview, rewind_session_data
from minicode.persistence.session_storage import (
    AUTOSAVE_INTERVAL_SECONDS,
    DELTA_DIR_NAME,
    FULL_SAVE_INTERVAL,
    MAX_DELTA_FILES,
    FileCheckpoint,
    SessionData,
    SessionMetadata,
    _runtime_summary_from_transcript_entries,
)


MINI_CODE_DIR = _storage.MINI_CODE_DIR
SESSIONS_DIR = _storage.SESSIONS_DIR


def _sync_paths() -> None:
    _storage.MINI_CODE_DIR = MINI_CODE_DIR
    _storage.SESSIONS_DIR = SESSIONS_DIR


def save_session(session: SessionData, force_full: bool = False) -> None:
    _sync_paths()
    _storage.save_session(session, force_full=force_full)


def load_session(session_id: str) -> SessionData | None:
    _sync_paths()
    return _storage.load_session(session_id)


def list_sessions() -> list[SessionMetadata]:
    _sync_paths()
    return _storage.list_sessions()


def delete_session(session_id: str) -> bool:
    _sync_paths()
    return _storage.delete_session(session_id)


def cleanup_old_sessions(max_sessions: int = 50) -> int:
    _sync_paths()
    return _storage.cleanup_old_sessions(max_sessions=max_sessions)


def create_new_session(workspace: str) -> SessionData:
    _sync_paths()
    return _storage.create_new_session(workspace=workspace)


def get_latest_session(workspace: str | None = None) -> SessionData | None:
    _sync_paths()
    return _storage.get_latest_session(workspace=workspace)


def create_file_checkpoint(
    session: SessionData | None,
    *,
    file_path: str,
    existed: bool,
    previous_content: str,
) -> FileCheckpoint | None:
    _sync_paths()
    return _rewind.create_file_checkpoint(
        session,
        file_path=file_path,
        existed=existed,
        previous_content=previous_content,
    )


def rewind_session(
    session_id: str,
    *,
    steps: int = 1,
    checkpoint_id: str | None = None,
) -> tuple[SessionData | None, list[FileCheckpoint]]:
    _sync_paths()
    return _rewind.rewind_session(
        session_id,
        steps=steps,
        checkpoint_id=checkpoint_id,
    )


class AutosaveManager(_autosave.AutosaveManager):
    """Path-synchronizing compatibility subclass."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _sync_paths()
        super().__init__(*args, **kwargs)


__all__ = [
    "AUTOSAVE_INTERVAL_SECONDS",
    "AutosaveManager",
    "DELTA_DIR_NAME",
    "FULL_SAVE_INTERVAL",
    "FileCheckpoint",
    "MAX_DELTA_FILES",
    "MINI_CODE_DIR",
    "SESSIONS_DIR",
    "SessionData",
    "SessionMetadata",
    "cleanup_old_sessions",
    "create_file_checkpoint",
    "create_new_session",
    "delete_session",
    "format_checkpoint_summary_line",
    "format_rewind_preview",
    "format_session_checkpoints",
    "format_session_inspect",
    "format_session_list",
    "format_session_replay",
    "format_session_resume",
    "get_latest_session",
    "list_sessions",
    "load_session",
    "rewind_session",
    "rewind_session_data",
    "save_session",
]
