"""Compatibility facade for minicode.memory.domain."""

import sys as _sys
from minicode.memory import domain as _implementation

_implementation.__all__ = ["DOMAIN_SEARCH_TOKENS","DomainType","FILE_EXT_DOMAIN_MAP","INTENT_KW_DOMAIN_MAP","classify","get_active_domain_values"]
_sys.modules[__name__] = _implementation

from minicode.memory.domain import (
    DOMAIN_SEARCH_TOKENS,
    DomainType,
    FILE_EXT_DOMAIN_MAP,
    INTENT_KW_DOMAIN_MAP,
    classify,
    get_active_domain_values,
)

__all__ = ["DOMAIN_SEARCH_TOKENS","DomainType","FILE_EXT_DOMAIN_MAP","INTENT_KW_DOMAIN_MAP","classify","get_active_domain_values"]
