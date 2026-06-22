"""Turn lifecycle helpers shared by the runtime runner."""

from minicode.core.types import ChatMessage


STABLE_TASK_STATE_MARKER = "[Stable task state]"


def upsert_stable_task_state_message(
    messages: list[ChatMessage],
    stable_text: str,
) -> list[ChatMessage]:
    """Replace the prior stable-state system message and append the new one."""
    filtered = [
        message
        for message in messages
        if not (
            message.get("role") == "system"
            and str(message.get("content", "")).startswith(STABLE_TASK_STATE_MARKER)
        )
    ]
    filtered.append(
        {
            "role": "system",
            "content": f"{STABLE_TASK_STATE_MARKER}\n{stable_text}",
        }
    )
    return filtered


__all__ = ["STABLE_TASK_STATE_MARKER", "upsert_stable_task_state_message"]
