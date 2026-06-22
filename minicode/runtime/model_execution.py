"""Provider call compatibility, diagnostics, and fallback classification."""

from __future__ import annotations

import inspect
import re
from typing import Any, Callable

from minicode.config import describe_fallback_guidance, describe_provider_channel
from minicode.core.state import AppState, Store
from minicode.core.types import AgentStep, ChatMessage, ModelAdapter
from minicode.providers.spec import detect_provider


_MODEL_FALLBACK_ERROR_HINTS = (
    "no available channel",
    "temporarily unavailable",
    "service unavailable",
    "please try again later",
    "capacity exceeded",
    "overloaded",
    "high demand",
    "503",
    "502",
    "500",
    "connection refused",
    "connection reset",
    "timed out",
    "timeout",
)
_MODEL_FALLBACK_BLOCK_HINTS = (
    "unauthorized",
    "forbidden",
    "invalid api key",
    "authentication",
    "bad request",
    "invalid_request",
    "validation",
    "tool schema",
    "context length",
)


def should_attempt_model_fallback(error_message: str) -> bool:
    normalized = error_message.lower()
    if any(marker in normalized for marker in _MODEL_FALLBACK_BLOCK_HINTS):
        return False
    return any(marker in normalized for marker in _MODEL_FALLBACK_ERROR_HINTS)


def looks_like_provider_availability_error(error_message: str) -> bool:
    normalized = error_message.lower()
    markers = (
        "no available channel",
        "temporarily unavailable",
        "service unavailable",
        "please try again later",
        "capacity exceeded",
        "overloaded",
        "high demand",
        "503",
        "502",
        "500",
    )
    return any(marker in normalized for marker in markers)


def summarize_model_api_failure(
    *,
    error_type: str,
    error: Exception,
    active_model_id: str = "",
    fallback_errors: list[str] | None = None,
    runtime: dict[str, Any] | None = None,
) -> str:
    fallback_errors = fallback_errors or []
    if fallback_errors:
        combined = " ".join(fallback_errors)
        if (
            "no viable fallback models were available" in combined.lower()
            and any(
                looks_like_provider_availability_error(item)
                for item in fallback_errors + [str(error)]
            )
        ):
            runtime = runtime or {}
            guidance_model = (
                str(runtime.get("configuredModel", "")).strip()
                or str(runtime.get("model", "")).strip()
                or active_model_id
                or "the active model"
            )
            model_label = guidance_model or active_model_id or "the active model"
            provider = detect_provider(guidance_model, runtime).value if guidance_model else "unknown"
            channel = describe_provider_channel(runtime, provider)
            guidance = describe_fallback_guidance(
                runtime,
                provider_name=provider,
                current_model=guidance_model,
            )
            guidance_suffix = f" Next step: {guidance[0]}" if guidance else ""
            return (
                f"Provider availability failure: {model_label} failed and all viable fallback models were unavailable. "
                f"Remaining blocker is upstream provider/channel availability, not a local retry loop. "
                f"Active channel: {channel}. Last error ({error_type}): {error}{guidance_suffix}"
            )
    return f"Model API error ({error_type}): {error}"


def extract_model_id_from_provider_error(error: Exception) -> str:
    match = re.search(
        r"model\s+([^\s]+)\s+under\s+group",
        str(error),
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def infer_active_model_id(
    model: ModelAdapter,
    runtime: dict[str, Any] | None,
    error: Exception | None = None,
) -> str:
    explicit = str(getattr(model, "model_id", "") or "").strip()
    if explicit:
        return explicit
    runtime_model = str((runtime or {}).get("model", "") or "").strip()
    if runtime_model:
        return runtime_model
    return extract_model_id_from_provider_error(error) if error is not None else ""


def is_empty_assistant_response(content: str) -> bool:
    return not content.strip()


def format_diagnostics(
    stop_reason: str | None,
    block_types: list[str] | None,
    ignored_block_types: list[str] | None,
) -> str:
    parts: list[str] = []
    if stop_reason:
        parts.append(f"stop_reason={stop_reason}")
    if block_types:
        parts.append(f"blocks={','.join(block_types)}")
    if ignored_block_types:
        parts.append(f"ignored={','.join(ignored_block_types)}")
    return f" Diagnostics: {'; '.join(parts)}." if parts else ""


def is_recoverable_thinking_stop(
    *,
    is_empty: bool,
    stop_reason: str | None,
    ignored_block_types: list[str] | None,
) -> bool:
    return bool(
        is_empty
        and stop_reason in {"pause_turn", "max_tokens"}
        and "thinking" in (ignored_block_types or [])
    )


def should_treat_assistant_as_progress(
    *,
    kind: str | None,
    content: str,
    saw_tool_result: bool,
) -> bool:
    if kind == "progress":
        return True
    if kind == "final" or not saw_tool_result:
        return False
    return False


def model_next(
    model: ModelAdapter,
    messages: list[ChatMessage],
    *,
    on_stream_chunk: Callable[[str], None] | None,
    on_thinking_chunk: Callable[[str], None] | None = None,
    store: Store[AppState] | None,
) -> AgentStep:
    """Call adapters with optional store/thinking support for test-double safety."""
    kwargs: dict[str, Any] = {"on_stream_chunk": on_stream_chunk}
    try:
        signature = inspect.signature(model.next)
        parameter_names = set(signature.parameters)
        has_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        if has_kwargs or "on_thinking_delta" in parameter_names:
            kwargs["on_thinking_delta"] = on_thinking_chunk
        if has_kwargs or "store" in parameter_names:
            kwargs["store"] = store
    except (TypeError, ValueError):
        pass
    return model.next(messages, **kwargs)


__all__ = [
    "format_diagnostics",
    "infer_active_model_id",
    "is_empty_assistant_response",
    "is_recoverable_thinking_stop",
    "looks_like_provider_availability_error",
    "model_next",
    "should_attempt_model_fallback",
    "should_treat_assistant_as_progress",
    "summarize_model_api_failure",
]
