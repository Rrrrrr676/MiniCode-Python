"""Tool-result budget and persistence policy."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from .models import ToolResultPersisted

class ToolResultBudgetManager:
    """Manages tool result size budget with disk persistence.

    When a tool_result exceeds the per-message budget, it is persisted
    to disk and replaced with a preview stub in the context.
    """

    DEFAULT_BUDGET_PER_MESSAGE = 8000  # chars per user message's tool results
    PERSIST_THRESHOLD = 4000  # Persist results larger than this
    PREVIEW_MAX_CHARS = 500

    def __init__(
        self,
        workspace: str | Path | None = None,
        budget_per_message: int = DEFAULT_BUDGET_PER_MESSAGE,
        persist_threshold: int = PERSIST_THRESHOLD,
    ):
        self._workspace = Path(workspace) if workspace else Path.cwd()
        self._budget = budget_per_message
        self._persist_threshold = persist_threshold
        self._results_dir = self._workspace / ".mini-code-tool-results"
        self._persisted: dict[str, ToolResultPersisted] = {}

    def check_and_replace(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        """Check tool results against budget, persist oversized ones.

        Returns:
            Tuple of (modified_messages, total_bytes_saved)
        """
        if not self._results_dir.exists():
            self._results_dir.mkdir(parents=True, exist_ok=True)

        modified = list(messages)
        bytes_saved = 0

        for i, msg in enumerate(modified):
            if msg.get("role") != "tool_result":
                continue

            content = msg.get("content")
            # Normalize content to a string — tool_result content can be None
            # (no output) or a non-string (structured result). Without this,
            # len(None) / len(list) crashes or mis-sizes (TS normalizes these).
            if not isinstance(content, str):
                content = "" if content is None else str(content)
                modified[i] = {**msg, "content": content}
                msg = modified[i]
            content_size = len(content)

            if content_size <= self._persist_threshold:
                continue

            tool_name = msg.get("toolName", "unknown")
            persisted = self._persist_content(content, tool_name, i)

            preview = self._generate_preview(content, tool_name, persisted.persisted_path)
            modified[i] = {**msg, "content": preview, "_persisted_path": str(persisted.persisted_path)}
            self._persisted[f"{i}-{tool_name}"] = persisted
            bytes_saved += content_size - len(preview)

        return modified, bytes_saved

    def _persist_content(
        self, content: str, tool_name: str, index: int
    ) -> ToolResultPersisted:
        """Persist content to disk atomically."""
        safe_name = f"{tool_name}_{index}_{int(time.time() * 1000)}.txt"
        path = self._results_dir / safe_name

        meta = {
            "tool_name": tool_name,
            "message_index": index,
            "original_size": len(content),
            "timestamp": time.time(),
        }
        header = json.dumps(meta, ensure_ascii=False) + "\n---CONTENT---\n"

        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self._results_dir), prefix=".tool_result_", suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(header)
                f.write(content)
            os.replace(tmp_path, str(path))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return ToolResultPersisted(
            original_size=len(content),
            persisted_path=path,
            preview_text="",
            tool_name=tool_name,
        )

    def _generate_preview(
        self, content: str, tool_name: str, path: Path
    ) -> str:
        """Generate preview text for persisted content."""
        lines = content.splitlines()
        head_lines = lines[:8]
        tail_lines = lines[-3:] if len(lines) > 12 else []

        parts = [
            f"[Tool result persisted to disk — {len(content)} chars]",
            f"Tool: {tool_name}",
            f"Path: {path.name}",
            "",
            "--- Preview (first/last lines) ---",
        ]
        parts.extend(head_lines)
        if tail_lines:
            parts.append(f"... ({len(lines) - len(head_lines) - len(tail_lines)} lines omitted) ...")
            parts.extend(tail_lines)

        preview = "\n".join(parts)
        return preview[:self.PREVIEW_MAX_CHARS]

    def get_persisted_count(self) -> int:
        return len(self._persisted)

    def get_total_saved_bytes(self) -> int:
        return sum(r.original_size for r in self._persisted.values())

__all__ = ["ToolResultBudgetManager"]
