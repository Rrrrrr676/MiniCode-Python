"""Compatibility facade for minicode.runtime.intent."""

import sys as _sys
from minicode.runtime import intent as _implementation

_implementation.__all__ = ["ActionType","IntentParser","IntentType","ParsedIntent","get_intent_parser","parse_intent"]
_sys.modules[__name__] = _implementation

from minicode.runtime.intent import (
    ActionType,
    IntentParser,
    IntentType,
    ParsedIntent,
    get_intent_parser,
    parse_intent,
)

__all__ = [
    "ActionType",
    "IntentParser",
    "IntentType",
    "ParsedIntent",
    "get_intent_parser",
    "parse_intent",
]
