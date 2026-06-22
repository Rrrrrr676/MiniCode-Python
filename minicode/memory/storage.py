"""Memory JSON validation, recovery, and atomic persistence."""
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

from .models import MemoryEntry, MemoryFile, MemoryScope

def _validate_memory_data(data: dict) -> tuple[bool, list[str]]:
    """Validate the structure of memory JSON data before loading.

    Checks for:
    - Required fields present (entries)
    - Valid enum values for scope
    - Valid data types for all entry fields

    Args:
        data: Parsed JSON data dictionary

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return False, ["Root data must be a dictionary"]

    if "entries" not in data:
        errors.append("Missing required field: 'entries'")
        return False, errors

    entries = data.get("entries")
    if not isinstance(entries, list):
        errors.append("'entries' must be a list")
        return False, errors

    for idx, entry_data in enumerate(entries):
        _, entry_errors = _validate_entry(entry_data, idx)
        errors.extend(entry_errors)

    return len(errors) == 0, errors

def _validate_entry(entry: Any, index: int) -> tuple[bool, list[str]]:
    """Validate a single memory entry dictionary.

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors: list[str] = []
    prefix = f"Entry at index {index}"

    if not isinstance(entry, dict):
        return False, [f"{prefix} is not a dictionary"]

    required_fields = ["id", "content"]
    for field_name in required_fields:
        if field_name not in entry:
            errors.append(f"{prefix} missing required field: '{field_name}'")

    if "id" in entry and not isinstance(entry["id"], str):
        errors.append(f"{prefix} field 'id' must be a string")

    if "scope" in entry:
        scope_val = entry["scope"]
        if not isinstance(scope_val, str):
            errors.append(f"{prefix} field 'scope' must be a string")
        elif scope_val not in {scope.value for scope in MemoryScope}:
            errors.append(
                f"{prefix} has invalid scope value: '{scope_val}'. "
                f"Must be one of: {', '.join(sorted({scope.value for scope in MemoryScope}))}"
            )

    if "category" in entry and not isinstance(entry["category"], str):
        errors.append(f"{prefix} field 'category' must be a string")

    if "content" in entry and not isinstance(entry["content"], str):
        errors.append(f"{prefix} field 'content' must be a string")

    if "created_at" in entry:
        val = entry["created_at"]
        if not isinstance(val, (int, float)):
            errors.append(f"{prefix} field 'created_at' must be a number")

    if "updated_at" in entry:
        val = entry["updated_at"]
        if not isinstance(val, (int, float)):
            errors.append(f"{prefix} field 'updated_at' must be a number")

    if "tags" in entry:
        val = entry["tags"]
        if not isinstance(val, list):
            errors.append(f"{prefix} field 'tags' must be a list")
        elif not all(isinstance(t, str) for t in val):
            errors.append(f"{prefix} field 'tags' must contain only strings")

    if "usage_count" in entry:
        val = entry["usage_count"]
        if not isinstance(val, int):
            errors.append(f"{prefix} field 'usage_count' must be an integer")

    return len(errors) == 0, errors

def _recover_entries(data: dict, memory_json_path: Path) -> list[dict]:
    """Attempt to recover valid entries from corrupted memory data.

    Creates a backup of the corrupted file and returns only valid entries.

    Args:
        data: Parsed JSON data (may be partially corrupted)
        memory_json_path: Path to the original memory.json file

    Returns:
        List of valid entry dictionaries
    """
    backup_path = memory_json_path.with_suffix(".json.bak")
    try:
        import shutil
        shutil.copy2(str(memory_json_path), str(backup_path))
        logger.warning(
            "Corrupted memory file backed up to %s", backup_path
        )
    except OSError as e:
        logger.error(
            "Failed to create backup of corrupted memory file: %s", e
        )

    entries = data.get("entries", [])
    valid_entries = []
    recovered_count = 0

    for idx, entry_data in enumerate(entries):
        entry_valid, _ = _validate_entry(entry_data, idx)
        if not entry_valid:
            logger.warning("Skipping corrupted entry at index %d", idx)
        else:
            valid_entries.append(entry_data)
            recovered_count += 1

    total = len(entries)
    logger.info(
        "Recovery complete: %d/%d entries recovered", recovered_count, total
    )
    return valid_entries

class MemoryStorageMixin:
    def _load_all(self) -> None:
        """Load all memory files."""
        for scope in MemoryScope:
            self._load_scope(scope)
            self._auto_recover_scope(scope)

    def _auto_recover_scope(self, scope: MemoryScope) -> None:
        """Check integrity and auto-recover if issues are found.

        After loading, validates the memory state. If integrity issues
        are detected, attempts to recover by removing invalid entries
        and deduplicating IDs.

        Args:
            scope: Memory scope to check and recover
        """
        result = self.check_integrity(scope)
        if not result["is_valid"]:
            logger.warning(
                "Integrity check failed for scope %s: %d issues found. "
                "Attempting auto-recovery...",
                scope.value,
                len(result["issues"]),
            )
            self._recover_scope(scope)

    def _recover_scope(self, scope: MemoryScope) -> None:
        """Attempt to recover a scope with integrity issues.

        Removes entries with invalid IDs, deduplicates IDs (keeps first),
        and fixes entries with empty content or category.

        Args:
            scope: Memory scope to recover
        """
        entries = self.memories[scope].entries
        seen_ids: set[str] = set()
        recovered: list[MemoryEntry] = []
        removed_count = 0
        fixed_count = 0

        for entry in entries:
            if not entry.id or not isinstance(entry.id, str):
                logger.warning(
                    "Removing entry with invalid ID during recovery"
                )
                removed_count += 1
                continue

            if entry.id in seen_ids:
                logger.warning(
                    "Removing duplicate entry with ID '%s'", entry.id
                )
                removed_count += 1
                continue

            if not entry.category or not isinstance(entry.category, str):
                entry.category = "general"
                fixed_count += 1

            if not entry.content or not isinstance(entry.content, str):
                logger.warning(
                    "Removing entry '%s' with empty content", entry.id
                )
                removed_count += 1
                continue

            seen_ids.add(entry.id)
            recovered.append(entry)

        self.memories[scope].entries = recovered
        self._save_scope(scope)

        logger.info(
            "Recovery complete for scope %s: %d entries recovered, "
            "%d removed, %d fixed",
            scope.value,
            len(recovered),
            removed_count,
            fixed_count,
        )

    def _load_scope(self, scope: MemoryScope) -> None:
        """Load memory file for a scope."""
        path = self._get_scope_path(scope)
        memory_md = path / "MEMORY.md"
        memory_json = path / "memory.json"

        if not memory_md.exists() and not memory_json.exists():
            return

        # Load JSON metadata if exists
        if memory_json.exists():
            try:
                raw_text = memory_json.read_text(encoding="utf-8")
                data = json.loads(raw_text)

                is_valid, errors = _validate_memory_data(data)
                if is_valid:
                    for entry_data in data.get("entries", []):
                        entry = MemoryEntry.from_dict(entry_data)
                        self.memories[scope].entries.append(entry)
                    self.memories[scope]._rebuild_indices()
                    return
                else:
                    logger.warning(
                        "Memory data validation failed for scope %s: %s",
                        scope.value,
                        "; ".join(errors[:5]),
                    )
                    valid_entries = _recover_entries(data, memory_json)
                    for entry_data in valid_entries:
                        entry = MemoryEntry.from_dict(entry_data)
                        self.memories[scope].entries.append(entry)
                    if valid_entries:
                        self._save_scope(scope)
                    self.memories[scope]._rebuild_indices()
                    return
            except json.JSONDecodeError as e:
                logger.error(
                    "JSON decode error in scope %s: %s", scope.value, e
                )
            except KeyError as e:
                logger.error(
                    "Missing key in scope %s data: %s", scope.value, e
                )

        # Load from MEMORY.md
        if memory_md.exists():
            content = memory_md.read_text(encoding="utf-8")
            self._parse_memory_md(content, scope)

    def _parse_memory_md(self, content: str, scope: MemoryScope) -> None:
        """Parse MEMORY.md file into entries."""
        lines = content.split("\n")
        current_category = "general"
        entry_counter = 0

        for line in lines:
            line = line.strip()

            # Skip headers and metadata
            if line.startswith("#") or line.startswith("*") or not line:
                if line.startswith("## "):
                    current_category = line[3:].strip().lower()
                continue

            # Parse list items
            if line.startswith("- "):
                entry_content = line[2:]

                # Extract tags
                tags = []
                if "`" in entry_content:
                    import re
                    tag_matches = re.findall(r"`([^`]+)`", entry_content)
                    for tag_match in tag_matches:
                        tags.extend(tag_match.split())
                    entry_content = re.sub(r"`[^`]+`", "", entry_content).strip()

                entry_counter += 1
                entry = MemoryEntry(
                    id=f"{scope.value}-{entry_counter}",
                    scope=scope,
                    category=current_category,
                    content=entry_content,
                    tags=tags,
                )
                self.memories[scope].entries.append(entry)
        # Rebuild indices after Markdown-based loading
        if self.memories[scope].entries:
            self.memories[scope]._rebuild_indices()

    def _get_scope_path(self, scope: MemoryScope) -> Path:
        """Get path for memory scope."""
        if scope == MemoryScope.USER:
            return self.paths.user_memory
        elif scope == MemoryScope.PROJECT:
            return self.paths.project_memory
        else:
            return self.paths.local_memory

    def _ensure_scope_path(self, scope: MemoryScope) -> None:
        """Ensure directory exists for scope."""
        path = self._get_scope_path(scope)
        path.mkdir(parents=True, exist_ok=True)

    def _save_scope(self, scope: MemoryScope) -> None:
        """Save memory to disk (atomic write to prevent corruption)."""
        path = self._get_scope_path(scope)
        self._ensure_scope_path(scope)

        # Save JSON metadata (atomic: write to temp, then replace)
        memory_json = path / "memory.json"
        data = {
            "scope": scope.value,
            "last_updated": time.time(),
            "entries": [e.to_dict() for e in self.memories[scope].entries],
        }
        self._atomic_write(memory_json, json.dumps(data, indent=2, ensure_ascii=False))

        # Also update MEMORY.md for human readability (atomic)
        memory_md = path / "MEMORY.md"
        self._atomic_write(memory_md, self.memories[scope].format_as_markdown())

    @staticmethod
    def _atomic_write(target: Path, content: str) -> None:
        """Write content atomically: write to temp file, then os.replace().

        This prevents data corruption if the process is killed mid-write
        or if multiple instances write to the same file concurrently.
        """
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(target))
        except BaseException:
            # Clean up temp file on any failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def check_integrity(self, scope: MemoryScope) -> dict[str, Any]:
        """Validate all entries in a scope for integrity.

        Checks:
        - Valid IDs (non-empty strings)
        - Valid categories (non-empty strings)
        - Non-empty content
        - No duplicate IDs

        Args:
            scope: Memory scope to check

        Returns:
            Dictionary with {is_valid: bool, issues: list[str]}
        """
        issues: list[str] = []
        seen_ids: set[str] = set()
        entries = self.memories[scope].entries

        for idx, entry in enumerate(entries):
            if not entry.id or not isinstance(entry.id, str):
                issues.append(
                    f"Entry at index {idx} has invalid or empty ID"
                )

            if entry.id in seen_ids:
                issues.append(
                    f"Duplicate ID found: '{entry.id}' "
                    f"(entries {list(self._find_entry_indices(scope, entry.id))})"
                )
            else:
                seen_ids.add(entry.id)

            if not entry.category or not isinstance(entry.category, str):
                issues.append(
                    f"Entry '{entry.id}' has invalid or empty category"
                )

            if not entry.content or not isinstance(entry.content, str):
                issues.append(
                    f"Entry '{entry.id}' has empty or invalid content"
                )

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
        }

__all__ = ["MemoryStorageMixin", "_validate_memory_data", "_validate_entry", "_recover_entries"]
