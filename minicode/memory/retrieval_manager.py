"""MemoryManager retrieval orchestration."""
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

from .models import *
from .retrieval import *

class MemoryRetrievalMixin:
    def search_by_tag(self, scope: MemoryScope, tag: str) -> list[MemoryEntry]:
        """Search entries by tag."""
        return [
            entry for entry in self.memories[scope].entries
            if tag in entry.tags
        ]

    def get_all_tags(self, scope: MemoryScope) -> set[str]:
        """Get all unique tags in a scope."""
        tags: set[str] = set()
        for entry in self.memories[scope].entries:
            tags.update(entry.tags)
        return tags

    def get_tags_by_category(self, scope: MemoryScope) -> dict[str, list[str]]:
        """Get tags grouped by category."""
        category_tags: dict[str, set[str]] = {}
        for entry in self.memories[scope].entries:
            if entry.category not in category_tags:
                category_tags[entry.category] = set()
            category_tags[entry.category].update(entry.tags)
        return {cat: sorted(list(tags)) for cat, tags in category_tags.items()}

    def search(
        self,
        query: str,
        scope: MemoryScope | None = None,
        limit: int = 20,
        min_relevance: float = 0.1,
        active_domains: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Search across memory scopes with TF-IDF + domain relevance.

        Args:
            query: Search query string
            scope: Optional scope to limit search to
            limit: Maximum results to return
            min_relevance: Minimum relevance score threshold (0.0-1.0)
            active_domains: Current domain context for soft boosting

        Returns:
            Entries ranked by relevance (TF-IDF + domain + usage + recency)
        """
        results = []

        scopes_to_search = [scope] if scope else list(MemoryScope)

        for s in scopes_to_search:
            results.extend(self.memories[s].search(query, active_domains=active_domains))

        # Apply minimum relevance threshold
        # (entries are already scored by MemoryFile.search)
        if min_relevance > 0:
            # Normalize scores to 0-1 range for threshold comparison
            if results:
                max_score = max(
                    self._score_entry(e, _tokenize(query)) for e in results
                )
                if max_score > 0:
                    results = [
                        e for e in results
                        if self._score_entry(e, _tokenize(query)) / max_score >= min_relevance
                    ]

        # Results are already ranked by MemoryFile.search()
        # Deduplicate by content (keep highest-scored)
        seen_content: set[str] = set()
        deduped = []
        for entry in results:
            content_key = entry.content[:100].strip().lower()
            if content_key not in seen_content:
                seen_content.add(content_key)
                deduped.append(entry)

        return deduped[:limit]

    def _score_entry(self, entry: MemoryEntry, query_tokens: list[str]) -> float:
        """Compute relevance score for a memory entry."""
        if not query_tokens:
            return 0.0

        query_tokens_expanded = _expand_query_terms(query_tokens)
        entry_tokens = _tokenize(
            f"{entry.content} {entry.category} {' '.join(entry.tags)}"
        )
        idf = _compute_idf([entry_tokens])
        avgdl = len(entry_tokens)
        bm25 = _bm25_score(query_tokens_expanded, entry_tokens, idf, avgdl)

        query_lower = " ".join(query_tokens).lower()
        content_lower = entry.content.lower()
        substring_score = 0.0
        if query_lower in content_lower:
            substring_score = 2.0
        elif any(q in content_lower for q in query_tokens):
            substring_score = 1.0

        tag_score = 0.0
        exact_tag_match = any(tag.lower() == query_lower for tag in entry.tags)
        partial_tag_match = any(query_lower in tag.lower() for tag in entry.tags)
        if exact_tag_match:
            tag_score = 5.0
        elif partial_tag_match:
            tag_score = 1.5
        if query_lower in entry.category.lower():
            tag_score += 1.0

        usage_bonus = math.log1p(entry.usage_count) * 0.3

        age_hours = (time.time() - entry.updated_at) / 3600
        recency_bonus = 1.0 / (1.0 + age_hours / 24.0) * 0.5

        return bm25 + substring_score + tag_score + usage_bonus + recency_bonus

    def get_relevant_context(
        self,
        max_entries: int = 20,
        max_tokens: int = 8000,
        query: str | None = None,
    ) -> str:
        """Get relevant memory context for system prompt injection.

        Returns formatted MEMORY.md content from all scopes,
        respecting token limits.
        """
        from minicode.context.tokens import estimate_tokens

        query = (query or "").strip()
        if query:
            scoped_parts = []
            total_tokens = 0
            for scope in [MemoryScope.LOCAL, MemoryScope.PROJECT, MemoryScope.USER]:
                entries = self.search(query, scope=scope, limit=max_entries, min_relevance=0.0)
                if not entries:
                    continue
                accepted_entries: list[MemoryEntry] = []
                for entry in entries[:max_entries]:
                    candidate_memory = MemoryFile(scope=scope, entries=[*accepted_entries, entry])
                    candidate = candidate_memory.format_as_markdown(include_header=True)
                    candidate_tokens = estimate_tokens(candidate)
                    if total_tokens + candidate_tokens <= max_tokens:
                        accepted_entries.append(entry)
                        continue
                    if not accepted_entries:
                        # Skip an oversized match instead of blocking lower-priority
                        # scopes that may have compact, relevant context.
                        continue
                    break
                if not accepted_entries:
                    continue
                formatted = MemoryFile(scope=scope, entries=accepted_entries).format_as_markdown(include_header=True)
                scoped_parts.append(formatted)
                total_tokens += estimate_tokens(formatted)
            if scoped_parts:
                return "\n\n".join(scoped_parts)
            return ""

        parts = []
        total_tokens = 0

        # Priority order: LOCAL > PROJECT > USER
        for scope in [MemoryScope.LOCAL, MemoryScope.PROJECT, MemoryScope.USER]:
            memory = self.memories[scope]
            if not memory.entries:
                continue

            formatted = memory.format_as_markdown(include_header=True)
            tokens = estimate_tokens(formatted)

            if total_tokens + tokens <= max_tokens:
                parts.append(formatted)
                total_tokens += tokens
            else:
                # Partial: include only recent entries
                remaining_tokens = max_tokens - total_tokens
                partial_entries = memory.entries[-max_entries:]
                partial_memory = MemoryFile(scope=scope, entries=partial_entries)
                formatted = partial_memory.format_as_markdown(include_header=True)

                if estimate_tokens(formatted) <= remaining_tokens:
                    parts.append(formatted)
                break

        if not parts:
            return ""

        return "\n\n".join(parts)

__all__ = ["MemoryRetrievalMixin"]
