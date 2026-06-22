"""Context compaction policies and implementations."""

from .budgets import ToolResultBudgetManager
from .dispatcher import AutoCompactDispatcher
from .micro import MicrocompactEngine, ReadDedupManager
from .models import (
    AutoCompactConfig,
    CompactBoundary,
    CompactStrategy,
    CompactTrigger,
    CompactionResult,
    MicrocompactState,
    ReadDedupEntry,
    ToolResultPersisted,
)
from .reactive import ReactiveCompactEngine
from .service import ContextCompactor
from .session_memory import SessionMemoryCompactEngine

__all__ = [name for name in globals() if not name.startswith("_")]
