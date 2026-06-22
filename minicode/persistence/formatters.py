"""Session list, resume, inspect, replay, and checkpoint formatting."""
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

from .session_models import (
    FileCheckpoint,
    SessionData,
    SessionMetadata,
    _format_named_collection,
    _named_list,
    _safe_text,
)

def _fmt_ts(ts: float, fmt: str) -> str:
    """Fast timestamp formatting using datetime (avoids repeated localtime)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt)

def format_session_list(sessions: list[SessionMetadata]) -> str:
    """Format sessions as a human-readable list."""
    if not sessions:
        return "No saved sessions found."

    lines = ["Saved sessions:", ""]
    for i, meta in enumerate(sessions, 1):
        created = _fmt_ts(meta.created_at, "%Y-%m-%d %H:%M")
        workspace = meta.workspace or "unknown"
        first_msg = meta.first_message or "(empty)"
        count = meta.message_count

        lines.append(
            f"  {i}. [{meta.session_id[:8]}] {created} - {workspace}"
        )
        lines.append(f"     Messages: {count} | First: {first_msg}")
        if meta.checkpoint_count:
            lines.append(f"     Checkpoints: {meta.checkpoint_count}")
        if meta.runtime_summary:
            lines.append(f"     Runtime: {meta.runtime_summary}")
        lines.append("")

    lines.append(f"Total: {len(sessions)} session(s)")
    return "\n".join(lines)

def format_session_resume(session: SessionData) -> str:
    """Format session info for resume confirmation."""
    created = _fmt_ts(session.created_at, "%Y-%m-%d %H:%M:%S")
    updated = _fmt_ts(session.updated_at, "%Y-%m-%d %H:%M:%S")
    return (
        f"Resuming session {session.session_id[:8]}\n"
        f"  Created: {created}\n"
        f"  Updated: {updated}\n"
        f"  Messages: {len(session.messages)}\n"
        f"  Workspace: {session.workspace}"
        + (
            f"\n  Checkpoints: {session.metadata.checkpoint_count}"
            if session.metadata.checkpoint_count
            else ""
        )
        + (
            f"\n  Recent checkpoints: {_format_checkpoint_summary_details(session)}"
            if session.metadata.checkpoint_count
            else ""
        )
        + (
            f"\n  Runtime: {session.metadata.runtime_summary}"
            if session.metadata.runtime_summary
            else ""
        )
        + (
            f"\n  Readiness: {session.metadata.readiness_summary}"
            if session.metadata.readiness_summary
            else ""
        )
        + (
            f"\n  Instructions: {session.metadata.instruction_summary}"
            if session.metadata.instruction_summary
            else ""
        )
        + (
            f"\n  Hooks: {session.metadata.hook_summary}"
            if session.metadata.hook_summary
            else ""
        )
        + (
            f"\n  Delegation: {session.metadata.delegation_summary}"
            if session.metadata.delegation_summary
            else ""
        )
        + (
            f"\n  Extensions: {session.metadata.extension_summary}"
            if session.metadata.extension_summary
            else ""
        )
    )

def _session_entry_preview(text: str, *, limit: int = 96) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."

def _session_transcript_label(entry: dict[str, Any]) -> str:
    kind = str(entry.get("kind", "entry") or "entry")
    if entry.get("category") == "runtime":
        runtime_kind = str(entry.get("runtimeKind", "") or "").strip()
        return f"runtime:{runtime_kind}" if runtime_kind else "runtime"
    if kind == "tool":
        tool_name = str(entry.get("toolName", "") or "").strip()
        status = str(entry.get("status", "") or "").strip()
        if tool_name and status:
            return f"tool:{tool_name}/{status}"
        if tool_name:
            return f"tool:{tool_name}"
    return kind

def _format_recent_transcript_lines(
    session: SessionData,
    *,
    limit: int = 8,
) -> list[str]:
    if not session.transcript_entries:
        return ["  (none)"]

    lines: list[str] = []
    recent_entries = session.transcript_entries[-limit:]
    for entry in recent_entries:
        label = _session_transcript_label(entry)
        preview = _session_entry_preview(str(entry.get("body", "") or "(empty)"))
        lines.append(f"  - [{label}] {preview}")
    return lines

def _format_recent_history_lines(
    session: SessionData,
    *,
    limit: int = 8,
) -> list[str]:
    if not session.history:
        return ["  (none)"]

    return [
        f"  {index}. {_session_entry_preview(item)}"
        for index, item in enumerate(session.history[-limit:], 1)
    ]

def _format_instruction_layer_lines(
    session: SessionData,
    *,
    limit: int = 6,
) -> list[str]:
    if not session.instruction_layers:
        return ["  (none)"]
    lines: list[str] = []
    for layer in session.instruction_layers[:limit]:
        name = _safe_text(layer.get("name")) or "layer"
        scope = _safe_text(layer.get("scope")) or "unknown"
        kind = _safe_text(layer.get("kind")) or "instruction"
        preview = _safe_text(layer.get("preview")) or "(no preview)"
        exists = "present" if layer.get("exists") else "missing"
        lines.append(f"  - {name} [{scope}/{kind}, {exists}] {preview}")
    if len(session.instruction_layers) > limit:
        lines.append(f"  ... {len(session.instruction_layers) - limit} more layer(s)")
    return lines

def _format_hook_status_lines(session: SessionData) -> list[str]:
    if not session.hook_status:
        return ["  (none)"]
    status = session.hook_status
    lines = [
        "  "
        + (
            _safe_text(status.get("summary"))
            or f"{status.get('enabled_hooks', 0)}/{status.get('total_hooks', 0)} hook(s) enabled"
        )
    ]
    hooks = status.get("hooks")
    if isinstance(hooks, list):
        for hook in hooks[:5]:
            lines.append(
                f"  - {hook.get('event', 'hook')} :: {hook.get('last_status', 'idle')}"
                f", calls={hook.get('call_count', 0)}, failures={hook.get('failure_count', 0)}"
            )
    return lines

def _format_delegation_lines(session: SessionData) -> list[str]:
    summary = session.metadata.delegation_summary or _summarize_delegation_status(
        session.delegation_status
    )
    lines = [f"  {summary}"] if summary else []
    if not session.delegated_tasks:
        return lines or ["  (none)"]
    for task in session.delegated_tasks[:5]:
        label = _safe_text(task.get("label") or task.get("task_id") or task.get("id")) or "task"
        status = _safe_text(task.get("status")) or "running"
        lines.append(f"  - {label} :: {status}")
    return lines

def _format_extension_lines(
    session: SessionData,
    *,
    limit: int = 6,
) -> list[str]:
    if not session.extension_manifests:
        return ["  (none)"]
    lines: list[str] = []
    for manifest in session.extension_manifests[:limit]:
        name = _safe_text(manifest.get("name")) or "extension"
        scope = _safe_text(manifest.get("scope")) or "unknown"
        version = _safe_text(manifest.get("version")) or "unversioned"
        enabled = "enabled" if manifest.get("enabled", True) else "disabled"
        description = _safe_text(manifest.get("description")) or "(no description)"
        lines.append(f"  - {name} [{scope}] {version}, {enabled} :: {description}")
    if len(session.extension_manifests) > limit:
        lines.append(
            f"  ... {len(session.extension_manifests) - limit} more extension(s)"
        )
    return lines

def _format_readiness_lines(session: SessionData) -> list[str]:
    if not session.readiness_report:
        return ["  (none)"]
    report = session.readiness_report
    provider = _safe_text(report.get("provider")) or "unknown-provider"
    provider_channel = _safe_text(report.get("provider_channel")) or ""
    status = _safe_text(report.get("status")) or "unknown"
    provider_ready = "ready" if report.get("provider_ready") else "not-ready"
    fallback_candidates = list(report.get("fallback_candidates", []) or [])
    viable_fallbacks = set(str(item) for item in list(report.get("viable_fallbacks", []) or []))
    lines = [f"  {status} via {provider} ({provider_ready})"]
    if provider_channel:
        lines.append(f"  channel: {provider_channel}")
    if fallback_candidates:
        lines.append(
            f"  fallback coverage: {len(viable_fallbacks)}/{len(fallback_candidates)} locally ready"
        )
        for candidate in fallback_candidates[:5]:
            label = "ready" if str(candidate) in viable_fallbacks else "not-ready"
            lines.append(f"  - fallback {candidate} [{label}]")
    guidance = report.get("fallback_guidance")
    if isinstance(guidance, list) and guidance:
        for item in guidance[:3]:
            lines.append(f"  - guidance: {item}")
    issues = report.get("issues")
    if isinstance(issues, list) and issues:
        for issue in issues[:5]:
            lines.append(f"  - {issue}")
    return lines

def _format_checkpoint_summary_details(
    session: SessionData,
    *,
    limit: int = 3,
) -> str:
    if not session.checkpoints:
        return "none"

    items: list[str] = []
    for checkpoint in reversed(session.checkpoints[-limit:]):
        file_name = Path(checkpoint.file_path).name or checkpoint.file_path
        label = " [rewind]" if getattr(checkpoint, "kind", "edit") == "rewind" else ""
        items.append(f"[{checkpoint.checkpoint_id[:8]}] {file_name}{label}")
    return f"{len(session.checkpoints)} saved; latest " + ", ".join(items)

def _format_checkpoint_type(checkpoint: FileCheckpoint) -> str:
    if getattr(checkpoint, "kind", "edit") == "rewind":
        return "rewind safety"
    return "edit"

def format_checkpoint_summary_line(
    session: SessionData | None,
    *,
    limit: int = 3,
) -> str:
    """Format a compact checkpoint summary for TUI and transcript surfaces."""
    if not session or not session.checkpoints:
        return ""
    return f"checkpoint-summary: {_format_checkpoint_summary_details(session, limit=limit)}"

def format_session_inspect(
    session: SessionData,
    *,
    transcript_limit: int = 8,
) -> str:
    """Format a detailed session inspection view for CLI/session replay."""
    created = _fmt_ts(session.created_at, "%Y-%m-%d %H:%M:%S")
    updated = _fmt_ts(session.updated_at, "%Y-%m-%d %H:%M:%S")
    skills = _format_named_collection(session.skills)
    mcp_servers = _format_named_collection(session.mcp_servers)

    lines = [
        f"Session inspect: {session.session_id[:8]}",
        f"  Created: {created}",
        f"  Updated: {updated}",
        f"  Workspace: {session.workspace}",
        f"  Messages: {len(session.messages)}",
        f"  Transcript entries: {len(session.transcript_entries)}",
        f"  History entries: {len(session.history)}",
        f"  Skills: {skills}",
        f"  MCP servers: {mcp_servers}",
        f"  Checkpoints: {session.metadata.checkpoint_count}",
    ]
    if session.metadata.runtime_summary:
        lines.append(f"  Runtime: {session.metadata.runtime_summary}")
    if session.metadata.readiness_summary:
        lines.append(f"  Readiness: {session.metadata.readiness_summary}")
    if session.metadata.instruction_summary:
        lines.append(f"  Instructions: {session.metadata.instruction_summary}")
    if session.metadata.hook_summary:
        lines.append(f"  Hooks: {session.metadata.hook_summary}")
    if session.metadata.delegation_summary:
        lines.append(f"  Delegation: {session.metadata.delegation_summary}")
    if session.metadata.extension_summary:
        lines.append(f"  Extensions: {session.metadata.extension_summary}")

    lines.extend(
        [
            "",
            f"Recent checkpoints: {_format_checkpoint_summary_details(session)}"
            if session.checkpoints
            else "Recent checkpoints: none",
            "",
            "Instruction layers:",
            *_format_instruction_layer_lines(session),
            "",
            "Hook surface:",
            *_format_hook_status_lines(session),
            "",
            "Delegation surface:",
            *_format_delegation_lines(session),
            "",
            "Extensions:",
            *_format_extension_lines(session),
            "",
            "Readiness:",
            *_format_readiness_lines(session),
            "",
            f"Recent transcript ({min(len(session.transcript_entries), transcript_limit)} shown):",
            *_format_recent_transcript_lines(session, limit=transcript_limit),
        ]
    )
    return "\n".join(lines)

def format_session_replay(
    session: SessionData,
    *,
    transcript_limit: int = 16,
    history_limit: int = 8,
    checkpoint_limit: int = 5,
) -> str:
    """Format a replay-oriented historical view for a session."""
    created = _fmt_ts(session.created_at, "%Y-%m-%d %H:%M:%S")
    updated = _fmt_ts(session.updated_at, "%Y-%m-%d %H:%M:%S")
    lines = [
        f"Session replay: {session.session_id[:8]}",
        f"  Workspace: {session.workspace}",
        f"  Created: {created}",
        f"  Updated: {updated}",
        f"  Runtime: {session.metadata.runtime_summary or '(none)'}",
        f"  Checkpoints: {session.metadata.checkpoint_count}",
    ]
    if session.metadata.readiness_summary:
        lines.append(f"  Readiness: {session.metadata.readiness_summary}")
        readiness_details = _format_readiness_lines(session)
        if readiness_details and readiness_details != ["  (none)"]:
            lines.extend(readiness_details[1:])
    if session.metadata.delegation_summary:
        lines.append(f"  Delegation: {session.metadata.delegation_summary}")
    lines.extend(
        [
            "",
            f"Checkpoint trail ({min(len(session.checkpoints), checkpoint_limit)} shown):",
        ]
    )
    if session.checkpoints:
        for checkpoint in reversed(session.checkpoints[-checkpoint_limit:]):
            created_at = _fmt_ts(checkpoint.created_at, "%Y-%m-%d %H:%M:%S")
            file_name = Path(checkpoint.file_path).name or checkpoint.file_path
            checkpoint_type = _format_checkpoint_type(checkpoint)
            lines.append(
                f"  - [{checkpoint.checkpoint_id[:8]}] {created_at} :: {file_name} ({checkpoint_type})"
            )
    else:
        lines.append("  (none)")

    lines.extend(
        [
            "",
            "Instruction layers:",
            *_format_instruction_layer_lines(session, limit=4),
            "",
            "Extensions:",
            *_format_extension_lines(session, limit=4),
            "",
            f"Prompt history ({min(len(session.history), history_limit)} shown):",
            *_format_recent_history_lines(session, limit=history_limit),
            "",
            f"Transcript timeline ({min(len(session.transcript_entries), transcript_limit)} shown):",
            *_format_recent_transcript_lines(session, limit=transcript_limit),
        ]
    )
    return "\n".join(lines)

def format_session_checkpoints(session: SessionData) -> str:
    """Format rewind checkpoints for inspection."""
    if not session.checkpoints:
        return f"No checkpoints saved for session {session.session_id[:8]}."

    lines = [
        f"Checkpoints for session {session.session_id[:8]}:",
        "",
    ]
    for index, checkpoint in enumerate(reversed(session.checkpoints), 1):
        created = _fmt_ts(checkpoint.created_at, "%Y-%m-%d %H:%M:%S")
        status = "existing file" if checkpoint.existed else "new file"
        checkpoint_type = _format_checkpoint_type(checkpoint)
        lines.append(
            f"  {index}. [{checkpoint.checkpoint_id[:8]}] {created} - {checkpoint.file_path}"
        )
        lines.append(f"     Restores: {status}")
        lines.append(f"     Type: {checkpoint_type}")
    lines.append("")
    lines.append(f"Total: {len(session.checkpoints)} checkpoint(s)")
    return "\n".join(lines)

__all__ = ["format_checkpoint_summary_line", "format_session_checkpoints", "format_session_inspect", "format_session_list", "format_session_replay", "format_session_resume"]
