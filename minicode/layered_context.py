"""Compatibility facade for minicode.context.layered."""

import sys as _sys
from minicode.context import layered as _implementation

_implementation.__all__ = ["ContextBudget","ContextBuilder","ContextLayer","LayerContent","LayeredContext"]
_sys.modules[__name__] = _implementation

from minicode.context.layered import (
    ContextBudget,
    ContextBuilder,
    ContextLayer,
    LayerContent,
    LayeredContext,
)

__all__ = [
    "ContextBudget",
    "ContextBuilder",
    "ContextLayer",
    "LayerContent",
    "LayeredContext",
]
