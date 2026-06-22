"""Compatibility facade for minicode.runtime.smart_routing."""

import sys as _sys
from minicode.runtime import smart_routing as _implementation

_implementation.__all__ = ["FeedbackLearner","SmartRouter","TaskOutcome","get_smart_router","reset_smart_router"]
_sys.modules[__name__] = _implementation

from minicode.runtime.smart_routing import (
    FeedbackLearner,
    SmartRouter,
    TaskOutcome,
    get_smart_router,
    reset_smart_router,
)

__all__ = [
    "FeedbackLearner",
    "SmartRouter",
    "TaskOutcome",
    "get_smart_router",
    "reset_smart_router",
]
