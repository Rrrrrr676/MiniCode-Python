"""Compatibility facade for minicode.integrations.background_tasks."""

import sys as _sys
from minicode.integrations import background_tasks as _implementation

_implementation.__all__ = ["can_start_new_task","check_completed_tasks","format_slot_status","get_background_task","get_slot_stats","list_background_tasks","register_background_shell_task","register_completion_callback","set_max_slots"]
_sys.modules[__name__] = _implementation

from minicode.integrations.background_tasks import (
    _refresh_record,
    can_start_new_task,
    check_completed_tasks,
    format_slot_status,
    get_background_task,
    get_slot_stats,
    list_background_tasks,
    register_background_shell_task,
    register_completion_callback,
    set_max_slots,
)

__all__ = [
    "can_start_new_task",
    "check_completed_tasks",
    "format_slot_status",
    "get_background_task",
    "get_slot_stats",
    "list_background_tasks",
    "register_background_shell_task",
    "register_completion_callback",
    "set_max_slots",
]
