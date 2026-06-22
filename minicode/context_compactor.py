"""Compatibility facade for :mod:`minicode.context.compaction`."""

from minicode.context.compaction import (
    AutoCompactConfig,
    AutoCompactDispatcher,
    CompactBoundary,
    CompactStrategy,
    CompactTrigger,
    CompactionResult,
    ContextCompactor,
    MicrocompactEngine,
    MicrocompactState,
    ReactiveCompactEngine,
    ReadDedupEntry,
    ReadDedupManager,
    SessionMemoryCompactEngine,
    ToolResultBudgetManager,
    ToolResultPersisted,
)

__all__ = [
    "AutoCompactConfig",
    "AutoCompactDispatcher",
    "CompactBoundary",
    "CompactStrategy",
    "CompactTrigger",
    "CompactionResult",
    "ContextCompactor",
    "MicrocompactEngine",
    "MicrocompactState",
    "ReactiveCompactEngine",
    "ReadDedupEntry",
    "ReadDedupManager",
    "SessionMemoryCompactEngine",
    "ToolResultBudgetManager",
    "ToolResultPersisted",
]
