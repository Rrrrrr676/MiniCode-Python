"""Compaction data models and policy enums."""
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
class CompactTrigger(str, Enum):
    """How the compaction was triggered."""
    MANUAL = "manual"
    AUTO = "auto"
    REACTIVE = "reactive"
    MICROCOMPACT_TIME = "microcompact_time"
    MICROCOMPACT_CACHED = "microcompact_cached"

class CompactStrategy(str, Enum):
    """Compaction strategy used."""
    SESSION_MEMORY = "session_memory"
    FULL = "full"
    PARTIAL = "partial"
    MICROCOMPACT = "microcompact"
    TOOL_BUDGET = "tool_budget"
    READ_DEDUP = "read_dedup"
    REACTIVE = "reactive"

@dataclass
class CompactBoundary:
    """Marks a compaction point in conversation history.

    After compaction, the active context view starts from the last boundary.
    The boundary itself is metadata, not model-visible content.
    """
    trigger: CompactTrigger
    strategy: CompactStrategy
    timestamp: float = field(default_factory=time.time)
    tokens_before: int = 0
    tokens_after: int = 0
    messages_removed: int = 0
    logical_parent_id: str | None = None
    preserved_segment: tuple[int, int] | None = None  # (start, end) message indices kept

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger.value,
            "strategy": self.strategy.value,
            "timestamp": self.timestamp,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "messages_removed": self.messages_removed,
            "logical_parent_id": self.logical_parent_id,
            "preserved_segment": list(self.preserved_segment) if self.preserved_segment else None,
        }

@dataclass
class CompactionResult:
    """Result of a compaction operation."""
    success: bool
    strategy: CompactStrategy
    trigger: CompactTrigger
    messages: list[dict[str, Any]]
    boundary: CompactBoundary | None = None
    tokens_freed: int = 0
    summary_text: str = ""
    error: str = ""

    @property
    def effective(self) -> bool:
        return self.success and self.tokens_freed > 0

@dataclass
class ToolResultPersisted:
    """A tool result that was persisted to disk."""
    original_size: int
    persisted_path: Path
    preview_text: str
    tool_name: str
    timestamp: float = field(default_factory=time.time)

@dataclass
class ReadDedupEntry:
    """Tracks a file read for deduplication."""
    file_path: str
    content_hash: str
    timestamp: float
    message_index: int  # Index in messages where full content lives

@dataclass
class MicrocompactState:
    """State for microcompact operations."""
    last_time_based_compact: float = 0.0
    time_based_interval: float = 3600.0  # Default 1 hour
    keep_recent_tool_results: int = 5
    total_tokens_cleared: int = 0

@dataclass
class AutoCompactConfig:
    """Configuration for Auto Compact dispatcher."""
    enabled: bool = True
    threshold_ratio: float = 0.85  # 85% of context window
    circuit_breaker_limit: int = 3
    circuit_breaker_recovery_seconds: float = 300.0  # auto-recover after this long
    session_memory_enabled: bool = True
    min_keep_tokens: int = 10000  # At least 10k tokens after compact
    min_keep_messages: int = 5  # At least 5 text messages
    max_expand_tokens: int = 40000  # Max expansion for tail preservation

__all__ = ['CompactTrigger', 'CompactStrategy', 'CompactBoundary', 'CompactionResult', 'ToolResultPersisted', 'ReadDedupEntry', 'MicrocompactState', 'AutoCompactConfig']
