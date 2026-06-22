"""Compatibility facade for minicode.context.prompt."""

import sys as _sys
from minicode.context import prompt as _implementation

_implementation.__all__ = ["build_system_prompt","build_system_prompt_bundle"]
_sys.modules[__name__] = _implementation

from minicode.context.prompt import (
    build_system_prompt,
    build_system_prompt_bundle,
)

__all__ = [
    "build_system_prompt",
    "build_system_prompt_bundle",
]
