"""Reactive prompt-overflow recovery."""
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
from .dispatcher import AutoCompactDispatcher

class ReactiveCompactEngine:
    """Error recovery compaction for post-API-failure scenarios.

    Triggered when the model API rejects a request due to:
    - prompt too long
    - media size exceeded
    - other recoverable errors
    """

    MAX_RETRIES = 3

    def __init__(
        self,
        auto_compact: AutoCompactDispatcher | None = None,
        estimate_fn=None,
    ):
        self._auto_compact = auto_compact
        self._estimate = estimate_fn or (lambda m: len(str(m)) // 4)
        self._recovery_attempts = 0

    def try_recover_from_overflow(
        self,
        messages: list[dict[str, Any]],
        error_message: str = "",
    ) -> CompactionResult | None:
        """Attempt recovery from prompt-too-long error.

        Strategy:
        1. Force Full Compact with aggressive truncation
        2. If still too long, drop oldest API round groups
        3. Up to MAX_RETRIES attempts
        """
        self._recovery_attempts += 1
        if self._recovery_attempts > self.MAX_RETRIES:
            logger.error("Reactive Compact: max retries (%d) exceeded", self.MAX_RETRIES)
            return None

        logger.info(
            "Reactive Compact attempt %d/%d: recovering from overflow",
            self._recovery_attempts,
            self.MAX_RETRIES,
        )

        # Use auto compact with force_full
        if self._auto_compact:
            # Temporarily reset circuit breaker for recovery
            original_tripped = self._auto_compact.is_tripped
            if original_tripped:
                self._auto_compact.reset_circuit_breaker()

            result = self._auto_compact.dispatch(messages, force_full=True)

            # Check if result is small enough
            result_usage = sum(self._estimate(m) for m in result.messages)
            if result_usage < self._auto_compact.blocking_limit * 0.9:
                self._recovery_attempts = 0  # Reset on success
                return CompactionResult(
                    success=True,
                    strategy=CompactStrategy.REACTIVE,
                    trigger=CompactTrigger.REACTIVE,
                    messages=result.messages,
                    boundary=result.boundary,
                    tokens_freed=result.tokens_freed,
                )

        # Aggressive fallback: truncate oldest messages directly
        # Only attempt if still within retry budget
        if self._recovery_attempts > self.MAX_RETRIES:
            logger.error("Reactive Compact: max retries (%d) exceeded in fallback", self.MAX_RETRIES)
            return None
        return self._aggressive_truncate(messages)

    def _aggressive_truncate(
        self, messages: list[dict[str, Any]]
    ) -> CompactionResult:
        """Aggressively truncate to fit within limits."""
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # Keep only most recent portion
        keep_ratio = 0.4 - (self._recovery_attempts * 0.1)  # Progressive truncation
        keep_count = max(3, int(len(non_system) * max(keep_ratio, 0.15)))

        truncated = list(system_msgs)
        truncated.append({
            "role": "system",
            "content": (
                f"[Context aggressively truncated for recovery — attempt {self._recovery_attempts}]\n"
                f"Earlier conversation was removed to fit context limits."
            ),
            "_reactive_compact": True,
        })
        truncated.extend(non_system[-keep_count:])

        boundary = CompactBoundary(
            trigger=CompactTrigger.REACTIVE,
            strategy=CompactStrategy.REACTIVE,
            tokens_before=sum(self._estimate(m) for m in messages),
            tokens_after=sum(self._estimate(m) for m in truncated),
            messages_removed=len(messages) - len(truncated),
        )

        return CompactionResult(
            success=True,
            strategy=CompactStrategy.REACTIVE,
            trigger=CompactTrigger.REACTIVE,
            messages=truncated,
            boundary=boundary,
            tokens_freed=boundary.tokens_before - boundary.tokens_after,
        )

__all__ = ["ReactiveCompactEngine"]
