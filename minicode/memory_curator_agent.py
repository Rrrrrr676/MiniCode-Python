"""Compatibility facade for minicode.memory.curator."""

import sys as _sys
from minicode.memory import curator as _implementation

_implementation.__all__ = ["CONSOLIDATE_PROMPT","CuratorReport","MemoryCuratorAgent"]
_sys.modules[__name__] = _implementation

from minicode.memory.curator import (
    CONSOLIDATE_PROMPT,
    CuratorReport,
    MemoryCuratorAgent,
)

__all__ = ["CONSOLIDATE_PROMPT","CuratorReport","MemoryCuratorAgent"]
