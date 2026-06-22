"""Compatibility facade for minicode.context.prompt_pipeline."""

import sys as _sys
from minicode.context import prompt_pipeline as _implementation

_implementation.__all__ = ["PromptPipeline","PromptSection","SYSTEM_PROMPT_DYNAMIC_BOUNDARY","content_hash","read_file_cached"]
_sys.modules[__name__] = _implementation

from minicode.context.prompt_pipeline import (
    PromptPipeline,
    PromptSection,
    SYSTEM_PROMPT_DYNAMIC_BOUNDARY,
    content_hash,
    read_file_cached,
)

__all__ = [
    "PromptPipeline",
    "PromptSection",
    "SYSTEM_PROMPT_DYNAMIC_BOUNDARY",
    "content_hash",
    "read_file_cached",
]
