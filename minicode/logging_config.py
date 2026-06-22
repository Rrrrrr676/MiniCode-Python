"""Compatibility facade for minicode.observability.logging."""

import sys as _sys
from minicode.observability import logging as _implementation

_implementation.__all__ = ["CONSOLE_FORMAT","FILE_FORMAT","LOG_BACKUP_COUNT","LOG_FILE","LOG_MAX_BYTES","StructuredFormatter","get_log_stats","get_logger","log_api_call","log_permission_check","log_session_event","log_tool_execution","setup_logging","structured_logging_requested"]
_sys.modules[__name__] = _implementation

from minicode.observability.logging import (
    CONSOLE_FORMAT,
    FILE_FORMAT,
    LOG_BACKUP_COUNT,
    LOG_FILE,
    LOG_MAX_BYTES,
    StructuredFormatter,
    get_log_stats,
    get_logger,
    log_api_call,
    log_permission_check,
    log_session_event,
    log_tool_execution,
    setup_logging,
    structured_logging_requested,
)

__all__ = [
    "CONSOLE_FORMAT",
    "FILE_FORMAT",
    "LOG_BACKUP_COUNT",
    "LOG_FILE",
    "LOG_MAX_BYTES",
    "StructuredFormatter",
    "get_log_stats",
    "get_logger",
    "log_api_call",
    "log_permission_check",
    "log_session_event",
    "log_tool_execution",
    "setup_logging",
    "structured_logging_requested",
]
