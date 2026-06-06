from minicode.task_object import TaskState
from minicode.turn_kernel import (
    AssistantMessageReplay,
    AssistantTurnDecision,
    DeferredToolReplay,
    ToolBatchPlan,
    ToolReplayPlan,
    ToolResultDecision,
    ToolResultReplay,
    ToolStepFeedback,
    TurnCodaSummary,
    apply_read_dedup_to_tool_result,
    apply_tool_step_feedback,
    build_assistant_turn_replay,
    build_step_content_replay,
    build_tool_batch_plan,
    build_deferred_tool_replay,
    build_tool_replay_plan,
    build_tool_result_context_output,
    build_tool_result_decision,
    build_tool_result_replay,
    build_turn_coda_summary,
    build_tool_step_feedback,
    collect_conflicting_failed_tool_names,
    TurnPreludeState,
    TurnRecurrentState,
    decide_assistant_turn,
    finalize_work_chain_task,
)


def test_turn_prelude_state_defaults() -> None:
    prelude = TurnPreludeState()

    assert prelude.task is None
    assert prelude.task_metadata == {}
    assert prelude.layered_context is None
    assert prelude.context_builder is None
    assert prelude.auditor is None


def test_turn_recurrent_state_tracks_retries_and_errors() -> None:
    state = TurnRecurrentState(max_steps=2)

    assert state.has_remaining_steps()
    assert state.begin_step() == 1
    assert state.step == 1
    assert state.can_retry_empty_response()
    assert state.can_retry_recoverable_thinking()

    state.record_empty_response_retry()
    state.record_recoverable_thinking_retry()
    state.record_tool_result(ok=False)

    assert state.saw_tool_result is True
    assert state.empty_response_retry_count == 1
    assert state.recoverable_thinking_retry_count == 1
    assert state.tool_error_count == 1
    assert state.final_task_state() is TaskState.FAILED

    assert state.begin_step() == 2
    assert state.has_remaining_steps() is False


def test_turn_recurrent_state_successful_completion() -> None:
    state = TurnRecurrentState(max_steps=None)

    state.record_tool_result(ok=True)

    assert state.saw_tool_result is True
    assert state.tool_error_count == 0
    assert state.final_task_state() is TaskState.COMPLETED


def test_decide_assistant_turn_retries_recoverable_pause() -> None:
    state = TurnRecurrentState(max_steps=3)

    decision = decide_assistant_turn(
        turn_state=state,
        step_content="",
        step_kind=None,
        stop_reason="pause_turn",
        block_types=None,
        ignored_block_types=["thinking"],
        is_empty=True,
        treat_as_progress=False,
        is_recoverable_thinking_stop=True,
        format_diagnostics=lambda *_: "",
        nudge_continue="continue",
        nudge_after_tool_result="after tool",
        resume_after_pause="resume pause",
        resume_after_max_tokens="resume max",
        nudge_after_empty_response="empty after tool",
        nudge_after_empty_no_tools="empty no tool",
    )

    assert decision.kind == "progress"
    assert decision.assistant_content == "Model returned pause_turn; requesting the next step."
    assert decision.user_content == "resume pause"
    assert state.recoverable_thinking_retry_count == 1


def test_decide_assistant_turn_builds_fallback_after_empty_tool_response() -> None:
    state = TurnRecurrentState(max_steps=3, saw_tool_result=True, tool_error_count=2)
    state.empty_response_retry_count = 2

    decision = decide_assistant_turn(
        turn_state=state,
        step_content="",
        step_kind=None,
        stop_reason="max_tokens",
        block_types=["tool"],
        ignored_block_types=["thinking"],
        is_empty=True,
        treat_as_progress=False,
        is_recoverable_thinking_stop=False,
        format_diagnostics=lambda stop, blocks, ignored: (
            f" Diagnostics: stop_reason={stop}; blocks={','.join(blocks or [])}; "
            f"ignored={','.join(ignored or [])}."
        ),
        nudge_continue="continue",
        nudge_after_tool_result="after tool",
        resume_after_pause="resume pause",
        resume_after_max_tokens="resume max",
        nudge_after_empty_response="empty after tool",
        nudge_after_empty_no_tools="empty no tool",
    )

    assert decision.kind == "fallback"
    assert "2 tool error(s)" in (decision.assistant_content or "")
    assert "stop_reason=max_tokens" in (decision.assistant_content or "")


def test_build_assistant_turn_replay_keeps_progress_then_nudge_order() -> None:
    replay = build_assistant_turn_replay(
        decision=AssistantTurnDecision(
            kind="progress",
            assistant_content="working",
            user_content="continue now",
        )
    )

    assert replay == AssistantMessageReplay(
        callback_kind="progress",
        callback_content="working",
        transcript_messages=[
            {"role": "assistant_progress", "content": "working"},
            {"role": "user", "content": "continue now"},
        ],
        should_return=False,
        protect_final_answer=False,
    )


def test_build_step_content_replay_returns_after_plain_assistant_content() -> None:
    replay = build_step_content_replay(
        content="done",
        content_kind=None,
        has_calls=False,
        nudge_continue="continue now",
    )

    assert replay == AssistantMessageReplay(
        callback_kind="assistant",
        callback_content="done",
        transcript_messages=[{"role": "assistant", "content": "done"}],
        should_return=True,
        protect_final_answer=False,
    )


def test_build_tool_step_feedback_normalizes_metrics() -> None:
    state = TurnRecurrentState(max_steps=5, tool_error_count=2, step=4)

    feedback = build_tool_step_feedback(
        turn_state=state,
        context_usage=0.75,
        oscillation_index=0.2,
    )

    assert feedback == ToolStepFeedback(
        error_rate=0.5,
        context_usage=0.75,
        avg_latency=8.0,
        oscillation_index=0.2,
    )


def test_apply_tool_step_feedback_drives_controllers() -> None:
    feedback = ToolStepFeedback(
        error_rate=0.5,
        context_usage=0.25,
        avg_latency=6.0,
        oscillation_index=0.1,
    )
    healing_logs: list[str] = []

    class FakeDecouplingController:
        def __init__(self) -> None:
            self.measurement = None
            self.computed = False

        def record_measurement(self, measurement) -> None:
            self.measurement = measurement

        def compute_decoupling_matrix(self) -> None:
            self.computed = True

    class FakeHealingAction:
        def __init__(self, strategy: str) -> None:
            self.strategy = strategy

    class FakeSelfHealingEngine:
        def __init__(self) -> None:
            self.metrics = None

        def detect_and_heal(self, metrics):
            self.metrics = metrics
            return [FakeHealingAction("compact")]

    decoupling = FakeDecouplingController()
    healing = FakeSelfHealingEngine()

    apply_tool_step_feedback(
        feedback=feedback,
        decoupling_controller=decoupling,
        self_healing_engine=healing,
        log_healing=healing_logs.append,
    )

    assert decoupling.measurement == {
        "token_usage_to_latency": (0.25, 0.1),
        "context_pressure_to_errors": (0.25, 0.5),
    }
    assert decoupling.computed is True
    assert healing.metrics == {
        "error_rate": 0.5,
        "context_usage": 0.25,
        "oscillation_index": 0.1,
    }
    assert healing_logs == ["compact"]


def test_build_tool_result_context_output_appends_retry_nudge() -> None:
    state = TurnRecurrentState(max_steps=4, tool_error_count=2, step=2)

    output = build_tool_result_context_output(
        turn_state=state,
        tool_name="shell",
        result_output="boom",
        ok=False,
        classify_error=lambda output, tool_name: {
            "output": output,
            "tool_name": tool_name,
        },
        generate_nudge=lambda classified, retry_count: (
            f"retry {retry_count} for {classified['tool_name']}"
        ),
    )

    assert output == "boom\n\n[System note: retry 2 for shell]"


def test_build_tool_result_decision_returns_transcript_and_await_user() -> None:
    decision = build_tool_result_decision(
        call={"id": "call-1"},
        tool_name="ask_user",
        tool_input={"question": "continue?"},
        result_output="Need approval",
        is_error=False,
        await_user=True,
    )

    assert decision == ToolResultDecision(
        tool_result_content="Need approval",
        transcript_messages=[
            {
                "role": "assistant_tool_call",
                "toolUseId": "call-1",
                "toolName": "ask_user",
                "input": {"question": "continue?"},
            },
            {
                "role": "tool_result",
                "toolUseId": "call-1",
                "toolName": "ask_user",
                "content": "Need approval",
                "isError": False,
            },
        ],
        assistant_content="Need approval",
        should_return=True,
    )


def test_build_tool_result_replay_normalizes_callback_and_transcript() -> None:
    class FakeDedupManager:
        def __init__(self) -> None:
            self.registered = []

        def should_dedup(self, file_path: str, content: str) -> bool:
            return file_path == "a.py" and content == "same content"

        def get_stub(self, file_path: str) -> str:
            return f"stub:{file_path}"

        def register_read(self, file_path: str, content: str, message_index: int) -> None:
            self.registered.append((file_path, content, message_index))

    dedup = FakeDedupManager()
    turn_state = TurnRecurrentState(max_steps=4)
    log_messages: list[str] = []
    call = {"id": "call-1", "toolName": "read_file", "input": {"path": "a.py"}}
    result = type(
        "R",
        (),
        {"ok": True, "output": "same content", "awaitUser": False},
    )()

    replay = build_tool_result_replay(
        call=call,
        result=result,
        turn_state=turn_state,
        total_call_count=2,
        is_concurrency_safe=True,
        all_results=[(call, result)],
        dedup_manager=dedup,
        message_index=5,
        classify_error=lambda output, tool_name: {
            "output": output,
            "tool_name": tool_name,
        },
        generate_nudge=lambda classified, retry_count: (
            f"retry {retry_count} for {classified['tool_name']}"
        ),
        log_dedup=log_messages.append,
    )

    assert replay == ToolResultReplay(
        callback_output="same content",
        should_emit_callback=True,
        should_increment_tool_calls=True,
        conflicting_tool_names=[],
        tool_decision=ToolResultDecision(
            tool_result_content="stub:a.py",
            transcript_messages=[
                {
                    "role": "assistant_tool_call",
                    "toolUseId": "call-1",
                    "toolName": "read_file",
                    "input": {"path": "a.py"},
                },
                {
                    "role": "tool_result",
                    "toolUseId": "call-1",
                    "toolName": "read_file",
                    "content": "stub:a.py",
                    "isError": False,
                },
            ],
            assistant_content=None,
            should_return=False,
        ),
    )
    assert turn_state.saw_tool_result is True
    assert dedup.registered == [("a.py", "stub:a.py", 5)]
    assert log_messages == ["a.py"]


def test_build_deferred_tool_replay_only_for_parallel_safe_tools() -> None:
    replay = build_deferred_tool_replay(
        is_concurrency_safe=True,
        total_call_count=2,
    )
    no_replay = build_deferred_tool_replay(
        is_concurrency_safe=False,
        total_call_count=2,
    )

    assert replay == DeferredToolReplay(should_replay=True)
    assert no_replay == DeferredToolReplay(should_replay=False)


def test_build_tool_batch_plan_restores_model_call_order() -> None:
    calls = [
        {"id": "1", "toolName": "read_file", "input": {"path": "a.py"}},
        {"id": "2", "toolName": "write_file", "input": {"path": "b.py"}},
        {"id": "3", "toolName": "list_files", "input": {"path": "."}},
        {"id": "4", "toolName": "edit_file", "input": {"path": "c.py"}},
    ]
    worker_inputs: list[list[str]] = []

    plan = build_tool_batch_plan(
        calls=calls,
        concurrent_calls=[calls[2], calls[0]],
        serial_calls=[calls[3], calls[1]],
        get_recommended_max_workers=lambda ordered_calls: (
            worker_inputs.append([call["id"] for call in ordered_calls]) or 3
        ),
    )

    assert plan == ToolBatchPlan(
        concurrent_calls=[calls[0], calls[2]],
        serial_calls=[calls[1], calls[3]],
        max_workers=3,
    )
    assert worker_inputs == [["1", "3"]]


def test_build_tool_replay_plan_preserves_call_order_and_deferred_starts() -> None:
    calls = [
        {"id": "1", "toolName": "read_file", "input": {"path": "a.py"}},
        {"id": "2", "toolName": "write_file", "input": {"path": "b.py"}},
        {"id": "3", "toolName": "list_files", "input": {"path": "."}},
    ]
    all_results = [
        (calls[2], type("R", (), {"ok": True})()),
        (calls[0], type("R", (), {"ok": True})()),
        (calls[1], type("R", (), {"ok": True})()),
    ]

    plan = build_tool_replay_plan(
        calls=calls,
        all_results=all_results,
        is_concurrency_safe=lambda tool_name: tool_name in {"read_file", "list_files"},
    )

    assert plan == ToolReplayPlan(
        ordered_results=[
            (calls[0], all_results[1][1]),
            (calls[1], all_results[2][1]),
            (calls[2], all_results[0][1]),
        ],
        deferred_start_calls=[calls[0], calls[2]],
    )


def test_collect_conflicting_failed_tool_names_returns_other_failures() -> None:
    conflicts = collect_conflicting_failed_tool_names(
        call_id="1",
        ok=False,
        all_results=[
            ({"id": "1", "toolName": "read_file"}, type("R", (), {"ok": False})()),
            ({"id": "2", "toolName": "grep_files"}, type("R", (), {"ok": False})()),
            ({"id": "3", "toolName": "ls"}, type("R", (), {"ok": True})()),
        ],
    )

    assert conflicts == ["grep_files"]


def test_apply_read_dedup_to_tool_result_replaces_duplicate_reads() -> None:
    log_messages: list[str] = []

    class FakeDedupManager:
        def __init__(self) -> None:
            self.registered = []

        def should_dedup(self, file_path: str, content: str) -> bool:
            return file_path == "a.py" and content == "same content"

        def get_stub(self, file_path: str) -> str:
            return f"stub:{file_path}"

        def register_read(self, file_path: str, content: str, message_index: int) -> None:
            self.registered.append((file_path, content, message_index))

    dedup = FakeDedupManager()

    result = apply_read_dedup_to_tool_result(
        dedup_manager=dedup,
        tool_name="read_file",
        tool_input={"path": "a.py"},
        result_output="same content",
        ok=True,
        message_index=5,
        log_dedup=log_messages.append,
    )

    assert result == "stub:a.py"
    assert dedup.registered == [("a.py", "stub:a.py", 5)]
    assert log_messages == ["a.py"]


def test_build_turn_coda_summary_normalizes_final_metrics() -> None:
    state = TurnRecurrentState(max_steps=5, tool_error_count=1, step=4)

    summary = build_turn_coda_summary(
        turn_state=state,
        context_usage=0.4,
    )

    assert summary == TurnCodaSummary(
        step=4,
        tool_error_count=1,
        success=False,
        result_summary="Turn completed: 4 steps, 1 errors",
        error_rate=0.25,
        avg_latency=8.0,
        context_usage=0.4,
        task_state=TaskState.FAILED,
    )


def test_finalize_work_chain_task_updates_task_and_auditor() -> None:
    class FakeTask:
        def __init__(self) -> None:
            self.state = None
            self.result_summary = ""
            self.error_message = "tool failed"

        def set_state(self, state: TaskState) -> None:
            self.state = state

    class FakeAuditor:
        def __init__(self) -> None:
            self.calls = []

        def complete_decision(
            self,
            outcome,
            confidence: float,
            summary: str,
            error_message: str,
        ) -> None:
            self.calls.append((outcome, confidence, summary, error_message))

    task = FakeTask()
    auditor = FakeAuditor()
    summary = TurnCodaSummary(
        step=3,
        tool_error_count=1,
        success=False,
        result_summary="Turn completed: 3 steps, 1 errors",
        error_rate=1 / 3,
        avg_latency=6.0,
        context_usage=0.5,
        task_state=TaskState.FAILED,
    )

    finalize_work_chain_task(
        task=task,
        auditor=auditor,
        coda_summary=summary,
        success_outcome="success",
        failure_outcome="failure",
    )

    assert task.state is TaskState.FAILED
    assert task.result_summary == "Turn completed: 3 steps, 1 errors"
    assert auditor.calls == [
        (
            "failure",
            300.0,
            "Turn completed: 3 steps, 1 errors",
            "tool failed",
        )
    ]
