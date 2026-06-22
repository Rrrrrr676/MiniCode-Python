"""Compatibility facade for :mod:`minicode.core.state`."""

from minicode.core.state import (
    AppState,
    Store,
    add_cost,
    create_app_store,
    format_app_state_summary,
    get_global_store,
    handle_state_command,
    increment_tool_calls,
    record_api_error,
    set_busy,
    set_global_store,
    set_idle,
    update_context_usage,
    update_message_count,
)

__all__ = [
    "AppState",
    "Store",
    "add_cost",
    "create_app_store",
    "format_app_state_summary",
    "get_global_store",
    "handle_state_command",
    "increment_tool_calls",
    "record_api_error",
    "set_busy",
    "set_global_store",
    "set_idle",
    "update_context_usage",
    "update_message_count",
]
