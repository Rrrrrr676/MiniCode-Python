"""Session-memory compaction strategy."""
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

class SessionMemoryCompactEngine:
    """Uses existing MemoryManager entries as compaction summary base.

    Instead of calling the model to generate a summary, this leverages
    already-maintained memory entries (project decisions, conventions,
    patterns) to form the compact summary, preserving recent messages
    verbatim as a tail.
    """

    TAIL_MIN_TOKENS = 10000
    TAIL_MIN_MESSAGES = 5
    TAIL_MAX_TOKENS = 40000

    def __init__(self, memory_manager=None):
        self._memory = memory_manager

    def try_session_memory_compact(
        self,
        messages: list[dict[str, Any]],
        context_window: int,
        estimate_fn=None,
        config: AutoCompactConfig | None = None,
    ) -> CompactionResult | None:
        """Attempt session memory compact. Returns None if not applicable."""

        config = config or AutoCompactConfig()

        if not config.session_memory_enabled:
            return None

        if self._memory is None:
            return None

        # Get memory context as summary base
        memory_context = self._memory.get_relevant_context(max_tokens=6000)
        if not memory_context.strip():
            return None  # No memory available, fall back to Full Compact

        # Find where to cut: keep recent tail
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # Calculate tail from the end
        tail_tokens = 0
        tail_start = len(non_system)
        estimate = estimate_fn or (lambda m: len(str(m)) // 4)

        for i in range(len(non_system) - 1, -1, -1):
            msg_tokens = estimate(non_system[i])
            if tail_tokens + msg_tokens > config.max_expand_tokens and \
               (len(non_system) - i) >= config.min_keep_messages:
                tail_start = i + 1
                break
            tail_tokens += msg_tokens

        if tail_tokens < self.TAIL_MIN_TOKENS:
            tail_start = max(0, len(non_system) - config.min_keep_messages)

        # Ensure we don't cut tool_use/tool_result pairs
        tail_start = self._adjust_for_tool_pair(non_system, tail_start)

        # Build compacted messages
        boundary = CompactBoundary(
            trigger=CompactTrigger.AUTO,
            strategy=CompactStrategy.SESSION_MEMORY,
            tokens_before=sum(estimate(m) for m in messages),
        )

        compacted = []
        compacted.append({
            "role": "system",
            "content": (
                f"[Context compacted at {time.strftime('%H:%M:%S')} via Session Memory]\n"
                f"Messages removed: {tail_start}. Tokens before: ~{boundary.tokens_before}\n\n"
                f"## Project Memory & Context\n\n{memory_context}\n\n"
                "--- Recent conversation continues below ---"
            ),
            "_compact_boundary": True,
        })

        # Add preserved tail
        tail = non_system[tail_start:]
        compacted.extend(tail)

        # Re-add system messages at front
        final = system_msgs + compacted

        boundary.tokens_after = sum(estimate(m) for m in final)
        boundary.messages_removed = len(messages) - len(final)
        boundary.preserved_segment = (tail_start + len(system_msgs), len(final) - 1)

        # Check if compaction actually helped
        if boundary.tokens_after >= boundary.tokens_before * 0.95:
            return None  # Not enough savings

        logger.info(
            "Session Memory Compact: %d → %d tokens (%d freed)",
            boundary.tokens_before,
            boundary.tokens_after,
            boundary.tokens_before - boundary.tokens_after,
        )

        return CompactionResult(
            success=True,
            strategy=CompactStrategy.SESSION_MEMORY,
            trigger=CompactTrigger.AUTO,
            messages=final,
            boundary=boundary,
            tokens_freed=boundary.tokens_before - boundary.tokens_after,
            summary_text=memory_context,
        )

    @staticmethod
    def _adjust_for_tool_pair(messages: list[dict], cut_point: int) -> int:
        """Adjust cut point to avoid breaking tool_use/tool_result pairs."""
        adjusted = cut_point

        # Scan forward from cut for orphaned tool_result
        for i in range(adjusted, len(messages)):
            if messages[i].get("role") == "tool_result":
                # Check if matching tool_use is before cut
                found_match = False
                for j in range(max(0, adjusted - 10), adjusted):
                    if (messages[j].get("role") == "assistant" and
                        isinstance(messages[j].get("content"), list) and
                        any(b.get("type") == "tool_use" for b in messages[j]["content"] if isinstance(b, dict))):
                        found_match = True
                        break
                if not found_match:
                    adjusted = i + 1

        # Scan backward for orphaned tool_use
        for i in range(adjusted - 1, max(0, adjusted - 10), -1):
            msg = messages[i]
            if (msg.get("role") == "assistant" and
                isinstance(msg.get("content"), list) and
                any(b.get("type") == "tool_use" for b in msg["content"] if isinstance(b, dict))):
                # Check if tool_result exists after cut
                has_result = any(
                    m.get("role") == "tool_result"
                    for m in messages[adjusted:]
                )
                if has_result:
                    adjusted = min(adjusted, i)
                    break

        return max(0, adjusted)

__all__ = ["SessionMemoryCompactEngine"]
