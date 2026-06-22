"""Compatibility facade for minicode.cli.install."""

import sys as _sys
from minicode.cli import install as _implementation

_implementation.__all__ = ["main"]
_sys.modules[__name__] = _implementation

from minicode.cli.install import (
    main,
)

__all__ = [
    "main",
]
