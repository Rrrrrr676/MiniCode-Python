"""Context compaction policies and implementations."""

from minicode.context.compaction.dispatcher import (
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
