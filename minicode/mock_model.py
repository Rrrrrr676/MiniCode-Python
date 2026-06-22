"""Compatibility facade for minicode.providers.mock."""

import sys as _sys
from minicode.providers import mock as _implementation

_implementation.__all__ = ["MockModelAdapter"]
_sys.modules[__name__] = _implementation

from minicode.providers.mock import (
    MockModelAdapter,
)

__all__ = [
    "MockModelAdapter",
]
