from minicode.release_readiness import (
    ReleaseCheck,
    classify_provider_outcome,
    release_readiness_as_dict,
    release_readiness_as_markdown,
    summarize_release_status,
)


def _check(label: str, *, status: str = "passed", exit_code: int = 0, summary: str | None = None) -> ReleaseCheck:
    return ReleaseCheck(
        label=label,
        command=f"python -m {label}",
        exit_code=exit_code,
        status=status,
        summary=summary or f"{label} completed.",
    )


def test_classify_provider_outcome_detects_answered_and_provider_outage() -> None:
    answered = classify_provider_outcome(exit_code=0, stdout="OK", stderr="")
    outage = classify_provider_outcome(
        exit_code=1,
        stdout="",
        stderr="Provider availability failure: all viable fallback models were unavailable.",
    )

    assert answered == ("answered", "OK")
    assert outage == ("provider_outage", "Provider availability failure: all viable fallback models were unavailable.")


def test_summarize_release_status_treats_provider_outage_as_warning() -> None:
    status = summarize_release_status(
        compile_check=_check("compileall"),
        test_check=_check("pytest-q"),
        runtime_eval_check=_check("runtime-profile-eval"),
        smoke_checks=[_check("inspect-session"), _check("replay-session")],
        provider_outcomes=["provider_outage"],
        readiness_report={"fallback_ready": True},
    )

    assert status == "warning"


def test_summarize_release_status_escalates_provider_outage_without_fallbacks() -> None:
    status = summarize_release_status(
        compile_check=_check("compileall"),
        test_check=_check("pytest-q"),
        runtime_eval_check=_check("runtime-profile-eval"),
        smoke_checks=[_check("inspect-session"), _check("replay-session")],
        provider_outcomes=["provider_outage"],
        readiness_report={"fallback_ready": False},
    )

    assert status == "at-risk"


def test_release_readiness_outputs_include_provider_diagnostics_and_artifacts() -> None:
    compile_check = _check("compileall")
    test_check = _check("pytest-q")
    runtime_eval_check = _check("runtime-profile-eval", summary="runtime eval completed.")
    smoke_checks = [
        _check("list-sessions", summary="2 sessions listed."),
        _check("preview-rewind", summary="rewind preview completed."),
    ]
    diagnostics = [
        {
            "label": "headless-provider-smoke",
            "outcome": "provider_outage",
            "command": "python -m minicode.headless \"Reply with exactly OK.\"",
            "exit_code": 1,
            "summary": "Provider availability failure.",
            "stdout": "",
            "stderr": "Provider availability failure.",
        }
    ]
    artifacts = {
        "json": "benchmarks/runtime_profile_eval_results.json",
        "markdown": "benchmarks/runtime_profile_eval_results.md",
    }

    payload = release_readiness_as_dict(
        generated_at="2026-06-05T00:00:00+00:00",
        status="warning",
        compile_check=compile_check,
        test_check=test_check,
        runtime_eval_check=runtime_eval_check,
        smoke_checks=smoke_checks,
        provider_diagnostics=diagnostics,
        runtime_profile_artifacts=artifacts,
        readiness_report={
            "provider": "anthropic",
            "provider_ready": True,
            "provider_channel": "anthropic-compatible via baseUrl/authToken",
            "fallback_ready": True,
            "fallback_candidates": ["gpt-4o"],
            "viable_fallbacks": ["gpt-4o"],
            "fallback_guidance": [
                "Primary runtime is using a single anthropic-compatible channel from baseUrl/authToken.",
                "Add fallbackModels or anthropicFallbackModels to enable model failover.",
            ],
            "summary": "readiness: ready (anthropic) [fallbacks 1/1 locally ready]",
        },
    )
    rendered = release_readiness_as_markdown(
        generated_at="2026-06-05T00:00:00+00:00",
        status="warning",
        compile_check=compile_check,
        test_check=test_check,
        runtime_eval_check=runtime_eval_check,
        smoke_checks=smoke_checks,
        provider_diagnostics=diagnostics,
        runtime_profile_artifacts=artifacts,
        readiness_report={
            "provider": "anthropic",
            "provider_ready": True,
            "provider_channel": "anthropic-compatible via baseUrl/authToken",
            "fallback_ready": True,
            "fallback_candidates": ["gpt-4o"],
            "viable_fallbacks": ["gpt-4o"],
            "fallback_guidance": [
                "Primary runtime is using a single anthropic-compatible channel from baseUrl/authToken.",
                "Add fallbackModels or anthropicFallbackModels to enable model failover.",
            ],
            "summary": "readiness: ready (anthropic) [fallbacks 1/1 locally ready]",
        },
    )

    assert payload["status"] == "warning"
    assert payload["provider_diagnostics"][0]["outcome"] == "provider_outage"
    assert payload["readiness_report"]["fallback_ready"] is True
    assert payload["readiness_report"]["provider_channel"] == "anthropic-compatible via baseUrl/authToken"
    assert payload["runtime_profile_artifacts"]["json"].endswith("runtime_profile_eval_results.json")
    assert "## Core Gate" in rendered
    assert "## Product Smokes" in rendered
    assert "## Provider Diagnostics" in rendered
    assert "## Provider Fallback Coverage" in rendered
    assert "headless-provider-smoke" in rendered
    assert "Channel: anthropic-compatible via baseUrl/authToken" in rendered
    assert "Guidance:" in rendered
    assert "gpt-4o" in rendered
    assert "runtime_profile_eval_results.md" in rendered
