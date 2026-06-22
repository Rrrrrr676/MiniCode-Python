"""Read deduplication and micro-compaction services."""
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

from .models import *

class ReadDedupManager:
    """Hash-based file read deduplication.

    When the same file (same path + same content hash) is read again,
    returns a stub instead of re-injecting full content into context.
    """

    def __init__(self):
        self._entries: dict[str, ReadDedupEntry] = {}  # file_path -> entry
        self._stub_template = (
            "File unchanged since last read. "
            "The content from the earlier Read tool_result "
            "in this conversation is still current — refer to that instead."
        )

    def register_read(
        self, file_path: str, content: str, message_index: int
    ) -> bool:
        """Register a file read. Returns True if this is a new/different read."""
        content_hash = hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()

        existing = self._entries.get(file_path)
        if existing and existing.content_hash == content_hash:
            return False  # Duplicate

        self._entries[file_path] = ReadDedupEntry(
            file_path=file_path,
            content_hash=content_hash,
            timestamp=time.time(),
            message_index=message_index,
        )
        return True  # New or changed

    def should_dedup(self, file_path: str, content: str) -> bool:
        """Check if this read can be deduplicated."""
        content_hash = hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()
        existing = self._entries.get(file_path)
        return existing is not None and existing.content_hash == content_hash

    def get_stub(self, file_path: str) -> str:
        """Get dedup stub for a previously-read file."""
        entry = self._entries.get(file_path)
        if not entry:
            return ""
        return (
            f"[Read deduplicated: {file_path}]\n"
            f"{self._stub_template}\n"
            f"(Original content at message index {entry.message_index})"
        )

    def invalidate(self, file_path: str) -> None:
        """Invalidate cache for a specific file (e.g., after write)."""
        self._entries.pop(file_path, None)

    def clear(self) -> None:
        self._entries.clear()

class MicrocompactEngine:
    """Lightweight pre-compact optimization.

    Clears old tool results when they're unlikely to be in prompt cache
    anymore (time-based), reducing rewrite cost on next API call.
    """

    def __init__(self, config: MicrocompactState | None = None):
        self._state = config or MicrocompactState()

    def run_time_based_microcompact(
        self,
        messages: list[dict[str, Any]],
        now: float | None = None,
    ) -> CompactionResult:
        """Clear old tool results based on time since last assistant response.

        Does NOT generate summaries. Simply replaces old tool_result
        content with a fixed marker text.
        """
        now = now or time.time()
        elapsed = now - self._state.last_time_based_compact

        if elapsed < self._state.time_based_interval:
            return CompactionResult(
                success=False,
                strategy=CompactStrategy.MICROCOMPACT,
                trigger=CompactTrigger.MICROCOMPACT_TIME,
                messages=messages,
            )

        tool_results = [
            (i, m) for i, m in enumerate(messages)
            if m.get("role") == "tool_result"
            and not m.get("content", "").startswith("[Tool result persisted")
            and not m.get("content", "").startswith("[Old tool result")
        ]

        if len(tool_results) <= self._state.keep_recent_tool_results:
            return CompactionResult(
                success=False,
                strategy=CompactStrategy.MICROCOMPACT,
                trigger=CompactTrigger.MICROCOMPACT_TIME,
                messages=messages,
            )

        modified = list(messages)
        cleared_count = 0
        tokens_cleared = 0

        # Keep recent N, clear older ones
        keep_indices = {idx for idx, _ in tool_results[-self._state.keep_recent_tool_results:]}

        for idx, msg in tool_results:
            if idx in keep_indices:
                continue

            old_content = msg.get("content", "")
            old_size = len(old_content)
            modified[idx] = {
                **msg,
                "content": "[Old tool result content cleared by time-based microcompact]",
                "_microcompacted": True,
            }
            cleared_count += 1
            tokens_cleared += old_size // 4  # Rough token estimate

        self._state.last_time_based_compact = now
        self._state.total_tokens_cleared += tokens_cleared

        logger.info(
            "Time-based microcompact: cleared %d old tool results (~%d tokens)",
            cleared_count,
            tokens_cleared,
        )

        return CompactionResult(
            success=True,
            strategy=CompactStrategy.MICROCOMPACT,
            trigger=CompactTrigger.MICROCOMPACT_TIME,
            messages=modified,
            tokens_freed=tokens_cleared,
        )

__all__ = ["ReadDedupManager", "MicrocompactEngine"]
