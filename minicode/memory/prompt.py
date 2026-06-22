"""Prompt injection and memory-list formatting."""
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

from .models import MemoryEntry

def inject_memory_into_prompt(
    system_prompt: str,
    memory_manager: MemoryManager,
    max_tokens: int = 8000,
) -> str:
    """Inject memory context into system prompt."""
    memory_context = memory_manager.get_relevant_context(max_tokens=max_tokens)

    if not memory_context:
        return system_prompt

    return f"""{system_prompt}

## Project Memory & Context

The following information has been accumulated from previous sessions:

{memory_context}

Use this context to inform your decisions and follow established patterns."""

def format_memory_list(memory_manager=None, scope: MemoryScope | None = None, category: str | None = None) -> str:
    """Format memory entries for CLI display."""
    if memory_manager is None:
        return "No MemoryManager available."

    # Collect entries from specified scope(s)
    scopes = [scope] if scope else list(MemoryScope)
    all_entries: list[MemoryEntry] = []
    for s in scopes:
        if s in memory_manager.memories:
            entries = memory_manager.memories[s].entries
            if category:
                entries = [e for e in entries if e.category == category]
            all_entries.extend(entries)

    if not all_entries:
        return "No memories found."

    lines = [f"{'=' * 60}"]
    for entry in all_entries[:20]:  # Limit to 20 entries
        scope_tag = f"[{entry.scope.value if hasattr(entry, 'scope') else '?'}]"
        cat_tag = f"[{entry.category}]"
        content_preview = entry.content[:100].replace('\n', ' ')
        lines.append(f"{scope_tag} {cat_tag} {content_preview}")
        if entry.tags:
            lines.append(f"     Tags: {', '.join(entry.tags[:5])}")
        lines.append(f"     Used: {entry.usage_count}x | Updated: {time.strftime('%Y-%m-%d %H:%M', time.localtime(entry.updated_at))}")
        lines.append("")
    lines.append(f"{'=' * 60}")
    lines.append(f"Total: {len(all_entries)} entries")
    return "\n".join(lines)

__all__ = ["inject_memory_into_prompt", "format_memory_list"]
