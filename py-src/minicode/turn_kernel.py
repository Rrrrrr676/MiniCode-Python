from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from minicode.layered_context import ContextBuilder, LayeredContext
from minicode.task_object import TaskState


@dataclass(slots=True)
class TurnPreludeState:
    """Prelude artifacts prepared once before the recurrent tool loop."""

    task: Any | None = None
    task_metadata: dict[str, Any] = field(default_factory=dict)
    layered_context: LayeredContext | None = None
    context_builder: ContextBuilder | None = None
    auditor: Any | None = None


@dataclass(slots=True)
class TurnRecurrentState:
    """Mutable loop state for a single agent turn."""

    max_steps: int | None
    saw_tool_result: bool = False
    empty_response_retry_count: int = 0
    recoverable_thinking_retry_count: int = 0
    tool_error_count: int = 0
    step: int = 0

    def has_remaining_steps(self) -> bool:
        return self.max_steps is None or self.step < self.max_steps

    def begin_step(self) -> int:
        self.step += 1
        return self.step

    def can_retry_empty_response(self, limit: int = 2) -> bool:
        return self.empty_response_retry_count < limit

    def record_empty_response_retry(self) -> None:
        self.empty_response_retry_count += 1

    def can_retry_recoverable_thinking(self, limit: int = 3) -> bool:
        return self.recoverable_thinking_retry_count < limit

    def record_recoverable_thinking_retry(self) -> None:
        self.recoverable_thinking_retry_count += 1

    def record_tool_result(self, ok: bool) -> None:
        self.saw_tool_result = True
        if not ok:
            self.tool_error_count += 1

    def final_task_state(self) -> TaskState:
        return TaskState.COMPLETED if self.tool_error_count == 0 else TaskState.FAILED


@dataclass(slots=True)
class AssistantTurnDecision:
    """Structured outcome for one assistant response inside the recurrent loop."""

    kind: Literal["progress", "retry", "fallback", "final"]
    assistant_content: str | None = None
    user_content: str | None = None
    protect_final_answer: bool = False


@dataclass(slots=True)
class AssistantMessageReplay:
    """Normalized callback and transcript payload for assistant-facing output."""

    callback_kind: Literal["assistant", "progress"] | None
    callback_content: str | None
    transcript_messages: list[dict[str, Any]]
    should_return: bool = False
    protect_final_answer: bool = False


@dataclass(slots=True)
class ToolStepFeedback:
    """Normalized measurements collected after one tool-execution step."""

    error_rate: float
    context_usage: float
    avg_latency: float
    oscillation_index: float


@dataclass(slots=True)
class ToolResultDecision:
    """Transcript updates and control flow after a tool result is prepared."""

    tool_result_content: str
    transcript_messages: list[dict[str, Any]]
    assistant_content: str | None = None
    should_return: bool = False


@dataclass(slots=True)
class ToolResultReplay:
    """Normalized replay payload for one completed tool result."""

    callback_output: str
    should_emit_callback: bool
    should_increment_tool_calls: bool
    conflicting_tool_names: list[str]
    tool_decision: ToolResultDecision


@dataclass(slots=True)
class DeferredToolReplay:
    """Whether a concurrent tool result needs deferred callback replay."""

    should_replay: bool


@dataclass(slots=True)
class ToolBatchPlan:
    """Normalized concurrent/serial execution plan for one tool batch."""

    concurrent_calls: list[dict[str, Any]]
    serial_calls: list[dict[str, Any]]
    max_workers: int


@dataclass(slots=True)
class ToolReplayPlan:
    """Ordered tool replay plan tuned for terminal/UI event sequencing."""

    ordered_results: list[tuple[dict[str, Any], Any]]
    deferred_start_calls: list[dict[str, Any]]


@dataclass(slots=True)
class TurnCodaSummary:
    """Final per-turn summary used by coda bookkeeping and logging."""

    step: int
    tool_error_count: int
    success: bool
    result_summary: str
    error_rate: float
    avg_latency: float
    context_usage: float
    task_state: TaskState


def build_assistant_turn_replay(
    *,
    decision: AssistantTurnDecision,
) -> AssistantMessageReplay:
    """Convert an assistant-turn decision into callback/transcript updates."""

    if decision.kind == "progress":
        transcript_messages: list[dict[str, Any]] = []
        if decision.assistant_content:
            transcript_messages.append(
                {"role": "assistant_progress", "content": decision.assistant_content}
            )
        if decision.user_content:
            transcript_messages.append({"role": "user", "content": decision.user_content})
        return AssistantMessageReplay(
            callback_kind="progress" if decision.assistant_content else None,
            callback_content=decision.assistant_content,
            transcript_messages=transcript_messages,
        )

    if decision.kind == "retry":
        transcript_messages = []
        if decision.user_content:
            transcript_messages.append({"role": "user", "content": decision.user_content})
        return AssistantMessageReplay(
            callback_kind=None,
            callback_content=None,
            transcript_messages=transcript_messages,
        )

    transcript_messages = []
    if decision.assistant_content:
        transcript_messages.append(
            {"role": "assistant", "content": decision.assistant_content}
        )
    return AssistantMessageReplay(
        callback_kind="assistant" if decision.assistant_content else None,
        callback_content=decision.assistant_content,
        transcript_messages=transcript_messages,
        should_return=True,
        protect_final_answer=decision.protect_final_answer,
    )


def build_step_content_replay(
    *,
    content: str,
    content_kind: str | None,
    has_calls: bool,
    nudge_continue: str,
) -> AssistantMessageReplay:
    """Normalize inline assistant content from a tool-call step for terminal replay."""

    if content_kind == "progress":
        return AssistantMessageReplay(
            callback_kind="progress",
            callback_content=content,
            transcript_messages=[
                {"role": "assistant_progress", "content": content},
                {"role": "user", "content": nudge_continue},
            ],
        )

    return AssistantMessageReplay(
        callback_kind="assistant",
        callback_content=content,
        transcript_messages=[{"role": "assistant", "content": content}],
        should_return=not has_calls,
    )


def build_tool_step_feedback(
    *,
    turn_state: TurnRecurrentState,
    context_usage: float,
    oscillation_index: float,
) -> ToolStepFeedback:
    """Build normalized measurements for step-end control feedback."""

    return ToolStepFeedback(
        error_rate=turn_state.tool_error_count / max(turn_state.step, 1),
        context_usage=context_usage,
        avg_latency=turn_state.step * 2.0,
        oscillation_index=oscillation_index,
    )


def apply_tool_step_feedback(
    *,
    feedback: ToolStepFeedback,
    decoupling_controller: Any | None,
    self_healing_engine: Any | None,
    log_healing: Callable[[str], None] | None = None,
) -> None:
    """Apply step-end controller feedback after tool execution."""

    if decoupling_controller:
        decoupling_controller.record_measurement(
            {
                "token_usage_to_latency": (
                    feedback.context_usage,
                    feedback.avg_latency / 60.0,
                ),
                "context_pressure_to_errors": (
                    feedback.context_usage,
                    feedback.error_rate,
                ),
            }
        )
        decoupling_controller.compute_decoupling_matrix()

    if self_healing_engine:
        healing_actions = self_healing_engine.detect_and_heal(
            {
                "error_rate": feedback.error_rate,
                "context_usage": feedback.context_usage,
                "oscillation_index": feedback.oscillation_index,
            }
        )
        if healing_actions and log_healing:
            log_healing(healing_actions[0].strategy)


def build_tool_result_context_output(
    *,
    turn_state: TurnRecurrentState,
    tool_name: str,
    result_output: str,
    ok: bool,
    classify_error: Callable[[str, str], Any],
    generate_nudge: Callable[[Any, int], str],
) -> str:
    """Build the tool_result content that should be fed back into the loop."""

    if ok:
        return result_output

    classified = classify_error(result_output, tool_name)
    nudge = generate_nudge(classified, turn_state.tool_error_count)
    return result_output + "\n\n[System note: " + nudge + "]"


def build_deferred_tool_replay(
    *,
    is_concurrency_safe: bool,
    total_call_count: int,
) -> DeferredToolReplay:
    """Determine whether callbacks/hooks must be replayed after concurrent execution."""

    return DeferredToolReplay(
        should_replay=is_concurrency_safe and total_call_count > 1,
    )


def build_tool_batch_plan(
    *,
    calls: list[dict[str, Any]],
    concurrent_calls: list[dict[str, Any]],
    serial_calls: list[dict[str, Any]],
    get_recommended_max_workers: Callable[[list[dict[str, Any]]], int],
) -> ToolBatchPlan:
    """Normalize a tool batch back into the model's original call order."""

    call_order = {call["id"]: index for index, call in enumerate(calls)}
    ordered_concurrent_calls = sorted(
        concurrent_calls,
        key=lambda call: call_order.get(call["id"], len(calls)),
    )
    ordered_serial_calls = sorted(
        serial_calls,
        key=lambda call: call_order.get(call["id"], len(calls)),
    )

    max_workers = (
        get_recommended_max_workers(ordered_concurrent_calls)
        if ordered_concurrent_calls
        else 1
    )

    return ToolBatchPlan(
        concurrent_calls=ordered_concurrent_calls,
        serial_calls=ordered_serial_calls,
        max_workers=max_workers,
    )


def build_tool_replay_plan(
    *,
    calls: list[dict[str, Any]],
    all_results: list[tuple[dict[str, Any], Any]],
    is_concurrency_safe: Callable[[str], bool],
) -> ToolReplayPlan:
    """Build a stable replay plan for tool callbacks and transcript ordering."""

    call_order = {call["id"]: index for index, call in enumerate(calls)}
    ordered_results = sorted(
        all_results,
        key=lambda pair: call_order.get(pair[0]["id"], len(calls)),
    )

    deferred_start_calls: list[dict[str, Any]] = []
    for call, _ in ordered_results:
        replay = build_deferred_tool_replay(
            is_concurrency_safe=is_concurrency_safe(call["toolName"]),
            total_call_count=len(calls),
        )
        if replay.should_replay:
            deferred_start_calls.append(call)

    return ToolReplayPlan(
        ordered_results=ordered_results,
        deferred_start_calls=deferred_start_calls,
    )


def collect_conflicting_failed_tool_names(
    *,
    call_id: str,
    ok: bool,
    all_results: list[tuple[dict[str, Any], Any]],
) -> list[str]:
    """Collect other failed tool names that should be marked as conflicts."""

    if ok or len(all_results) <= 1:
        return []

    conflicting_names: list[str] = []
    for other_call, other_result in all_results:
        if other_call["id"] == call_id:
            continue
        if not other_result.ok:
            conflicting_names.append(other_call["toolName"])
    return conflicting_names


def apply_read_dedup_to_tool_result(
    *,
    dedup_manager: Any | None,
    tool_name: str,
    tool_input: dict[str, Any],
    result_output: str,
    ok: bool,
    message_index: int,
    log_dedup: Callable[[str], None] | None = None,
) -> str:
    """Apply read-file deduplication and register the resulting transcript payload."""

    if dedup_manager is None or not ok or tool_name != "read_file":
        return result_output

    file_path = tool_input.get("path", "")
    if not file_path:
        return result_output

    if dedup_manager.should_dedup(file_path, result_output):
        result_output = dedup_manager.get_stub(file_path)
        if log_dedup:
            log_dedup(file_path)

    dedup_manager.register_read(file_path, result_output, message_index)
    return result_output


def build_tool_result_decision(
    *,
    call: dict[str, Any],
    tool_name: str,
    tool_input: dict[str, Any],
    result_output: str,
    is_error: bool,
    await_user: bool,
) -> ToolResultDecision:
    """Build transcript entries and await-user control flow for a tool result."""

    transcript_messages = [
        {
            "role": "assistant_tool_call",
            "toolUseId": call["id"],
            "toolName": tool_name,
            "input": tool_input,
        },
        {
            "role": "tool_result",
            "toolUseId": call["id"],
            "toolName": tool_name,
            "content": result_output,
            "isError": is_error,
        },
    ]
    return ToolResultDecision(
        tool_result_content=result_output,
        transcript_messages=transcript_messages,
        assistant_content=result_output if await_user else None,
        should_return=await_user,
    )


def build_tool_result_replay(
    *,
    call: dict[str, Any],
    result: Any,
    turn_state: TurnRecurrentState,
    total_call_count: int,
    is_concurrency_safe: bool,
    all_results: list[tuple[dict[str, Any], Any]],
    dedup_manager: Any | None,
    message_index: int,
    classify_error: Callable[[str, str], Any],
    generate_nudge: Callable[[Any, int], str],
    log_dedup: Callable[[str], None] | None = None,
) -> ToolResultReplay:
    """Normalize callback, transcript, and early-return decisions for one tool result."""

    deferred_replay = build_deferred_tool_replay(
        is_concurrency_safe=is_concurrency_safe,
        total_call_count=total_call_count,
    )

    turn_state.record_tool_result(result.ok)
    result_output = build_tool_result_context_output(
        turn_state=turn_state,
        tool_name=call["toolName"],
        result_output=result.output,
        ok=result.ok,
        classify_error=classify_error,
        generate_nudge=generate_nudge,
    )
    result_output = apply_read_dedup_to_tool_result(
        dedup_manager=dedup_manager,
        tool_name=call["toolName"],
        tool_input=call["input"],
        result_output=result_output,
        ok=result.ok,
        message_index=message_index,
        log_dedup=log_dedup,
    )

    return ToolResultReplay(
        callback_output=result.output,
        should_emit_callback=deferred_replay.should_replay,
        should_increment_tool_calls=deferred_replay.should_replay,
        conflicting_tool_names=collect_conflicting_failed_tool_names(
            call_id=call["id"],
            ok=result.ok,
            all_results=all_results,
        ),
        tool_decision=build_tool_result_decision(
            call=call,
            tool_name=call["toolName"],
            tool_input=call["input"],
            result_output=result_output,
            is_error=not result.ok,
            await_user=result.awaitUser,
        ),
    )


def build_turn_coda_summary(
    *,
    turn_state: TurnRecurrentState,
    context_usage: float,
) -> TurnCodaSummary:
    """Build a normalized turn summary for coda/finalization logic."""

    task_state = turn_state.final_task_state()
    success = task_state is TaskState.COMPLETED
    return TurnCodaSummary(
        step=turn_state.step,
        tool_error_count=turn_state.tool_error_count,
        success=success,
        result_summary=(
            f"Turn completed: {turn_state.step} steps, {turn_state.tool_error_count} errors"
        ),
        error_rate=turn_state.tool_error_count / max(turn_state.step, 1),
        avg_latency=turn_state.step * 2.0,
        context_usage=context_usage,
        task_state=task_state,
    )


def finalize_work_chain_task(
    *,
    task: Any | None,
    auditor: Any | None,
    coda_summary: TurnCodaSummary,
    success_outcome: Any,
    failure_outcome: Any,
) -> None:
    """Apply final task state and audit completion during coda."""

    if task is None:
        return

    task.set_state(coda_summary.task_state)
    task.result_summary = coda_summary.result_summary

    if auditor is None:
        return

    auditor.complete_decision(
        success_outcome if coda_summary.success else failure_outcome,
        coda_summary.step * 100.0,
        task.result_summary,
        task.error_message if not coda_summary.success else "",
    )


def decide_assistant_turn(
    *,
    turn_state: TurnRecurrentState,
    step_content: str,
    step_kind: str | None,
    stop_reason: str | None,
    block_types: list[str] | None,
    ignored_block_types: list[str] | None,
    is_empty: bool,
    treat_as_progress: bool,
    is_recoverable_thinking_stop: bool,
    format_diagnostics: Callable[[str | None, list[str] | None, list[str] | None], str],
    nudge_continue: str,
    nudge_after_tool_result: str,
    resume_after_pause: str,
    resume_after_max_tokens: str,
    nudge_after_empty_response: str,
    nudge_after_empty_no_tools: str,
) -> AssistantTurnDecision:
    """Decide how the loop should react to an assistant-only step."""

    if treat_as_progress:
        return AssistantTurnDecision(
            kind="progress",
            assistant_content=step_content,
            user_content=(
                nudge_after_tool_result
                if turn_state.saw_tool_result and step_kind != "progress"
                else nudge_continue
            ),
        )

    if is_recoverable_thinking_stop and turn_state.can_retry_recoverable_thinking():
        turn_state.record_recoverable_thinking_retry()
        progress_content = (
            "Model hit max_tokens during thinking; requesting the next step."
            if stop_reason == "max_tokens"
            else "Model returned pause_turn; requesting the next step."
        )
        return AssistantTurnDecision(
            kind="progress",
            assistant_content=progress_content,
            user_content=(
                resume_after_pause
                if stop_reason == "pause_turn"
                else resume_after_max_tokens
            ),
        )

    if is_empty and turn_state.can_retry_empty_response():
        turn_state.record_empty_response_retry()
        return AssistantTurnDecision(
            kind="retry",
            user_content=(
                nudge_after_empty_response
                if turn_state.saw_tool_result
                else nudge_after_empty_no_tools
            ),
        )

    if is_empty:
        diagnostics_suffix = format_diagnostics(
            stop_reason,
            block_types,
            ignored_block_types,
        )
        if turn_state.saw_tool_result:
            fallback = (
                "Model returned an empty response after tool execution and the turn "
                "was stopped. There were "
                f"{turn_state.tool_error_count} tool error(s); retry, adjust the "
                f"command, or choose a different approach.{diagnostics_suffix}"
                if turn_state.tool_error_count > 0
                else "Model returned an empty response after tool execution and the "
                "turn was stopped. Retry or ask the model to continue the remaining "
                f"steps.{diagnostics_suffix}"
            )
        else:
            fallback = (
                "Model returned an empty response and the turn was stopped."
                f"{diagnostics_suffix}"
            )
        return AssistantTurnDecision(kind="fallback", assistant_content=fallback)

    return AssistantTurnDecision(
        kind="final",
        assistant_content=step_content,
        protect_final_answer=True,
    )
