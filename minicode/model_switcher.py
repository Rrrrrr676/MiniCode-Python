"""Compatibility facade for minicode.providers.switching."""

import sys as _sys
from minicode.providers import switching as _implementation

_implementation.__all__ = ["ModelSwitcher","SwitchResult","detect_provider_name"]
_sys.modules[__name__] = _implementation

from minicode.providers.switching import (
    ModelSwitcher,
    SwitchResult,
    detect_provider_name,
)

__all__ = [
    "ModelSwitcher",
    "SwitchResult",
    "detect_provider_name",
]
