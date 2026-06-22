"""Single-tool execution, timeout, callback, and state handling."""

from __future__ import annotations

import concurrent.futures
import os
import traceback
from typing import Any, Callable

from minicode.core.state import increment_tool_calls, set_busy, set_idle
from minicode.observability.logging import get_logger
from minicode.tooling import ToolContext, ToolRegistry, ToolResult


logger = get_logger("runtime.tool_execution")


def execute_single_tool(
    call: dict,
    tools: ToolRegistry,
    cwd: str,
    permissions: Any | None,
    session: Any | None,
    runtime: dict | None,
    store: Any | None,
    step: int,
    on_tool_start: Callable[[str, dict], None] | None,
    on_tool_result: Callable[[str, str, bool], None] | None,
    tool_scheduler: Any | None = None,
) -> ToolResult:
    """Execute one tool with timeout, callbacks, and crash containment."""
    tool_name = call["toolName"]
    tool_input = call["input"]
    try:
        if on_tool_start:
            on_tool_start(tool_name, tool_input)
        if store:
            store.set_state(set_busy(tool_name))

        base_timeout = int(os.environ.get("MINICODE_TOOL_TIMEOUT", "120"))
        timeout = (
            int(getattr(tool_scheduler, "_force_tool_timeout", base_timeout))
            if tool_scheduler and hasattr(tool_scheduler, "_force_tool_timeout")
            else base_timeout
        )
        context = ToolContext(
            cwd=cwd,
            permissions=permissions,
            session=session,
            _runtime=runtime,
        )
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(tools.execute, tool_name, tool_input, context)
                result = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            result = ToolResult(
                ok=False,
                output=f"Tool '{tool_name}' timed out after {timeout}s",
            )
        except Exception:
            result = tools.execute(tool_name, tool_input, context)

        if store:
            store.set_state(increment_tool_calls())
            store.set_state(set_idle())
        if on_tool_result:
            on_tool_result(tool_name, result.output, not result.ok)
        return result
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:  # noqa: BLE001
        traceback_excerpt = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)[-3:]
        ).strip()
        error_type = type(exc).__name__
        logger.error("Tool execution pipeline crashed (%s): %s", error_type, exc)
        if store:
            try:
                store.set_state(set_idle())
            except Exception:
                pass
        return ToolResult(
            ok=False,
            output=(
                f"[{error_type}] Tool execution pipeline crashed: {exc}\n"
                f"Traceback:\n{traceback_excerpt}"
            ),
        )


__all__ = ["execute_single_tool"]
