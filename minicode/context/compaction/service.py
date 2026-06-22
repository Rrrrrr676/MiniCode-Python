"""Public context compaction service composition."""
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
from .budgets import ToolResultBudgetManager
from .micro import MicrocompactEngine, ReadDedupManager
from .dispatcher import AutoCompactDispatcher
from .reactive import ReactiveCompactEngine

class ContextCompactor:
    """Unified context management orchestrator.

    Implements the complete Claude Code-style pipeline:

    Step 1: Construct active context (from last boundary)
    Step 2: Apply tool result budget
    Step 3: Read dedup
    Step 4: Microcompact
    Step 5: Auto Compact high-water check
    Step 6: Dispatch (Session Memory → Full)
    Step 7: Reactive recovery (if needed)
    """

    def __init__(
        self,
        context_window: int = 200000,
        workspace: str | Path | None = None,
        memory_manager=None,
        estimate_fn=None,
        config: AutoCompactConfig | None = None,
    ):
        self._context_window = context_window
        self._workspace = Path(workspace) if workspace else Path.cwd()
        self._config = config or AutoCompactConfig()

        self._tool_budget = ToolResultBudgetManager(workspace)
        self._read_dedup = ReadDedupManager()
        self._microcompact = MicrocompactEngine()
        self._auto_compact = AutoCompactDispatcher(
            context_window=context_window,
            config=config,
            memory_manager=memory_manager,
            estimate_fn=estimate_fn,
        )
        self._reactive = ReactiveCompactEngine(self._auto_compact, estimate_fn)
        self._estimate = estimate_fn or (lambda m: len(str(m)) // 4)

        self._last_compact_result: CompactionResult | None = None
        self._total_optimization_passes = 0

    def process_request(
        self,
        messages: list[dict[str, Any]],
        *,
        enable_tool_budget: bool = True,
        enable_read_dedup: bool = True,
        enable_microcompact: bool = True,
        enable_auto_compact: bool = True,
    ) -> CompactionResult:
        """Run the full pre-request optimization pipeline.

        This is the main entry point called before each API request.
        """
        self._total_optimization_passes += 1
        current = list(messages)
        total_freed = 0
        steps_taken = []

        # Step 2: Tool Result Budget
        if enable_tool_budget:
            current, budget_saved = self._tool_budget.check_and_replace(current)
            if budget_saved > 0:
                total_freed += budget_saved
                steps_taken.append(f"tool_budget({budget_saved})")

        # Step 3: Read Dedup (handled at tool level, but we track state)
        # Read dedup is primarily used when processing tool results

        # Step 4: Microcompact
        if enable_microcompact:
            mc_result = self._microcompact.run_time_based_microcompact(current)
            if mc_result.effective:
                current = mc_result.messages
                total_freed += mc_result.tokens_freed
                steps_taken.append(f"microcompact({mc_result.tokens_freed})")

        # Step 5+6: Auto Compact high-water dispatch
        if enable_auto_compact and self._auto_compact.should_trigger(current):
            ac_result = self._auto_compact.dispatch(current)
            if ac_result.effective:
                current = ac_result.messages
                total_freed += ac_result.tokens_freed
                steps_taken.append(f"auto_compact({ac_result.strategy.value},{ac_result.tokens_freed})")
                self._last_compact_result = ac_result

        result = CompactionResult(
            success=total_freed > 0,
            strategy=CompactStrategy.FULL,
            trigger=CompactTrigger.AUTO,
            messages=current,
            tokens_freed=total_freed,
            summary_text=f"Optimization steps: {' + '.join(steps_taken)}" if steps_taken else "",
        )

        logger.info(
            "ContextCompactor pass #%d: %d tokens freed across [%s]",
            self._total_optimization_passes,
            total_freed,
            ", ".join(steps_taken) if steps_taken else "none",
        )

        return result

    def reactive_recover(
        self, messages: list[dict[str, Any]], error: str = ""
    ) -> CompactionResult | None:
        """Attempt reactive recovery after API error."""
        return self._reactive.try_recover_from_overflow(messages, error)

    @property
    def tool_budget(self) -> ToolResultBudgetManager:
        return self._tool_budget

    @property
    def read_dedup(self) -> ReadDedupManager:
        return self._read_dedup

    @property
    def auto_compact(self) -> AutoCompactDispatcher:
        return self._auto_compact

    @property
    def reactive(self) -> ReactiveCompactEngine:
        return self._reactive

    @property
    def last_result(self) -> CompactionResult | None:
        return self._last_compact_result

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_passes": self._total_optimization_passes,
            "tool_results_persisted": self._tool_budget.get_persisted_count(),
            "tool_bytes_saved": self._tool_budget.get_total_saved_bytes(),
            "read_dedup_entries": len(self._read_dedup._entries),
            "microcompact_tokens_cleared": self._microcompact._state.total_tokens_cleared,
            "auto_compact_boundaries": len(self._auto_compact.get_history()),
            "circuit_breaker_tripped": self._auto_compact.is_tripped,
            "reactive_recovery_attempts": self._reactive._recovery_attempts,
            "context_window": self._context_window,
            "auto_compact_threshold": self._auto_compact.threshold_tokens,
        }

    def format_pipeline_status(self) -> str:
        stats = self.get_stats()
        lines = [
            "Context Management Pipeline Status",
            "=" * 40,
            f"Optimization passes: {stats['total_passes']}",
            f"Tool results persisted: {stats['tool_results_persisted']} ({stats['tool_bytes_saved']} bytes saved)",
            f"Read dedup cache: {stats['read_dedup_entries']} files",
            f"Microcompact cleared: ~{stats['microcompact_tokens_cleared']} tokens",
            f"Compact boundaries: {stats['auto_compact_boundaries']}",
            f"Circuit breaker: {'TRIPPED' if stats['circuit_breaker_tripped'] else 'OK'}",
            f"Reactive recoveries: {stats['reactive_recovery_attempts']}",
            "",
            f"Context window: {stats['context_window']:,} tokens",
            f"Auto compact threshold: {stats['auto_compact_threshold']:,} tokens ({self._config.threshold_ratio:.0%})",
        ]
        return "\n".join(lines)

__all__ = ["ContextCompactor"]
