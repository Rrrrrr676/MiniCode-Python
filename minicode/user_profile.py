"""Compatibility facade for minicode.persistence.user_profile."""

import sys as _sys
from minicode.persistence import user_profile as _implementation

_implementation.__all__ = ["CodingStyle","UserPreferences","UserProfile","UserProfileManager","handle_user_command","parse_user_md","serialize_user_md"]
_sys.modules[__name__] = _implementation

from minicode.persistence.user_profile import (
    CodingStyle,
    UserPreferences,
    UserProfile,
    UserProfileManager,
    handle_user_command,
    parse_user_md,
    serialize_user_md,
)

__all__ = [
    "CodingStyle",
    "UserPreferences",
    "UserProfile",
    "UserProfileManager",
    "handle_user_command",
    "parse_user_md",
    "serialize_user_md",
]
