"""Auto-compaction strategy selection and dispatch."""
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
from .micro import MicrocompactEngine
from .session_memory import SessionMemoryCompactEngine

class AutoCompactDispatcher:
    """High-water mark auto-compaction dispatcher.

    Not a multi-level percentage selector. Instead:
    - Monitors token usage against threshold
    - Tries Session Memory Compact first
    - Falls back to Full Compact
    - Has circuit breaker for consecutive failures
    """

    def __init__(
        self,
        context_window: int = 200000,
        config: AutoCompactConfig | None = None,
        memory_manager=None,
        estimate_fn=None,
    ):
        self._context_window = context_window
        self._config = config or AutoCompactConfig()
        self._memory = memory_manager
        self._estimate = estimate_fn or (lambda m: len(str(m)) // 4)
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._boundaries: list[CompactBoundary] = []
        self._suppressed_until: float = 0.0  # Warning suppression after compact
        self._session_memory_engine = SessionMemoryCompactEngine(memory_manager)
        self._microcompact = MicrocompactEngine()

    @property
    def threshold_tokens(self) -> int:
        return int(self._context_window * self._config.threshold_ratio)

    @property
    def blocking_limit(self) -> int:
        return int(self._context_window * 0.97)

    @property
    def is_tripped(self) -> bool:
        """Pure predicate: are we at/over the failure threshold? No side effects
        (callers like ReactiveCompactEngine read this as a plain check)."""
        return self._consecutive_failures >= self._config.circuit_breaker_limit

    def _maybe_auto_recover(self) -> bool:
        """If tripped but past the recovery timeout, reset to half-open.

        Returns True if a recovery reset just happened. Without this, once
        tripped, ``should_trigger`` always returns False, ``_on_success`` never
        runs, and the breaker stays open for the whole session.
        """
        if self._consecutive_failures < self._config.circuit_breaker_limit:
            return False
        recovery = self._config.circuit_breaker_recovery_seconds
        if (
            recovery > 0
            and self._last_failure_time > 0
            and time.time() - self._last_failure_time >= recovery
        ):
            self._consecutive_failures = 0
            self._last_failure_time = 0.0
            logger.info(
                "Auto Compact circuit breaker auto-recovered after %.0fs", recovery
            )
            return True
        return False

    def should_trigger(
        self,
        messages: list[dict[str, Any]],
        token_usage: int | None = None,
    ) -> bool:
        """Check if auto compact should trigger."""
        if not self._config.enabled:
            return False
        if self.is_tripped:
            # Half-open auto-recovery: if past the recovery timeout, allow a
            # retry; otherwise stay blocked.
            if not self._maybe_auto_recover():
                return False

        usage = token_usage or sum(self._estimate(m) for m in messages)
        return usage >= self.threshold_tokens

    def dispatch(
        self,
        messages: list[dict[str, Any]],
        token_usage: int | None = None,
        force_full: bool = False,
    ) -> CompactionResult:
        """Run auto compact dispatch: try session memory first, then full."""
        if not self.should_trigger(messages, token_usage) and not force_full:
            return CompactionResult(
                success=False,
                strategy=CompactStrategy.FULL,
                trigger=CompactTrigger.AUTO,
                messages=messages,
            )

        usage = token_usage or sum(self._estimate(m) for m in messages)
        logger.info(
            "Auto Compact dispatch: usage=%d, threshold=%d, circuit_breaker=%s",
            usage,
            self.threshold_tokens,
            "TRIPPED" if self.is_tripped else "OK",
        )

        # Try Session Memory Compact first (unless forced full)
        if not force_full:
            sm_result = self._session_memory_engine.try_session_memory_compact(
                messages,
                self._context_window,
                self._estimate,
                self._config,
            )
            if sm_result and sm_result.effective:
                self._on_success(sm_result.boundary)
                self._suppress_warnings()
                return sm_result

        # Fall back to Full Compact
        return self._run_full_compact(messages, usage)

    def _run_full_compact(
        self, messages: list[dict[str, Any]], usage: int
    ) -> CompactionResult:
        """Full compact: generate summary and create new baseline."""
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if len(non_system) <= self._config.min_keep_messages:
            self._on_failure()
            return CompactionResult(
                success=False,
                strategy=CompactStrategy.FULL,
                trigger=CompactTrigger.AUTO,
                messages=messages,
                error="Too few messages to compact",
            )

        # Generate summary from conversation structure
        summary = self._generate_structured_summary(non_system)

        boundary = CompactBoundary(
            trigger=CompactTrigger.AUTO,
            strategy=CompactStrategy.FULL,
            tokens_before=usage,
        )

        # Build compacted: system + boundary + summary + restored essentials
        compacted = list(system_msgs)
        compacted.append({
            "role": "system",
            "content": (
                f"[Context compacted at {time.strftime('%H:%M:%S')} — Full Compact]\n"
                f"Original: ~{usage} tokens, {len(messages)} messages\n\n"
                f"## Conversation Summary\n\n{summary}"
            ),
            "_compact_boundary": True,
        })

        # Keep recent tail
        tail_size = min(len(non_system) // 3, self._config.min_keep_messages)
        tail = non_system[-tail_size:] if tail_size > 0 else []
        compacted.extend(tail)

        boundary.tokens_after = sum(self._estimate(m) for m in compacted)
        boundary.messages_removed = len(messages) - len(compacted)

        self._on_success(boundary)
        self._suppress_warnings()

        logger.info(
            "Full Compact: %d → %d tokens (%d removed)",
            boundary.tokens_before,
            boundary.tokens_after,
            boundary.messages_removed,
        )

        return CompactionResult(
            success=True,
            strategy=CompactStrategy.FULL,
            trigger=CompactTrigger.AUTO,
            messages=compacted,
            boundary=boundary,
            tokens_freed=boundary.tokens_before - boundary.tokens_after,
            summary_text=summary,
        )

    def _generate_structured_summary(self, messages: list[dict]) -> str:
        """Generate structured summary from message history without LLM call."""
        parts = ["### Summary of conversation so far:\n"]

        # Extract key information patterns
        user_topics = []
        tool_calls_made = set()
        files_mentioned = set()
        errors_seen = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user" and isinstance(content, str) and len(content) > 10:
                topic = content[:100].replace("\n", " ")
                user_topics.append(topic)

            if role == "assistant" and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls_made.add(block.get("name", "unknown"))
                        input_data = block.get("input", {})
                        if "file_path" in input_data:
                            files_mentioned.add(input_data["file_path"])

            if role == "tool_result":
                err = msg.get("isError")
                if err:
                    errors_seen.append(content[:80] if isinstance(content, str) else str(content)[:80])

        if user_topics:
            parts.append("**Topics discussed:**\n")
            for t in user_topics[:8]:
                parts.append(f"- {t}")
            parts.append("")

        if tool_calls_made:
            parts.append(f"**Tools used:** {', '.join(sorted(tool_calls_made))}\n")

        if files_mentioned:
            parts.append(f"**Files touched:** {', '.join(sorted(files_mentioned)[:10])}\n")

        if errors_seen:
            parts.append("**Errors encountered:**\n")
            for e in errors_seen[:3]:
                parts.append(f"- {e}")
            parts.append("")

        parts.append("\n*Continue from where we left off.*")
        return "\n".join(parts)

    def _on_success(self, boundary: CompactBoundary | None) -> None:
        self._consecutive_failures = 0
        if boundary:
            self._boundaries.append(boundary)

    def _on_failure(self) -> None:
        self._consecutive_failures += 1
        self._last_failure_time = time.time()
        logger.warning(
            "Auto Compact failure #%d/%d (circuit breaker)",
            self._consecutive_failures,
            self._config.circuit_breaker_limit,
        )

    def _suppress_warnings(self, duration: float = 30.0) -> None:
        self._suppressed_until = time.time() + duration

    def is_warning_suppressed(self) -> bool:
        return time.time() < self._suppressed_until

    def reset_circuit_breaker(self) -> None:
        self._consecutive_failures = 0

    def get_history(self) -> list[CompactBoundary]:
        return list(self._boundaries)

    def get_last_boundary(self) -> CompactBoundary | None:
        return self._boundaries[-1] if self._boundaries else None

__all__ = ["AutoCompactDispatcher"]
