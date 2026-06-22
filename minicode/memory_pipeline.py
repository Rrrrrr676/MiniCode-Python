"""Compatibility facade for minicode.memory.pipeline."""

import sys as _sys
from minicode.memory import pipeline as _implementation

_implementation.__all__ = ["MemoryPipeline"]
_sys.modules[__name__] = _implementation

from minicode.memory.pipeline import (
    MemoryPipeline,
)

__all__ = ["MemoryPipeline"]
