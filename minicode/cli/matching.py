"""Slash-command matching and completion."""
from __future__ import annotations

from .registry import SLASH_COMMANDS

def find_matching_slash_commands(user_input: str) -> list[str]:
    """Find slash commands matching user input.

    Tries exact prefix first, falls back to fuzzy subsequence matching.
    """
    commands = [c.usage for c in SLASH_COMMANDS]
    prefix_matches = [c for c in commands if c.startswith(user_input)]
    if prefix_matches:
        return prefix_matches
    # Fuzzy fallback: subsequence match (e.g., "mem" matches "/memory")
    lower = user_input.lower()
    fuzzy = [c for c in commands if all(ch in c.lower() for ch in lower)]
    return fuzzy if fuzzy else commands

def complete_slash_command(line: str) -> tuple[list[str], str]:
    commands = [c.usage for c in SLASH_COMMANDS]
    hits = [c for c in commands if c.startswith(line)]
    if not hits and line:
        lower = line.lower()
        hits = [c for c in commands if all(ch in c.lower() for ch in lower)]
    return (hits if hits else commands, line)

__all__ = ["find_matching_slash_commands", "complete_slash_command"]
