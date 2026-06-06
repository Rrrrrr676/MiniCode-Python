from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minicode.runtime_profile_eval import (
    ProviderDiagnostic,
    RuntimeEvalCondition,
    RuntimeEvalScenario,
    evaluate_runtime_profiles,
    runtime_profile_eval_as_dict,
    runtime_profile_eval_as_markdown,
)
from minicode.tooling import ToolRegistry
from minicode.types import AgentStep, ChatMessage, ModelAdapter


class ScriptedModel(ModelAdapter):
    def __init__(self, steps: list[AgentStep]) -> None:
        self._steps = steps
        self.calls = 0

    def next(self, messages: list[ChatMessage], on_stream_chunk=None) -> AgentStep:
        step = self._steps[self.calls]
        self.calls += 1
        return step


def build_demo_scenarios() -> list[RuntimeEvalScenario]:
    return [
        RuntimeEvalScenario(
            name="depth-budget-floor",
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "repair the runtime policy"},
            ],
            model_factory=lambda: ScriptedModel(
                [
                    AgentStep(
                        type="assistant",
                        content="scanning the relevant files",
                        kind="progress",
                    ),
                    AgentStep(type="assistant", content="done"),
                ]
            ),
            tools_factory=lambda: ToolRegistry([]),
            max_steps=1,
        ),
        RuntimeEvalScenario(
            name="widening-escalation",
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "repair the runtime policy"},
            ],
            model_factory=lambda: ScriptedModel(
                [
                    AgentStep(type="assistant", content="still exploring", kind="progress"),
                    AgentStep(type="assistant", content="still exploring", kind="progress"),
                    AgentStep(type="assistant", content="still exploring", kind="progress"),
                    AgentStep(type="assistant", content="still exploring", kind="progress"),
                    AgentStep(type="assistant", content="still exploring", kind="progress"),
                    AgentStep(type="assistant", content=""),
                    AgentStep(type="assistant", content=""),
                    AgentStep(type="assistant", content=""),
                    AgentStep(type="assistant", content=""),
                    AgentStep(type="assistant", content="done with a broader plan"),
                ]
            ),
            tools_factory=lambda: ToolRegistry([]),
        ),
    ]


def build_demo_conditions() -> list[RuntimeEvalCondition]:
    return [
        RuntimeEvalCondition(
            label="single",
            runtime={"runtimeProfile": "single"},
            max_steps=1,
        ),
        RuntimeEvalCondition(
            label="single-deep",
            runtime={"runtimeProfile": "single-deep"},
            max_steps=1,
        ),
    ]


def _classify_provider_diagnostic(
    *,
    label: str,
    command: str,
    exit_code: int,
    stdout: str,
    stderr: str,
) -> ProviderDiagnostic:
    combined = " ".join(f"{stdout}\n{stderr}".lower().split())
    stripped_stdout = stdout.strip()
    summary_source = stripped_stdout or stderr.strip()
    summary_line = summary_source.splitlines()[0].strip() if summary_source else ""
    if exit_code == 0 and stripped_stdout == "OK":
        outcome = "answered"
    elif (
        "provider availability failure" in combined
        or "all viable fallback models were unavailable" in combined
        or "no available channel" in combined
    ):
        outcome = "provider_outage"
    elif "empty response" in combined:
        outcome = "empty_output"
    else:
        outcome = "error"
    return ProviderDiagnostic(
        label=label,
        outcome=outcome,
        command=command,
        exit_code=exit_code,
        summary=summary_line or f"{label}: {outcome}",
        stdout=stdout,
        stderr=stderr,
    )


def collect_provider_diagnostics() -> list[ProviderDiagnostic]:
    command = [sys.executable, "-m", "minicode.headless", "Reply with exactly OK."]
    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        return [
            _classify_provider_diagnostic(
                label="headless-smoke",
                command=" ".join(command),
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        ]
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return [
            ProviderDiagnostic(
                label="headless-smoke",
                outcome="timeout",
                command=" ".join(command),
                exit_code=124,
                summary="Headless provider smoke timed out.",
                stdout=stdout if isinstance(stdout, str) else "",
                stderr=stderr if isinstance(stderr, str) else "",
            )
        ]


def main() -> None:
    rows = evaluate_runtime_profiles(
        scenarios=build_demo_scenarios(),
        conditions=build_demo_conditions(),
    )
    provider_diagnostics = collect_provider_diagnostics()
    payload = runtime_profile_eval_as_dict(rows, provider_diagnostics)
    output_path = Path("benchmarks") / "runtime_profile_eval_results.json"
    markdown_path = Path("benchmarks") / "runtime_profile_eval_results.md"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(
        runtime_profile_eval_as_markdown(rows, provider_diagnostics),
        encoding="utf-8",
    )
    print(output_path)
    print(markdown_path)


if __name__ == "__main__":
    main()
