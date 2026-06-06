import minicode.agent_loop as agent_loop_module
from minicode.agent_loop import run_agent_turn
from minicode.state import create_app_store
from minicode.tooling import ToolCapability, ToolDefinition, ToolMetadata, ToolRegistry, ToolResult
from minicode.types import AgentStep, ChatMessage, ModelAdapter, StepDiagnostics


class ScriptedModel(ModelAdapter):
    def __init__(self, steps: list[AgentStep]) -> None:
        self._steps = steps
        self.calls = 0

    def next(self, messages: list[ChatMessage], on_stream_chunk=None) -> AgentStep:
        step = self._steps[self.calls]
        self.calls += 1
        return step


class StoreCapturingModel(ModelAdapter):
    def __init__(self) -> None:
        self.received_store = None

    def next(self, messages: list[ChatMessage], on_stream_chunk=None, store=None) -> AgentStep:
        self.received_store = store
        return AgentStep(type="assistant", content="done")


def test_agent_turn_executes_tool_and_returns_assistant() -> None:
    def run_echo(input_data: dict, _context) -> ToolResult:
        return ToolResult(ok=True, output=f"echo:{input_data['text']}")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="echo",
                description="echo tool",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_echo,
            )
        ]
    )
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[{"id": "1", "toolName": "echo", "input": {"text": "hi"}}],
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    assert messages[-1] == {"role": "assistant", "content": "done"}
    assert any(message["role"] == "tool_result" for message in messages)


def test_agent_turn_emits_callbacks() -> None:
    events: list[tuple[str, str]] = []

    def run_echo(input_data: dict, _context) -> ToolResult:
        return ToolResult(ok=True, output=f"echo:{input_data['text']}")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="echo",
                description="echo tool",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_echo,
            )
        ]
    )
    model = ScriptedModel(
        [
            AgentStep(type="tool_calls", content="working", contentKind="progress", calls=[{"id": "1", "toolName": "echo", "input": {"text": "hi"}}]),
            AgentStep(type="assistant", content="done"),
        ]
    )

    run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
        on_tool_start=lambda name, _input: events.append(("start", name)),
        on_tool_result=lambda name, _output, _error: events.append(("result", name)),
        on_assistant_message=lambda content: events.append(("assistant", content)),
        on_progress_message=lambda content: events.append(("progress", content)),
    )

    assert ("progress", "working") in events
    assert ("start", "echo") in events
    assert ("result", "echo") in events
    assert ("assistant", "done") in events


def test_agent_turn_keeps_progress_and_nudge_ahead_of_tool_results() -> None:
    def run_echo(input_data: dict, _context) -> ToolResult:
        return ToolResult(ok=True, output=f"echo:{input_data['text']}")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="echo",
                description="echo tool",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_echo,
            )
        ]
    )
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                content="working",
                contentKind="progress",
                calls=[{"id": "1", "toolName": "echo", "input": {"text": "hi"}}],
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    progress_index = next(
        index
        for index, message in enumerate(messages)
        if message == {"role": "assistant_progress", "content": "working"}
    )
    nudge_index = next(
        index
        for index, message in enumerate(messages)
        if message["role"] == "user" and "Continue immediately" in message["content"]
    )
    tool_result_index = next(
        index
        for index, message in enumerate(messages)
        if message["role"] == "tool_result"
    )

    assert progress_index < nudge_index < tool_result_index


def test_agent_turn_retries_empty_response_then_continues() -> None:
    model = ScriptedModel(
        [
            AgentStep(type="assistant", content=""),
            AgentStep(type="assistant", content="done"),
        ]
    )
    registry = ToolRegistry([])

    messages = run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    assert messages[-1] == {"role": "assistant", "content": "done"}
    assert any(
        message["role"] == "user" and "last response was empty" in message["content"]
        for message in messages
    )


def test_agent_turn_handles_recoverable_pause_turn() -> None:
    model = ScriptedModel(
        [
            AgentStep(
                type="assistant",
                content="",
                diagnostics=StepDiagnostics(stopReason="pause_turn", ignoredBlockTypes=["thinking"]),
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )
    registry = ToolRegistry([])
    progress_events: list[str] = []

    messages = run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
        on_progress_message=progress_events.append,
    )

    assert messages[-1] == {"role": "assistant", "content": "done"}
    assert any("pause_turn" in event for event in progress_events)


def test_agent_turn_returns_fallback_after_repeated_empty_responses() -> None:
    model = ScriptedModel(
        [
            AgentStep(type="assistant", content=""),
            AgentStep(type="assistant", content=""),
            AgentStep(type="assistant", content=""),
        ]
    )
    registry = ToolRegistry([])

    messages = run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    assert "empty response" in messages[-1]["content"].lower()


def test_agent_turn_with_zero_max_steps_returns_limit_fallback() -> None:
    registry = ToolRegistry([])
    model = ScriptedModel([AgentStep(type="assistant", content="unused")])

    messages = run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
        max_steps=0,
    )

    assert messages[-1] == {
        "role": "assistant",
        "content": "Reached the maximum tool step limit for this turn.",
    }
    assert model.calls == 0


def test_tool_registry_dispose_calls_disposer() -> None:
    disposed: list[bool] = []
    registry = ToolRegistry([], disposer=lambda: disposed.append(True))

    registry.dispose()

    assert disposed == [True]


def test_agent_turn_passes_store_to_provider_adapter() -> None:
    model = StoreCapturingModel()
    registry = ToolRegistry([])
    store = create_app_store()

    messages = run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
        store=store,
    )

    assert messages[-1] == {"role": "assistant", "content": "done"}
    assert model.received_store is store


def test_agent_turn_returns_after_await_user_tool() -> None:
    def run_ask_user(input_data: dict, _context) -> ToolResult:
        return ToolResult(ok=True, output=input_data["question"], awaitUser=True)

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="ask_user",
                description="ask user tool",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_ask_user,
            )
        ]
    )
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[
                    {
                        "id": "1",
                        "toolName": "ask_user",
                        "input": {"question": "Need approval"},
                    }
                ],
            ),
            AgentStep(type="assistant", content="unused"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    assert messages[-1] == {"role": "assistant", "content": "Need approval"}
    assert model.calls == 1


def test_agent_turn_replays_all_concurrent_results_before_await_user_return() -> None:
    def run_tool(input_data: dict, _context) -> ToolResult:
        if input_data["kind"] == "ask":
            return ToolResult(ok=True, output="Need approval", awaitUser=True)
        return ToolResult(ok=True, output="a.py\nb.py")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="ask_user",
                description="ask user tool",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_tool,
                metadata=ToolMetadata(
                    name="ask_user",
                    description="ask user tool",
                    capabilities={ToolCapability.CONCURRENCY_SAFE},
                ),
            ),
            ToolDefinition(
                name="list_files",
                description="list files",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_tool,
                metadata=ToolMetadata(
                    name="list_files",
                    description="list files",
                    capabilities={ToolCapability.CONCURRENCY_SAFE},
                ),
            ),
        ]
    )
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[
                    {"id": "1", "toolName": "ask_user", "input": {"kind": "ask"}},
                    {"id": "2", "toolName": "list_files", "input": {"kind": "list"}},
                ],
            ),
            AgentStep(type="assistant", content="unused"),
        ]
    )

    messages = run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
    )

    tool_results = [message for message in messages if message["role"] == "tool_result"]
    assert len(tool_results) == 2
    assert tool_results[0]["toolName"] == "ask_user"
    assert tool_results[1]["toolName"] == "list_files"
    assert messages[-1] == {"role": "assistant", "content": "Need approval"}
    assert model.calls == 1


def test_agent_turn_replays_concurrent_tool_starts_before_results() -> None:
    events: list[tuple[str, str]] = []

    def run_read(input_data: dict, _context) -> ToolResult:
        return ToolResult(ok=True, output=f"read:{input_data['path']}")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="read_file",
                description="read file",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_read,
                metadata=ToolMetadata(
                    name="read_file",
                    description="read file",
                    capabilities={ToolCapability.CONCURRENCY_SAFE},
                ),
            ),
            ToolDefinition(
                name="list_files",
                description="list files",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_read,
                metadata=ToolMetadata(
                    name="list_files",
                    description="list files",
                    capabilities={ToolCapability.CONCURRENCY_SAFE},
                ),
            ),
        ]
    )
    model = ScriptedModel(
        [
            AgentStep(
                type="tool_calls",
                calls=[
                    {"id": "1", "toolName": "read_file", "input": {"path": "a.py"}},
                    {"id": "2", "toolName": "list_files", "input": {"path": "."}},
                ],
            ),
            AgentStep(type="assistant", content="done"),
        ]
    )

    run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
        on_tool_start=lambda name, _input: events.append(("start", name)),
        on_tool_result=lambda name, _output, _error: events.append(("result", name)),
    )

    assert events[:4] == [
        ("start", "read_file"),
        ("start", "list_files"),
        ("result", "read_file"),
        ("result", "list_files"),
    ]


def test_agent_turn_reorders_batch_for_terminal_friendly_progress(monkeypatch) -> None:
    events: list[tuple[str, str]] = []
    execution_order: list[str] = []

    def run_tool(input_data: dict, _context) -> ToolResult:
        execution_order.append(input_data["name"])
        return ToolResult(ok=True, output=f"ok:{input_data['name']}")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="read_file",
                description="read file",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_tool,
                metadata=ToolMetadata(
                    name="read_file",
                    description="read file",
                    capabilities={ToolCapability.CONCURRENCY_SAFE},
                ),
            ),
            ToolDefinition(
                name="list_files",
                description="list files",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_tool,
                metadata=ToolMetadata(
                    name="list_files",
                    description="list files",
                    capabilities={ToolCapability.CONCURRENCY_SAFE},
                ),
            ),
            ToolDefinition(
                name="write_file",
                description="write file",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_tool,
            ),
            ToolDefinition(
                name="edit_file",
                description="edit file",
                input_schema={"type": "object"},
                validator=lambda value: value,
                run=run_tool,
            ),
        ]
    )
    calls = [
        {"id": "1", "toolName": "read_file", "input": {"name": "read"}},
        {"id": "2", "toolName": "write_file", "input": {"name": "write"}},
        {"id": "3", "toolName": "list_files", "input": {"name": "list"}},
        {"id": "4", "toolName": "edit_file", "input": {"name": "edit"}},
    ]
    model = ScriptedModel(
        [
            AgentStep(type="tool_calls", calls=calls),
            AgentStep(type="assistant", content="done"),
        ]
    )

    def fake_schedule_calls(self, raw_calls, _tools):
        assert raw_calls == calls
        return [raw_calls[2], raw_calls[0]], [raw_calls[3], raw_calls[1]]

    monkeypatch.setattr(
        agent_loop_module.ToolScheduler,
        "schedule_calls",
        fake_schedule_calls,
    )
    monkeypatch.setattr(
        agent_loop_module.ToolScheduler,
        "get_recommended_max_workers",
        lambda self, raw_calls: len(raw_calls),
    )

    run_agent_turn(
        model=model,
        tools=registry,
        messages=[{"role": "system", "content": "sys"}],
        cwd=".",
        on_tool_start=lambda name, _input: events.append(("start", name)),
        on_tool_result=lambda name, _output, _error: events.append(("result", name)),
    )

    assert events[:4] == [
        ("start", "read_file"),
        ("start", "list_files"),
        ("start", "write_file"),
        ("result", "write_file"),
    ]
    assert ("start", "edit_file") in events
    assert execution_order[-2:] == ["write", "edit"]
