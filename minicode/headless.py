"""MiniCode Headless Runner — non-interactive, one-shot execution.

Inspired by Hermes Agent's headless mode for CI/CD pipelines and
automated workflows.

Usage:
  # Run a single prompt and exit
  python -m minicode.headless "帮我分析这个项目的结构"

  # Pipe input
  echo "解释这段代码" | python -m minicode.headless

  # In Docker
  docker compose run --rm headless "修复这个 bug"
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _write_headless_messages_trace(
    trace_path: str | None,
    *,
    cwd: str,
    prompt: str,
    runtime: dict | None,
    result_messages: list[dict] | None,
    response_text: str | None,
    error_text: str | None = None,
) -> None:
    if not trace_path:
        return
    payload = {
        "cwd": cwd,
        "prompt": prompt,
        "model": (runtime or {}).get("model"),
        "messages": result_messages or [],
        "assistant_response": response_text,
        "error": error_text,
    }
    path = Path(trace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def run_headless(prompt: str | None = None) -> str:
    """Run a single agent turn in headless mode and return the response.

    Args:
        prompt: The user message to send. If None, reads from stdin.

    Returns:
        The assistant's response text.
    """
    from minicode.agent_loop import run_agent_turn
    from minicode.config import load_runtime_config
    from minicode.memory import MemoryManager
    from minicode.model_registry import create_model_adapter
    from minicode.permissions import PermissionManager
    from minicode.prompt import build_system_prompt
    from minicode.tools import create_default_tool_registry
    from minicode.logging_config import setup_logging, get_logger

    setup_logging(level=os.environ.get("MINI_CODE_LOG_LEVEL", "WARNING"))
    logger = get_logger("headless")

    # Read prompt from stdin if not provided
    if prompt is None:
        if not sys.stdin.isatty():
            prompt = sys.stdin.read().strip()
        else:
            print("Usage: python -m minicode.headless <prompt>", file=sys.stderr)
            sys.exit(1)

    if not prompt:
        print("Error: empty prompt", file=sys.stderr)
        sys.exit(1)

    cwd = str(Path.cwd())

    # Load config
    try:
        runtime = load_runtime_config(cwd)
    except Exception as exc:  # noqa: BLE001
        print(f"Config error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Initialize components
    tools = create_default_tool_registry(cwd, runtime=runtime)
    permissions = PermissionManager(cwd, prompt=None)
    memory_mgr = MemoryManager(project_root=Path(cwd))

    model = create_model_adapter(
        model=runtime.get("model", ""),
        tools=tools,
        runtime=runtime,
    )

    messages = [
        {
            "role": "system",
            "content": build_system_prompt(
                cwd,
                permissions.get_summary(),
                {
                    "skills": tools.get_skills(),
                    "mcpServers": tools.get_mcp_servers(),
                    "memory_context": memory_mgr.get_relevant_context(),
                },
            ),
        },
        {"role": "user", "content": prompt},
    ]

    logger.info("Headless run: %s", prompt[:80])
    trace_output_path = os.environ.get("MINI_CODE_HEADLESS_MESSAGES_OUT", "").strip() or None

    try:
        result_messages = run_agent_turn(
            model=model,
            tools=tools,
            messages=messages,
            cwd=cwd,
            permissions=permissions,
            runtime=runtime,
        )

        # Extract last assistant message
        last_assistant = next(
            (m for m in reversed(result_messages) if m["role"] == "assistant"),
            None,
        )
        response_text = last_assistant["content"] if last_assistant else "(no response)"
        _write_headless_messages_trace(
            trace_output_path,
            cwd=cwd,
            prompt=prompt,
            runtime=runtime,
            result_messages=result_messages,
            response_text=response_text,
        )
        return response_text

    except Exception as exc:  # noqa: BLE001
        logger.error("Headless error: %s", exc)
        response_text = f"Error: {exc}"
        _write_headless_messages_trace(
            trace_output_path,
            cwd=cwd,
            prompt=prompt,
            runtime=runtime,
            result_messages=[],
            response_text=response_text,
            error_text=str(exc),
        )
        return response_text
    finally:
        try:
            tools.dispose()
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    """CLI entry point for headless mode."""
    # Get prompt from command line args or stdin
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    response = run_headless(prompt)
    print(response)


if __name__ == "__main__":
    main()
