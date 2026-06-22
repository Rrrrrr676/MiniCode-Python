"""Compatibility facade for the Agent Runtime.

The implementation lives in :mod:`minicode.runtime.runner`; this stable module
keeps existing imports and monkeypatch targets working.
"""

from minicode.runtime.runner import run_agent_turn

__all__ = ["run_agent_turn"]
