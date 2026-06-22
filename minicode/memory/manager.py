"""Layered memory business orchestration and maintenance."""
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
from .storage import MemoryStorageMixin
from .retrieval_manager import MemoryRetrievalMixin
from .prompt import format_memory_list, inject_memory_into_prompt


class MemoryManager(MemoryStorageMixin, MemoryRetrievalMixin):
    """Manage layered memory while delegating storage and retrieval boundaries."""

    def __init__(
        self,
        workspace: str | Path | None = None,
        *,
        project_root: str | Path | None = None,
    ):
        # Backward compatibility: older call sites pass `project_root=...`.
        resolved_workspace = workspace if workspace is not None else project_root
        if resolved_workspace is None:
            resolved_workspace = Path.cwd()

        self.workspace = str(resolved_workspace)
        self.paths = MemoryPaths.for_workspace(self.workspace)
        self.memories: dict[MemoryScope, MemoryFile] = {
            MemoryScope.USER: MemoryFile(scope=MemoryScope.USER),
            MemoryScope.PROJECT: MemoryFile(scope=MemoryScope.PROJECT),
            MemoryScope.LOCAL: MemoryFile(scope=MemoryScope.LOCAL),
        }
        self._load_all()

    def add_entry(
        self,
        scope: MemoryScope,
        category: str = "auto",
        content: str = "",
        tags: list[str] | None = None,
    ) -> MemoryEntry:
        """Add a new memory entry.

        If category is 'auto' or not provided, content will be automatically
        classified using keyword heuristics.

        Args:
            scope: Memory scope level
            category: Category for the entry, or 'auto' for auto-classification
            content: Content of the memory entry
            tags: Optional list of tags

        Returns:
            The created MemoryEntry
        """
        self._ensure_scope_path(scope)

        final_category = category
        final_tags = tags or []

        if category == "auto" and content:
            auto_category, auto_tags = _auto_classify_content(content)
            final_category = auto_category
            final_tags = list(dict.fromkeys(final_tags + auto_tags))

        entry_id = f"{scope.value}-{int(time.time())}-{len(self.memories[scope].entries)}"
        entry = MemoryEntry(
            id=entry_id,
            scope=scope,
            category=final_category,
            content=content,
            tags=final_tags,
        )

        self.memories[scope].add_entry(entry)
        self._save_scope(scope)
        return entry

    def update_entry(self, scope: MemoryScope, entry_id: str, content: str) -> bool:
        """Update an existing entry."""
        if self.memories[scope].update_entry(entry_id, content):
            self._save_scope(scope)
            return True
        return False

    def delete_entry(self, scope: MemoryScope, entry_id: str) -> bool:
        """Delete an entry."""
        if self.memories[scope].delete_entry(entry_id):
            self._save_scope(scope)
            return True
        return False

    def add_tag(self, scope: MemoryScope, entry_id: str, tag: str) -> bool:
        """Add a tag to an entry."""
        for entry in self.memories[scope].entries:
            if entry.id == entry_id:
                if tag not in entry.tags:
                    entry.tags.append(tag)
                    self._save_scope(scope)
                return True
        return False

    def remove_tag(self, scope: MemoryScope, entry_id: str, tag: str) -> bool:
        """Remove a tag from an entry."""
        for entry in self.memories[scope].entries:
            if entry.id == entry_id:
                if tag in entry.tags:
                    entry.tags.remove(tag)
                    self._save_scope(scope)
                return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        return {
            scope.value: {
                "entries": len(memory.entries),
                "size_bytes": memory.size_bytes,
                "categories": list(set(e.category for e in memory.entries)),
            }
            for scope, memory in self.memories.items()
        }

    def format_stats(self) -> str:
        """Format memory stats for display with tier and domain breakdown."""
        from collections import Counter

        lines = ["Memory System Status", "=" * 50, ""]
        tiers: Counter[str] = Counter()
        domains: Counter[str] = Counter()
        total_entries = 0
        total_size = 0
        insight_count = 0

        for scope_name, scope_stats in self.get_stats().items():
            lines.append(f"{scope_name.title()}: {scope_stats['entries']} entries, "
                        f"{scope_stats['size_bytes'] / 1024:.1f} KB")
            total_entries += scope_stats["entries"]
            total_size += scope_stats["size_bytes"]

            # Collect tier and domain stats
            scope = MemoryScope(scope_name)
            if scope in self.memories:
                for e in self.memories[scope].entries:
                    tiers[e.tier.value] += 1
                    for d in e.domains:
                        domains[d] += 1
                    if e.category == "insight":
                        insight_count += 1

        lines.append("")
        lines.append(f"Total: {total_entries} entries ({total_size / 1024:.1f} KB)")
        lines.append("")

        if tiers:
            lines.append("Tier Distribution:")
            for tier_name in ["working", "short_term", "long_term", "archival"]:
                count = tiers.get(tier_name, 0)
                bar = "#" * (count // max(1, total_entries // 20))
                lines.append(f"  {tier_name:<12} {count:>4} {bar}")
            lines.append("")

        if domains:
            lines.append("Domain Distribution:")
            for domain, count in domains.most_common(6):
                lines.append(f"  {domain:<15} {count:>3}")
            lines.append("")

        if insight_count:
            lines.append(f"Curator Insights: {insight_count} synthesized")

        return "\n".join(lines)

    def clear_scope(self, scope: MemoryScope) -> None:
        """Clear all entries in a scope."""
        self.memories[scope] = MemoryFile(scope=scope)
        self._save_scope(scope)

    def handle_user_memory_input(self, user_input: str) -> str | None:
        """Handle explicit memory inputs from the main chat path.

        Supported forms:
        - "# remember this project convention"
        - "/memory add remember this project convention"
        - "/memory add project: remember this shared project convention"
        - "/memory add local: remember this local-only note"
        - "/memory add user: remember this cross-project preference"
        """
        raw = user_input.strip()
        if not raw:
            return None

        content = ""
        scope = MemoryScope.PROJECT
        category = "note"

        if raw.startswith("#"):
            content = raw[1:].strip()
            category = "directive"
        elif raw.startswith("/memory add "):
            content = raw[len("/memory add ") :].strip()
            scope_match = re.match(r"^(user|project|local)\s*:\s*(.+)$", content, flags=re.I)
            if scope_match:
                scope = MemoryScope(scope_match.group(1).lower())
                content = scope_match.group(2).strip()
        else:
            return None

        if not content:
            return "Usage: # <memory> or /memory add [user|project|local:] <memory>"

        entry = self.add_entry(scope, category, content, tags=["chat"])
        return f"Saved memory ({entry.scope.value}): {entry.content}"

    def compress_scope(
        self, scope: MemoryScope, similarity_threshold: float = 0.8
    ) -> dict[str, int]:
        """Compress memory entries by merging similar content.

        Merges entries with content similarity above the threshold.
        Removes duplicate entries (exact content matches).
        Updates timestamps and preserves usage counts.

        Args:
            scope: Memory scope to compress
            similarity_threshold: Jaccard similarity threshold for merging
                (default 0.8 = 80%)

        Returns:
            Stats dictionary with {merged_count, removed_count, remaining_count}
        """
        entries = self.memories[scope].entries
        if len(entries) <= 1:
            return {"merged_count": 0, "removed_count": 0, "remaining_count": len(entries)}

        seen_content: dict[str, int] = {}
        duplicates_removed = 0

        unique_entries = []
        for entry in entries:
            content_key = entry.content.strip().lower()
            if content_key in seen_content:
                master_idx = seen_content[content_key]
                master = unique_entries[master_idx]
                master.usage_count += entry.usage_count
                master.updated_at = max(master.updated_at, entry.updated_at)
                master.tags = sorted(
                    list(set(master.tags + entry.tags))
                )
                duplicates_removed += 1
            else:
                seen_content[content_key] = len(unique_entries)
                unique_entries.append(entry)

        merged_count = 0
        final_entries: list[MemoryEntry] = []
        merged_indices: set[int] = set()

        for i, entry_a in enumerate(unique_entries):
            if i in merged_indices:
                continue

            best_match_idx = None
            best_similarity = 0.0

            for j, entry_b in enumerate(unique_entries):
                if i == j or j in merged_indices:
                    continue

                similarity = self._jaccard_similarity(
                    entry_a.content, entry_b.content
                )
                if similarity >= similarity_threshold and similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = j

            if best_match_idx is not None:
                entry_b = unique_entries[best_match_idx]
                merged_content = self._merge_entry_content(
                    entry_a.content, entry_b.content
                )
                entry_a.content = merged_content
                entry_a.usage_count += entry_b.usage_count
                entry_a.updated_at = max(
                    entry_a.updated_at, entry_b.updated_at
                )
                entry_a.tags = sorted(
                    list(set(entry_a.tags + entry_b.tags))
                )
                merged_indices.add(best_match_idx)
                merged_count += 1

            final_entries.append(entry_a)

        self.memories[scope].entries = final_entries
        self._save_scope(scope)

        return {
            "merged_count": merged_count,
            "removed_count": duplicates_removed,
            "remaining_count": len(final_entries),
        }

    @staticmethod
    def _jaccard_similarity(text_a: str, text_b: str) -> float:
        """Compute Jaccard similarity between two text strings.

        Uses token-based Jaccard similarity: |A ∩ B| / |A ∪ B|

        Args:
            text_a: First text string
            text_b: Second text string

        Returns:
            Similarity score between 0.0 and 1.0
        """
        tokens_a = set(_tokenize(text_a))
        tokens_b = set(_tokenize(text_b))

        if not tokens_a and not tokens_b:
            return 1.0
        if not tokens_a or not tokens_b:
            return 0.0

        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b

        return len(intersection) / len(union)

    @staticmethod
    def _merge_entry_content(content_a: str, content_b: str) -> str:
        """Merge two similar content strings.

        Keeps the longer version, appends unique parts from the shorter.

        Args:
            content_a: First content string
            content_b: Second content string

        Returns:
            Merged content string
        """
        if len(content_a) >= len(content_b):
            return content_a
        return content_b

    def detect_conflicts(self, content: str, scope: MemoryScope | None = None, threshold: float = 0.6) -> list[tuple[MemoryEntry, float]]:
        """Detect potential conflicts between new content and existing memories.

        Uses Jaccard similarity on token sets to identify entries that may
        contradict or overlap with the proposed new memory content.

        Args:
            content: New memory content to check for conflicts
            scope: Scope to check (None = all scopes)
            threshold: Similarity threshold for conflict flagging (0.0-1.0)

        Returns:
            List of (entry, similarity) tuples sorted by similarity descending
        """
        new_tokens = set(_tokenize(content))
        if not new_tokens:
            return []

        conflicts: list[tuple[MemoryEntry, float]] = []
        scopes = [scope] if scope else list(MemoryScope)

        for s in scopes:
            if s not in self.memories:
                continue
            for entry in self.memories[s].entries:
                old_tokens = set(entry.get_tokens())
                if not old_tokens:
                    continue
                intersection = new_tokens & old_tokens
                union = new_tokens | old_tokens
                similarity = len(intersection) / len(union) if union else 0.0
                if similarity >= threshold:
                    conflicts.append((entry, similarity))

        conflicts.sort(key=lambda x: x[1], reverse=True)
        return conflicts

    def decay_memories(self, max_age_days: float = 30.0, decay_factor: float = 0.5) -> int:
        """Apply time-based decay to memory usage_count.

        Entries older than max_age_days have their usage_count halved
        (multiplied by decay_factor), reducing their search ranking.
        Returns number of entries decayed.
        """
        now = time.time()
        decayed = 0
        for scope in MemoryScope:
            if scope not in self.memories:
                continue
            for entry in self.memories[scope].entries:
                age_days = (now - entry.updated_at) / 86400.0
                if age_days > max_age_days and entry.usage_count > 0:
                    entry.usage_count = max(0, int(entry.usage_count * decay_factor))
                    decayed += 1
        if decayed:
            for scope in MemoryScope:
                self._save_scope(scope)
        return decayed

    def promote_memories(self) -> dict[str, int]:
        """Promote/demote memories across tiers based on usage and age.

        WORKING → SHORT_TERM → LONG_TERM → ARCHIVAL
        Returns counts per operation.
        """
        now = time.time()
        stats = {"promoted_to_long": 0, "demoted_to_archival": 0, "reactivated": 0}
        for scope in MemoryScope:
            if scope not in self.memories:
                continue
            for entry in self.memories[scope].entries:
                age_days = (now - entry.updated_at) / 86400.0
                accessed_days = (now - entry.last_accessed) / 86400.0
                if entry.tier == MemoryTier.SHORT_TERM and entry.usage_count >= 5 and age_days > 7:
                    entry.tier = MemoryTier.LONG_TERM
                    stats["promoted_to_long"] += 1
                if entry.tier == MemoryTier.LONG_TERM and accessed_days > 30:
                    entry.tier = MemoryTier.ARCHIVAL
                    entry.content = self._summarize_content(entry.content)
                    stats["demoted_to_archival"] += 1
                if entry.tier in (MemoryTier.LONG_TERM, MemoryTier.ARCHIVAL) and accessed_days < 7:
                    entry.tier = MemoryTier.SHORT_TERM
                    stats["reactivated"] += 1
        if any(stats.values()):
            for scope in MemoryScope:
                self._save_scope(scope)
        return stats

    def link_memories(self, similarity_threshold: float = 0.4) -> int:
        """Auto-link related memories by content similarity. Returns link count."""
        links = 0
        for scope in MemoryScope:
            if scope not in self.memories:
                continue
            entries = self.memories[scope].entries
            for i, a in enumerate(entries):
                for j, b in enumerate(entries):
                    if i >= j:
                        continue
                    if b.id in a.related_to:
                        continue
                    if self._jaccard_similarity(a.content, b.content) >= similarity_threshold:
                        a.related_to.append(b.id)
                        b.related_to.append(a.id)
                        links += 2
        if links:
            for scope in MemoryScope:
                self._save_scope(scope)
        return links

    def get_linked_memories(self, entry_id: str, depth: int = 1) -> list[MemoryEntry]:
        """Get memories linked to entry_id via related_to graph (BFS up to depth)."""
        entry = None
        found_scope = None
        for s in MemoryScope:
            if s in self.memories:
                entry = self.memories[s]._id_index.get(entry_id)
                if entry:
                    found_scope = s
                    break
        if not entry or not entry.related_to or not found_scope:
            return []
        visited = {entry_id}
        frontier = list(entry.related_to)
        results = []
        for _ in range(depth):
            nxt = []
            for rid in frontier:
                if rid in visited:
                    continue
                visited.add(rid)
                linked = self.memories[found_scope]._id_index.get(rid)
                if linked:
                    results.append(linked)
                    nxt.extend(linked.related_to)
            frontier = nxt
            if not frontier:
                break
        return results

    @staticmethod
    def _summarize_content(content: str, max_len: int = 150) -> str:
        if len(content) <= max_len:
            return content
        for sep in [". ", ".\n", "; ", ";\n", "\n"]:
            idx = content.find(sep)
            if 20 < idx < max_len:
                return content[:idx + 1]
        return content[:max_len] + "..."

    def _find_entry_indices(self, scope: MemoryScope, entry_id: str) -> list[int]:
        """Find all indices of entries with a given ID."""
        indices = []
        for idx, entry in enumerate(self.memories[scope].entries):
            if entry.id == entry_id:
                indices.append(idx)
        return indices

__all__ = ["MemoryManager", "MemoryEntry", "MemoryFile", "MemoryPaths", "MemoryScope", "MemoryTier", "format_memory_list", "get_tfidf_keywords", "inject_memory_into_prompt"]
