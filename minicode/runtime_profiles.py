"""Compatibility facade for minicode.runtime.profiles."""

import sys as _sys
from minicode.runtime import profiles as _implementation

_implementation.__all__ = ["RuntimeProfile","get_runtime_profile","resolve_runtime_profile"]
_sys.modules[__name__] = _implementation

from minicode.runtime.profiles import (
    RuntimeProfile,
    get_runtime_profile,
    resolve_runtime_profile,
)

__all__ = [
    "RuntimeProfile",
    "get_runtime_profile",
    "resolve_runtime_profile",
]
