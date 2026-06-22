from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol, TypedDict


# 会话消息的统一类型
class ChatMessage(TypedDict, total=False):
    # 消息的角色，支持六种
    role: Literal[
        "system",
        "user",
        "assistant", # 助手消息
        "assistant_progress", # 助手中间进度消息
        "assistant_tool_call", # 助手工具调用
        "tool_result", # 工具调用结果
    ]
    content: str
    toolUseId: str
    toolName: str
    input: Any
    isError: bool


# 单次工具调用描述
class ToolCall(TypedDict):
    id: str
    toolName: str
    input: Any


# 步骤诊断信息：模型单次API响应的底层诊断数据
@dataclass(slots=True)
class StepDiagnostics:
    stopReason: str | None = None
    blockTypes: list[str] = field(default_factory=list)
    ignoredBlockTypes: list[str] = field(default_factory=list)


# 模型单步输出，模型一次调用的完整输出，包括两种类型：文本回复、请求工具调用
@dataclass(slots=True)
class AgentStep:
    type: Literal["assistant", "tool_calls"]
    content: str = ""
    kind: Literal["final", "progress"] | None = None
    calls: list[ToolCall] = field(default_factory=list)
    contentKind: Literal["progress"] | None = None
    diagnostics: StepDiagnostics | None = None


# 运行时事件的类别
RuntimeEventCategory = Literal[
    "phase",
    "compaction",
    "guard",
    "widening",
    "recovery",
    "stop",
]


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    category: RuntimeEventCategory
    message: str
    step: int | None = None
    profile: str = ""
    phase: str = ""
    verification_focus: str = ""
    stop_reason: str = ""
    widening_reason: str = ""
    evidence_summary: str = ""


# 模型适配器协议
class ModelAdapter(Protocol):
    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk: Callable[[str], None] | None = None,
        store: Any | None = None,
    ) -> AgentStep: ...
