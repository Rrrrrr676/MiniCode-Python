"""Compatibility facade for minicode.providers.openai."""

import sys as _sys
from minicode.providers import openai as _implementation

_implementation.__all__ = ["DEFAULT_MAX_RETRIES","DEFAULT_OPENAI_USER_AGENT","OPENAI_MODELS","OpenAIModelAdapter"]
_sys.modules[__name__] = _implementation

from minicode.providers.openai import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_OPENAI_USER_AGENT,
    OPENAI_MODELS,
    OpenAIModelAdapter,
)

__all__ = [
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_OPENAI_USER_AGENT",
    "OPENAI_MODELS",
    "OpenAIModelAdapter",
]
