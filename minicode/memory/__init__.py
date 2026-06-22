"""Layered memory public API and legacy import compatibility."""

from minicode.memory.manager import (
    _CODE_TERM_EXPANSIONS,
    _auto_classify_content,
    _expand_query_terms,
    _tokenize,
    MemoryEntry,
    MemoryFile,
    MemoryManager,
    MemoryPaths,
    MemoryScope,
    MemoryTier,
    format_memory_list,
    get_tfidf_keywords,
    inject_memory_into_prompt,
)

# Historical tests and integrations imported these implementation helpers
# directly. Keep them addressable during the compatibility window, while they
# remain excluded from the documented public ``__all__`` surface.

__all__ = [
    "MemoryEntry",
    "MemoryFile",
    "MemoryManager",
    "MemoryPaths",
    "MemoryScope",
    "MemoryTier",
    "format_memory_list",
    "get_tfidf_keywords",
    "inject_memory_into_prompt",
]
