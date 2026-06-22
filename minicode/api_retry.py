"""Compatibility facade for minicode.providers.retry."""

import sys as _sys
from minicode.providers import retry as _implementation

_implementation.__all__ = ["APIRetryExhaustedError","BASE_BACKOFF","ErrorCategory","HTTPError","JITTER_FACTOR","MAX_BACKOFF","MAX_RETRIES","RETRYABLE_STATUS","RetryState","calculate_backoff","classify_error","format_retry_state","is_retryable","is_retryable_error","raise_for_status","retry_with_backoff","retry_with_backoff_async"]
_sys.modules[__name__] = _implementation

from minicode.providers.retry import (
    APIRetryExhaustedError,
    BASE_BACKOFF,
    ErrorCategory,
    HTTPError,
    JITTER_FACTOR,
    MAX_BACKOFF,
    MAX_RETRIES,
    RETRYABLE_STATUS,
    RetryState,
    calculate_backoff,
    classify_error,
    format_retry_state,
    is_retryable,
    is_retryable_error,
    raise_for_status,
    retry_with_backoff,
    retry_with_backoff_async,
)

__all__ = [
    "APIRetryExhaustedError",
    "BASE_BACKOFF",
    "ErrorCategory",
    "HTTPError",
    "JITTER_FACTOR",
    "MAX_BACKOFF",
    "MAX_RETRIES",
    "RETRYABLE_STATUS",
    "RetryState",
    "calculate_backoff",
    "classify_error",
    "format_retry_state",
    "is_retryable",
    "is_retryable_error",
    "raise_for_status",
    "retry_with_backoff",
    "retry_with_backoff_async",
]
