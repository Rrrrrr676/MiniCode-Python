"""Memory scope, tier, entry, file, and path models."""
from __future__ import annotations

import functools
import json
import logging
import math
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from minicode.config import MINI_CODE_DIR

logger = logging.getLogger(__name__)

from .retrieval import *

class MemoryScope(str, Enum):
    """Memory scope levels."""
    USER = "user"       # Cross-project, ~/.mini-code/memory/
    PROJECT = "project" # Project-shared, .mini-code-memory/
    LOCAL = "local"     # Project-local, .mini-code-memory-local/

class MemoryTier(str, Enum):
    """Memory tier for multi-level storage architecture.

    Inspired by human memory models (Atkinson-Shiffrin) and Letta/MemGPT:
      WORKING    → current session, full detail, fast access
      SHORT_TERM → recent (< 7 days), full detail
      LONG_TERM  → consolidated (< 30 days), compressed
      ARCHIVAL   → permanent, heavily summarized
    """
    WORKING = "working"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    ARCHIVAL = "archival"

@dataclass
class MemoryEntry:
    """A single memory entry (fact, pattern, decision, etc.)."""
    id: str
    scope: MemoryScope
    category: str  # e.g., "architecture", "convention", "decision", "pattern"
    content: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    usage_count: int = 0  # How often this was referenced
    domains: list[str] = field(default_factory=list)  # Domain classification
    # Multi-tier memory architecture
    tier: MemoryTier = MemoryTier.SHORT_TERM
    last_accessed: float = field(default_factory=time.time)
    related_to: list[str] = field(default_factory=list)  # Related memory IDs
    _cached_tokens: list[str] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # `content` is accessed as a str throughout search/scoring/formatting
        # (8+ sites use .lower()/.strip()/[:N]); coerce None/non-str at
        # construction so a malformed entry can't crash a memory search, which
        # is injected into every system prompt.
        if not isinstance(self.content, str):
            self.content = "" if self.content is None else str(self.content)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MemoryEntry):
            return NotImplemented
        return self.id == other.id

    def get_tokens(self) -> list[str]:
        if self._cached_tokens is None:
            text = f"{self.content} {self.category} {' '.join(self.tags)}"
            self._cached_tokens = _tokenize(text)
        return self._cached_tokens

    def invalidate_tokens(self) -> None:
        self._cached_tokens = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "scope": self.scope.value,
            "category": self.category,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "usage_count": self.usage_count,
            "domains": self.domains,
            "tier": self.tier.value,
            "last_accessed": self.last_accessed,
            "related_to": self.related_to,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            scope=MemoryScope(data.get("scope", "user")),
            category=data.get("category", "general"),
            content=data["content"],
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            tags=data.get("tags", []),
            usage_count=data.get("usage_count", 0),
            domains=data.get("domains", []),
            tier=MemoryTier(data.get("tier", "short_term")),
            last_accessed=data.get("last_accessed", time.time()),
            related_to=data.get("related_to", []),
        )

@dataclass
class MemoryFile:
    """Represents a MEMORY.md file content with indexed lookups."""
    scope: MemoryScope
    entries: list[MemoryEntry] = field(default_factory=list)
    max_entries: int = 200  # Claude Code limit
    max_size_bytes: int = 25 * 1024  # 25KB limit
    _id_index: dict[str, MemoryEntry] = field(default_factory=dict, repr=False)
    _tag_index: dict[str, set[MemoryEntry]] = field(default_factory=dict, repr=False)
    _category_index: dict[str, list[MemoryEntry]] = field(default_factory=dict, repr=False)
    _tokens_cache: dict[str, list[str]] = field(default_factory=dict, repr=False)
    _idf_cache: dict[str, float] | None = field(default=None, repr=False)
    _avgdl_cache: float | None = field(default=None, repr=False)
    _cache_dirty: bool = field(default=True, repr=False)

    def _rebuild_indices(self) -> None:
        self._id_index.clear()
        self._tag_index.clear()
        self._category_index.clear()
        self._tokens_cache.clear()
        for entry in self.entries:
            self._id_index[entry.id] = entry
            for tag in entry.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(entry)
            cat = entry.category
            if cat not in self._category_index:
                self._category_index[cat] = []
            self._category_index[cat].append(entry)
            self._tokens_cache[entry.id] = entry.get_tokens()
        # Precompute IDF and avgdl
        if self._tokens_cache:
            all_tokens = list(self._tokens_cache.values())
            self._idf_cache = _compute_idf(all_tokens)
            self._avgdl_cache = _compute_avgdl(all_tokens)
        self._cache_dirty = False

    def _ensure_cache_valid(self) -> None:
        if self._cache_dirty:
            self._rebuild_indices()

    def _invalidate_cache(self) -> None:
        self._cache_dirty = True
        self._idf_cache = None
        self._avgdl_cache = None

    @property
    def size_bytes(self) -> int:
        """Estimate size in bytes."""
        return sum(len(e.content) for e in self.entries)

    def add_entry(self, entry: MemoryEntry) -> None:
        """Add entry, respecting limits. Maintains indices incrementally."""
        self._ensure_cache_valid()
        self.entries.append(entry)
        self._id_index[entry.id] = entry
        for tag in entry.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(entry)
        cat = entry.category
        if cat not in self._category_index:
            self._category_index[cat] = []
        self._category_index[cat].append(entry)
        self._tokens_cache[entry.id] = entry.get_tokens()
        self._enforce_limits()

    def update_entry(self, entry_id: str, content: str) -> bool:
        """Update existing entry using index."""
        self._ensure_cache_valid()
        entry = self._id_index.get(entry_id)
        if entry is None:
            return False
        entry.content = content
        entry.updated_at = time.time()
        entry.invalidate_tokens()
        self._tokens_cache[entry.id] = entry.get_tokens()
        return True

    def delete_entry(self, entry_id: str) -> bool:
        """Delete entry using index."""
        self._ensure_cache_valid()
        entry = self._id_index.get(entry_id)
        if entry is None:
            return False
        self.entries.remove(entry)
        del self._id_index[entry_id]
        for tag in entry.tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(entry)
        cat = entry.category
        if cat in self._category_index and entry in self._category_index[cat]:
            self._category_index[cat].remove(entry)
        self._tokens_cache.pop(entry_id, None)
        return True

    def get_entries_by_category(self, category: str) -> list[MemoryEntry]:
        """Get entries filtered by category using index."""
        self._ensure_cache_valid()
        return list(self._category_index.get(category, []))

    def search(self, query: str, active_domains: list[str] | None = None) -> list[MemoryEntry]:
        """Search entries by keyword with BM25 + domain relevance scoring.

        Combines BM25 semantic relevance with usage frequency and optional
        domain-based boosting (soft blend, not hard filtering).
        Domain score uses Jaccard similarity between entry domains and active domains.
        """
        if not self.entries:
            return []

        # Snapshot entries so concurrent add_entry/_enforce_limits can't shift
        # indices between the two loops below (was: "list index out of range"
        # when another thread appended between building entry_tokens and the
        # scoring loop).
        entries = list(self.entries)

        query_tokens = _tokenize(query)
        query_tokens = _expand_query_terms(query_tokens, active_domains=active_domains)
        if not query_tokens:
            return []

        query_lower = query.lower()
        query_terms = query_lower.split()

        entry_tokens = []
        for entry in entries:
            text = f"{entry.content} {entry.category} {' '.join(entry.tags)}"
            entry_tokens.append(_tokenize(text))

        idf = _compute_idf(entry_tokens)
        avgdl = _compute_avgdl(entry_tokens)

        scored: list[tuple[float, MemoryEntry]] = []
        for i, entry in enumerate(entries):
            bm25 = _bm25_score(query_tokens, entry_tokens[i], idf, avgdl)

            substring_score = 0.0
            content_lower = entry.content.lower()
            if query_lower in content_lower:
                substring_score = 2.0
            elif any(q in content_lower for q in query_terms):
                substring_score = 1.0

            tag_score = 0.0
            exact_tag_match = any(
                tag.lower() == query_lower for tag in entry.tags
            )
            partial_tag_match = any(
                query_lower in tag.lower() for tag in entry.tags
            )
            if exact_tag_match:
                tag_score = 5.0
            elif partial_tag_match:
                tag_score = 1.5
            if query_lower in entry.category.lower():
                tag_score += 1.0

            match_score = bm25 + substring_score + tag_score
            if match_score <= 0:
                continue

            # Domain score: Jaccard similarity between entry.domains and active_domains
            domain_score = 0.0
            if active_domains and entry.domains:
                entry_set = set(entry.domains)
                active_set = set(active_domains)
                intersection = entry_set & active_set
                union = entry_set | active_set
                domain_score = len(intersection) / len(union) if union else 0.0

            # Soft blend: BM25 dominates, domain provides light steering
            final_relevance = match_score * 0.7 + domain_score * 0.3

            usage_bonus = math.log1p(entry.usage_count) * 0.3
            age_hours = (time.time() - entry.updated_at) / 3600
            recency_bonus = 1.0 / (1.0 + age_hours / 24.0) * 0.5

            total_score = final_relevance + usage_bonus + recency_bonus
            scored.append((total_score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        # Increment usage_count for top results to feed back into future scoring
        for _, entry in scored[:10]:
            entry.usage_count += 1
        return [entry for _, entry in scored]

    def _enforce_limits(self) -> None:
        """Remove oldest entries if exceeding limits."""
        # Check entry count
        while len(self.entries) > self.max_entries:
            self.entries.pop(0)  # Remove oldest

        # Check size
        while self.size_bytes > self.max_size_bytes and self.entries:
            self.entries.pop(0)

    def format_as_markdown(self, include_header: bool = True) -> str:
        """Format as MEMORY.md content."""
        lines = []

        if include_header:
            scope_names = {
                MemoryScope.USER: "User Memory",
                MemoryScope.PROJECT: "Project Memory",
                MemoryScope.LOCAL: "Local Memory",
            }
            lines.append(f"# {scope_names[self.scope]}")
            lines.append("")
            lines.append(f"*Last updated: {time.strftime('%Y-%m-%d %H:%M')}*")
            lines.append("")

        # Group by category
        categories: dict[str, list[MemoryEntry]] = {}
        for entry in self.entries:
            if entry.category not in categories:
                categories[entry.category] = []
            categories[entry.category].append(entry)

        for category, entries in categories.items():
            lines.append(f"## {category.title()}")
            lines.append("")
            for entry in entries:
                tags_str = f" `{' '.join(entry.tags)}`" if entry.tags else ""
                lines.append(f"- {entry.content}{tags_str}")
            lines.append("")

        return "\n".join(lines)

@dataclass
class MemoryPaths:
    """Paths for memory files at different scopes."""
    user_memory: Path
    project_memory: Path
    local_memory: Path

    @classmethod
    def for_workspace(cls, workspace: str) -> "MemoryPaths":
        """Create memory paths for a workspace."""
        workspace_path = Path(workspace)

        return cls(
            user_memory=MINI_CODE_DIR / "memory",
            project_memory=workspace_path / ".mini-code-memory",
            local_memory=workspace_path / ".mini-code-memory-local",
        )

__all__ = ['MemoryScope', 'MemoryTier', 'MemoryEntry', 'MemoryFile', 'MemoryPaths']
