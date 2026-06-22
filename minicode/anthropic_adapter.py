"""Compatibility facade for minicode.providers.anthropic."""

import sys as _sys
from minicode.providers import anthropic as _implementation

_implementation.__all__ = ["AnthropicModelAdapter","DEFAULT_MAX_RETRIES"]
_sys.modules[__name__] = _implementation

from minicode.providers.anthropic import (
    _messages_endpoint,
    AnthropicModelAdapter,
    DEFAULT_MAX_RETRIES,
)

__all__ = [
    "AnthropicModelAdapter",
    "DEFAULT_MAX_RETRIES",
]
