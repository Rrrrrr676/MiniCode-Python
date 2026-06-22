"""Compatibility facade for minicode.cli.commands."""

import sys as _sys
from minicode.cli import commands as _implementation

_implementation.__all__ = ["SLASH_COMMANDS","SlashCommand","complete_slash_command","find_matching_slash_commands","format_cybernetics_status","format_slash_commands","try_handle_local_command"]
_sys.modules[__name__] = _implementation

from minicode.cli.commands import (
    SLASH_COMMANDS,
    SlashCommand,
    complete_slash_command,
    find_matching_slash_commands,
    format_cybernetics_status,
    format_slash_commands,
    try_handle_local_command,
)

__all__ = [
    "SLASH_COMMANDS",
    "SlashCommand",
    "complete_slash_command",
    "find_matching_slash_commands",
    "format_cybernetics_status",
    "format_slash_commands",
    "try_handle_local_command",
]
