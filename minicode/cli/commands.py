"""Public slash-command API."""

from .registry import SLASH_COMMANDS, SlashCommand
from .matching import complete_slash_command, find_matching_slash_commands
from .formatters import format_cybernetics_status, format_slash_commands
from .handlers import try_handle_local_command

__all__ = [
    "SLASH_COMMANDS", "SlashCommand", "complete_slash_command",
    "find_matching_slash_commands", "format_cybernetics_status",
    "format_slash_commands", "try_handle_local_command",
]
