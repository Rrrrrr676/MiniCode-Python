"""Compatibility facade for minicode.runtime.reflection."""

import sys as _sys
from minicode.runtime import reflection as _implementation

_implementation.__all__ = ["ReflectionEngine","ReflectionResult"]
_sys.modules[__name__] = _implementation

from minicode.runtime.reflection import (
    ReflectionEngine,
    ReflectionResult,
)

__all__ = [
    "ReflectionEngine",
    "ReflectionResult",
]
