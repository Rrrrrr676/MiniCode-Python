from __future__ import annotations

from pathlib import Path

from minicode.tooling import ToolRegistry
from minicode.types import AgentStep, ChatMessage, ModelAdapter


class _DummyPermissions:
    def __init__(self, cwd: str, prompt=None) -> None:
        self.cwd = cwd
        self.prompt = prompt

    def get_summary(self) -> list[str]:
        return ["workspace writes allowed"]


class _DummyMemoryManager:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def get_relevant_context(self) -> dict[str, str]:
        return {}


class _ProviderUnavailableModel(ModelAdapter):
    model_id = "deepseek-v4-pro[1m]"

    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk=None,
        store=None,
    ) -> AgentStep:
        raise RuntimeError(
            "No available channel for model deepseek-v4-pro[1m] under group cc"
        )


def test_run_headless_forwards_runtime_to_agent_turn(monkeypatch, tmp_path: Path) -> None:
    import minicode.headless

    runtime = {
        "model": "deepseek-v4-pro[1m]",
        "baseUrl": "https://openai-proxy.example/v1",
        "authToken": "test-token",
    }
    captured: dict[str, object] = {}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "minicode.config.load_runtime_config",
        lambda cwd: runtime,
    )
    monkeypatch.setattr(
        "minicode.tools.create_default_tool_registry",
        lambda cwd, runtime=None: ToolRegistry([]),
    )
    monkeypatch.setattr("minicode.permissions.PermissionManager", _DummyPermissions)
    monkeypatch.setattr("minicode.memory.MemoryManager", _DummyMemoryManager)
    monkeypatch.setattr(
        "minicode.prompt.build_system_prompt",
        lambda cwd, permissions, context: "sys",
    )
    monkeypatch.setattr(
        "minicode.model_registry.create_model_adapter",
        lambda model, tools, runtime=None: object(),
    )

    def _fake_run_agent_turn(**kwargs):
        captured["runtime"] = kwargs["runtime"]
        return [{"role": "assistant", "content": "ok"}]

    monkeypatch.setattr("minicode.agent_loop.run_agent_turn", _fake_run_agent_turn)

    response = minicode.headless.run_headless("Reply with exactly OK.")

    assert response == "ok"
    assert captured["runtime"] is runtime


def test_run_headless_provider_failure_uses_runtime_channel_details(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import minicode.headless

    runtime = {
        "model": "deepseek-v4-pro[1m]",
        "baseUrl": "https://openai-proxy.example/v1",
        "authToken": "test-token",
    }

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINI_CODE_MODEL_FALLBACKS", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL_FALLBACKS", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_FALLBACKS", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL_FALLBACKS", raising=False)
    monkeypatch.setattr(
        "minicode.config.load_runtime_config",
        lambda cwd: runtime,
    )
    monkeypatch.setattr(
        "minicode.tools.create_default_tool_registry",
        lambda cwd, runtime=None: ToolRegistry([]),
    )
    monkeypatch.setattr("minicode.permissions.PermissionManager", _DummyPermissions)
    monkeypatch.setattr("minicode.memory.MemoryManager", _DummyMemoryManager)
    monkeypatch.setattr(
        "minicode.prompt.build_system_prompt",
        lambda cwd, permissions, context: "sys",
    )
    monkeypatch.setattr(
        "minicode.model_registry.create_model_adapter",
        lambda model, tools, runtime=None: _ProviderUnavailableModel(),
    )

    response = minicode.headless.run_headless("Reply with exactly OK.")

    assert "Provider availability failure:" in response
    assert "Active channel: anthropic-compatible via baseUrl/authToken." in response
    assert "Next step: Primary runtime is using a single anthropic-compatible channel from baseUrl/authToken." in response

