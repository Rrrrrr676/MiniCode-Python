"""Compatibility facade for minicode.context.working."""

import sys as _sys
from minicode.context import working as _implementation

_implementation.__all__ = ["ContinuityMarker","ConversationContinuityManager","WorkingMemoryEntry","WorkingMemoryTracker","get_continuity_manager","get_working_memory","mark_continuity","protect_context"]
_sys.modules[__name__] = _implementation

from minicode.context.working import (
    ContinuityMarker,
    ConversationContinuityManager,
    WorkingMemoryEntry,
    WorkingMemoryTracker,
    get_continuity_manager,
    get_working_memory,
    mark_continuity,
    protect_context,
)

__all__ = [
    "ContinuityMarker",
    "ConversationContinuityManager",
    "WorkingMemoryEntry",
    "WorkingMemoryTracker",
    "get_continuity_manager",
    "get_working_memory",
    "mark_continuity",
    "protect_context",
]
