"""Session, metadata, checkpoint models and summary primitives."""
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
@dataclass
class FileCheckpoint:
    """Persistent file snapshot captured before a write tool mutates disk."""

    checkpoint_id: str
    created_at: float
    file_path: str
    existed: bool
    previous_content: str
    kind: str = "edit"
    group_id: str = ""

@dataclass
class SessionMetadata:
    """Lightweight metadata for session listing."""
    session_id: str
    created_at: float  # Unix timestamp
    updated_at: float  # Unix timestamp
    first_message: str = ""  # Truncated first user message
    last_message: str = ""   # Truncated last message
    message_count: int = 0
    workspace: str = ""      # Working directory when session started
    runtime_summary: str = ""  # Compact runtime timeline, if available
    checkpoint_count: int = 0  # Number of stored rewind checkpoints
    instruction_summary: str = ""
    hook_summary: str = ""
    delegation_summary: str = ""
    extension_summary: str = ""
    readiness_summary: str = ""

@dataclass
class SessionData:
    """Complete session state that can be persisted and restored."""
    session_id: str
    created_at: float
    updated_at: float
    workspace: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    transcript_entries: list[dict[str, Any]] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    permissions_summary: dict[str, Any] = field(default_factory=dict)
    skills: list[dict[str, Any]] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    instruction_layers: list[dict[str, Any]] = field(default_factory=list)
    hook_status: dict[str, Any] = field(default_factory=dict)
    delegated_tasks: list[dict[str, Any]] = field(default_factory=list)
    delegation_status: dict[str, Any] = field(default_factory=dict)
    extension_manifests: list[dict[str, Any]] = field(default_factory=list)
    readiness_report: dict[str, Any] = field(default_factory=dict)
    checkpoints: list[FileCheckpoint] = field(default_factory=list)
    metadata: SessionMetadata = field(default=None)

    # Incremental save tracking
    _last_saved_msg_count: int = field(default=0, repr=False)
    _last_saved_transcript_count: int = field(default=0, repr=False)
    _last_saved_checkpoint_count: int = field(default=0, repr=False)
    _delta_save_count: int = field(default=0, repr=False)
    _last_full_save_hash: str = field(default="", repr=False)

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = SessionMetadata(
                session_id=self.session_id,
                created_at=self.created_at,
                updated_at=self.updated_at,
                message_count=len(self.messages),
                workspace=self.workspace,
                checkpoint_count=len(self.checkpoints),
                instruction_summary=_summarize_instruction_layers(self.instruction_layers),
                hook_summary=_summarize_hook_status(self.hook_status),
                delegation_summary=_summarize_delegation_status(self.delegation_status),
                extension_summary=_summarize_extension_manifests(self.extension_manifests),
                readiness_summary=_summarize_readiness_report(self.readiness_report),
            )

    def update_metadata(self) -> None:
        """Refresh metadata from current state."""
        self.updated_at = time.time()
        self.metadata.updated_at = self.updated_at
        self.metadata.message_count = len(self.messages)
        self.metadata.runtime_summary = _runtime_summary_from_transcript_entries(
            self.transcript_entries
        )
        self.metadata.checkpoint_count = len(self.checkpoints)
        self.metadata.instruction_summary = _summarize_instruction_layers(
            self.instruction_layers
        )
        self.metadata.hook_summary = _summarize_hook_status(self.hook_status)
        self.metadata.delegation_summary = _summarize_delegation_status(
            self.delegation_status
        )
        self.metadata.extension_summary = _summarize_extension_manifests(
            self.extension_manifests
        )
        self.metadata.readiness_summary = _summarize_readiness_report(
            self.readiness_report
        )

        # Extract first user message (truncated)
        for msg in self.messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if not isinstance(content, str):
                    content = "" if content is None else str(content)
                self.metadata.first_message = content[:100]
                break

        # Extract last message (truncated) — avoid full reverse iteration
        if self.messages:
            for msg in reversed(self.messages):
                if msg.get("role") in ("user", "assistant"):
                    content = msg.get("content", "")
                    if not isinstance(content, str):
                        content = "" if content is None else str(content)
                    self.metadata.last_message = content[:100]
                    break

    @property
    def has_delta(self) -> bool:
        """Check if there are unsaved changes."""
        return (
            len(self.messages) != self._last_saved_msg_count
            or len(self.transcript_entries) != self._last_saved_transcript_count
            or len(self.checkpoints) != self._last_saved_checkpoint_count
        )

    def _compute_content_hash(self) -> str:
        """Compute a quick hash of message content for change detection."""
        h = hashlib.md5(usedforsecurity=False)
        for msg in self.messages[-20:]:  # Hash last 20 messages for speed
            h.update(msg.get("role", "").encode())
            content = msg.get("content", "")
            if isinstance(content, str):
                h.update(content[:500].encode())
        return h.hexdigest()

def _runtime_trace_token_from_entry(entry: dict[str, Any]) -> str | None:
    kind = str(entry.get("runtimeKind") or "").strip().lower()
    category = str(entry.get("category") or "").strip().lower()
    body = str(entry.get("body") or "")

    if category != "runtime" and not kind:
        normalized = " ".join(body.split()).lower()
        if normalized.startswith("runtime phase:"):
            kind = "phase"
        elif normalized.startswith("verification guard:"):
            kind = "guard"
        elif "widened mode is active" in normalized or "widening is now available" in normalized:
            kind = "widening"
        elif normalized.startswith("turn completed") or normalized.startswith("turn complete"):
            kind = "stop"
        else:
            return None

    step = entry.get("runtimeStep")
    step_suffix = f"@{step}" if isinstance(step, int) else ""
    phase = str(entry.get("runtimePhase") or "").strip()
    stop_reason = str(entry.get("runtimeStopReason") or "").strip()
    verify = str(entry.get("runtimeVerificationFocus") or "").strip()

    if kind == "phase":
        return f"phase:{phase or 'unknown'}{step_suffix}"
    if kind == "guard":
        return f"guard:{verify or stop_reason or 'verification'}{step_suffix}"
    if kind == "widening":
        return f"widen:{stop_reason or 'escalation'}{step_suffix}"
    if kind == "stop":
        return f"stop:{stop_reason or 'done'}{step_suffix}"
    if kind == "compaction":
        return f"compact:{phase or 'context'}{step_suffix}"
    if kind == "recovery":
        return f"recover:{stop_reason or 'resume'}{step_suffix}"

    return f"{kind or 'runtime'}{step_suffix}"

def _runtime_summary_from_transcript_entries(entries: list[dict[str, Any]]) -> str:
    tokens: list[str] = []
    for entry in entries:
        token = _runtime_trace_token_from_entry(entry)
        if token and (not tokens or tokens[-1] != token):
            tokens.append(token)
    return " -> ".join(tokens)

def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

def _named_list(items: list[Any], *, key: str = "name") -> list[str]:
    names: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            candidate = _safe_text(item.get(key) or item.get("label") or item.get("id"))
            if candidate:
                names.append(candidate)
        else:
            candidate = _safe_text(item)
            if candidate:
                names.append(candidate)
    return names

def _summarize_instruction_layers(layers: list[dict[str, Any]]) -> str:
    names = _named_list(layers)
    if not names:
        return ""
    return f"{len(names)} layer(s): {', '.join(names[:3])}" + ("..." if len(names) > 3 else "")

def _summarize_hook_status(status: dict[str, Any]) -> str:
    if not isinstance(status, dict):
        return ""
    summary = _safe_text(status.get("summary"))
    if summary:
        return summary
    total = int(status.get("total_hooks", 0) or 0)
    enabled = int(status.get("enabled_hooks", 0) or 0)
    return f"{enabled}/{total} hook(s) enabled" if total else ""

def _summarize_delegation_status(status: dict[str, Any]) -> str:
    if not isinstance(status, dict):
        return ""
    summary = _safe_text(status.get("summary"))
    if summary:
        return summary
    running = int(status.get("running_tasks", 0) or 0)
    available = int(status.get("available_slots", 0) or 0)
    return f"{running} running, {available} slot(s) open"

def _summarize_extension_manifests(manifests: list[dict[str, Any]]) -> str:
    names = _named_list(manifests)
    if not names:
        return ""
    return f"{len(names)} extension(s): {', '.join(names[:3])}" + ("..." if len(names) > 3 else "")

def _summarize_readiness_report(report: dict[str, Any]) -> str:
    if not isinstance(report, dict):
        return ""
    summary = _safe_text(report.get("summary"))
    if summary:
        return summary
    status = _safe_text(report.get("status"))
    provider = _safe_text(report.get("provider"))
    if status and provider:
        return f"{status} via {provider}"
    return status or provider

def _format_named_collection(items: list[Any], *, fallback: str = "(none)") -> str:
    names = _named_list(items)
    return ", ".join(names) if names else fallback

__all__ = ["SessionMetadata", "FileCheckpoint", "SessionData", "_runtime_summary_from_transcript_entries"]
