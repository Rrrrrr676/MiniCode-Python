from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    label: str
    command: str
    exit_code: int
    status: str
    summary: str
    stdout: str = ""
    stderr: str = ""


def classify_provider_outcome(*, exit_code: int, stdout: str, stderr: str) -> tuple[str, str]:
    stripped_stdout = (stdout or "").strip()
    stripped_stderr = (stderr or "").strip()
    combined = " ".join(f"{stripped_stdout}\n{stripped_stderr}".lower().split())
    summary_source = stripped_stdout or stripped_stderr
    summary = summary_source.splitlines()[0].strip() if summary_source else ""

    if exit_code == 0 and stripped_stdout == "OK":
        return "answered", summary or "Headless provider smoke returned OK."
    if (
        "provider availability failure" in combined
        or "all viable fallback models were unavailable" in combined
        or "no available channel" in combined
    ):
        return "provider_outage", summary or "Provider availability failure."
    if "empty response" in combined:
        return "empty_output", summary or "Provider smoke returned an empty response."
    if exit_code == 124:
        return "timeout", summary or "Provider smoke timed out."
    return "error", summary or f"Provider smoke failed with exit code {exit_code}."


def summarize_release_status(
    *,
    compile_check: ReleaseCheck,
    test_check: ReleaseCheck,
    runtime_eval_check: ReleaseCheck,
    smoke_checks: list[ReleaseCheck],
    provider_outcomes: list[str],
    readiness_report: dict[str, Any] | None = None,
) -> str:
    if any(check.status == "failed" for check in [compile_check, test_check, runtime_eval_check, *smoke_checks]):
        return "blocked"
    if any(outcome not in {"answered", "provider_outage", "empty_output"} for outcome in provider_outcomes):
        return "at-risk"
    if any(outcome == "provider_outage" for outcome in provider_outcomes):
        report = dict(readiness_report or {})
        if not report.get("fallback_ready"):
            return "at-risk"
        return "warning"
    return "pass"


def release_readiness_as_dict(
    *,
    generated_at: str,
    status: str,
    compile_check: ReleaseCheck,
    test_check: ReleaseCheck,
    runtime_eval_check: ReleaseCheck,
    smoke_checks: list[ReleaseCheck],
    provider_diagnostics: list[dict[str, Any]],
    runtime_profile_artifacts: dict[str, str],
    readiness_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "status": status,
        "compile_check": asdict(compile_check),
        "test_check": asdict(test_check),
        "runtime_eval_check": asdict(runtime_eval_check),
        "smoke_checks": [asdict(item) for item in smoke_checks],
        "provider_diagnostics": provider_diagnostics,
        "runtime_profile_artifacts": runtime_profile_artifacts,
        "readiness_report": dict(readiness_report or {}),
    }


def release_readiness_as_markdown(
    *,
    generated_at: str,
    status: str,
    compile_check: ReleaseCheck,
    test_check: ReleaseCheck,
    runtime_eval_check: ReleaseCheck,
    smoke_checks: list[ReleaseCheck],
    provider_diagnostics: list[dict[str, Any]],
    runtime_profile_artifacts: dict[str, str],
    readiness_report: dict[str, Any] | None = None,
) -> str:
    report = dict(readiness_report or {})
    lines = [
        "# MiniCode Release Readiness",
        "",
        f"- Generated at: {generated_at}",
        f"- Status: {status}",
        "",
        "## Core Gate",
        "",
        "| check | status | exit_code | summary |",
        "| --- | --- | ---: | --- |",
    ]
    for item in [compile_check, test_check, runtime_eval_check]:
        lines.append(
            f"| {item.label} | {item.status} | {item.exit_code} | {item.summary} |"
        )

    lines.extend(
        [
            "",
            "## Product Smokes",
            "",
            "| check | status | exit_code | summary |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for item in smoke_checks:
        lines.append(
            f"| {item.label} | {item.status} | {item.exit_code} | {item.summary} |"
        )

    lines.extend(
        [
            "",
            "## Provider Diagnostics",
            "",
            "| label | outcome | exit_code | summary |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for item in provider_diagnostics:
        lines.append(
            f"| {item.get('label', '-')} | {item.get('outcome', '-')} | "
            f"{item.get('exit_code', 0)} | {item.get('summary', '')} |"
        )

    if report:
        fallback_candidates = [
            str(candidate)
            for candidate in list(report.get("fallback_candidates", []) or [])
        ]
        viable_fallbacks = {
            str(candidate)
            for candidate in list(report.get("viable_fallbacks", []) or [])
        }
        lines.extend(
            [
                "",
                "## Provider Fallback Coverage",
                "",
                f"- Provider: {report.get('provider', 'unknown')}",
                f"- Provider ready: {'yes' if report.get('provider_ready') else 'no'}",
                f"- Channel: {report.get('provider_channel', 'unknown')}",
                f"- Fallback ready: {'yes' if report.get('fallback_ready') else 'no'}",
                f"- Summary: {report.get('summary', '')}",
            ]
        )
        guidance = [
            str(item)
            for item in list(report.get("fallback_guidance", []) or [])
            if str(item).strip()
        ]
        if guidance:
            lines.append("- Guidance:")
            for item in guidance:
                lines.append(f"  - {item}")
        if fallback_candidates:
            lines.append("")
            lines.append("| fallback | locally ready |")
            lines.append("| --- | --- |")
            for candidate in fallback_candidates:
                lines.append(
                    f"| {candidate} | {'yes' if candidate in viable_fallbacks else 'no'} |"
                )

    lines.extend(
        [
            "",
            "## Runtime Profile Artifacts",
            "",
            f"- JSON: {runtime_profile_artifacts.get('json', '-')}",
            f"- Markdown: {runtime_profile_artifacts.get('markdown', '-')}",
        ]
    )
    return "\n".join(lines)
