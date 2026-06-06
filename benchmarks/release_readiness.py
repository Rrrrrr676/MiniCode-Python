from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minicode.release_readiness import (
    ReleaseCheck,
    classify_provider_outcome,
    release_readiness_as_dict,
    release_readiness_as_markdown,
    summarize_release_status,
)
from minicode.product_surfaces import build_readiness_report
from minicode.session import create_file_checkpoint, create_new_session, save_session


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS_DIR = REPO_ROOT / "benchmarks"


def _run_command(label: str, command: list[str], *, cwd: Path, timeout: int = 1800) -> ReleaseCheck:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        summary_source = stdout or stderr
        summary = summary_source.splitlines()[-1].strip() if summary_source else f"{label} completed."
        status = "passed" if completed.returncode == 0 else "failed"
        return ReleaseCheck(
            label=label,
            command=" ".join(command),
            exit_code=completed.returncode,
            status=status,
            summary=summary,
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return ReleaseCheck(
            label=label,
            command=" ".join(command),
            exit_code=124,
            status="failed",
            summary=f"{label} timed out.",
            stdout=stdout if isinstance(stdout, str) else "",
            stderr=stderr if isinstance(stderr, str) else "",
        )


def _prepare_saved_session(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "demo.txt"
    target.write_text("after", encoding="utf-8")
    extension_dir = workspace / ".mini-code" / "extensions" / "git-helpers"
    extension_dir.mkdir(parents=True, exist_ok=True)
    (extension_dir / "extension.json").write_text(
        json.dumps(
            {
                "name": "git-helpers",
                "version": "1.0.0",
                "description": "Local helper bundle",
                "enabled": True,
                "entrypoint": "bundle.py",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (extension_dir / "bundle.py").write_text("print('ok')\n", encoding="utf-8")

    session = create_new_session(workspace=str(workspace))
    session.history = ["continue with runtime trace"]
    session.transcript_entries = [
        {
            "id": 1,
            "kind": "progress",
            "category": "runtime",
            "runtimeKind": "phase",
            "runtimeStep": 2,
            "runtimePhase": "verify",
            "body": "Runtime phase: verify.",
        },
        {
            "id": 2,
            "kind": "tool",
            "toolName": "edit_file",
            "status": "success",
            "body": "Patched demo.txt",
        },
    ]
    session.instruction_layers = [
        {
            "name": "project-managed",
            "scope": "project",
            "kind": "managed",
            "path": str(workspace / ".mini-code" / "MANAGED.md"),
            "exists": True,
            "preview": "Prefer verification-first delivery.",
        }
    ]
    session.hook_status = {
        "total_hooks": 1,
        "enabled_hooks": 1,
        "total_calls": 1,
        "total_duration_ms": 8,
        "failure_count": 0,
        "last_status": "success",
    }
    session.delegated_tasks = [{"label": "lint-worker", "status": "running"}]
    session.delegation_status = {
        "running_tasks": 1,
        "total_tracked": 1,
        "max_slots": 4,
        "available_slots": 3,
        "active_labels": ["lint-worker"],
    }
    session.extension_manifests = [
        {
            "name": "git-helpers",
            "scope": "project",
            "enabled": True,
            "version": "1.0.0",
            "description": "Local helper bundle",
            "entrypoint": "bundle.py",
        }
    ]
    session.readiness_report = {
        "status": "ready",
        "provider": "anthropic-compatible",
        "provider_ready": True,
        "issues": [],
    }
    create_file_checkpoint(
        session,
        file_path=str(target),
        existed=True,
        previous_content="before",
    )
    save_session(session)


def main() -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    workspace = REPO_ROOT / "outputs" / "release_smoke_workspace"
    _prepare_saved_session(workspace)

    compile_check = _run_command(
        "compileall",
        [sys.executable, "-m", "compileall", "-q", "minicode", "tests", "benchmarks"],
        cwd=REPO_ROOT,
        timeout=600,
    )
    test_check = _run_command(
        "pytest-q",
        [sys.executable, "-m", "pytest", "-q"],
        cwd=REPO_ROOT,
        timeout=2400,
    )
    runtime_eval_check = _run_command(
        "runtime-profile-eval",
        [sys.executable, "benchmarks/runtime_profile_eval.py"],
        cwd=REPO_ROOT,
        timeout=600,
    )

    smoke_checks = [
        _run_command(
            "list-sessions",
            [sys.executable, "-m", "minicode.main", "--list-sessions"],
            cwd=workspace,
            timeout=120,
        ),
        _run_command(
            "inspect-session",
            [sys.executable, "-m", "minicode.main", "--inspect-session", "latest"],
            cwd=workspace,
            timeout=120,
        ),
        _run_command(
            "replay-session",
            [sys.executable, "-m", "minicode.main", "--replay-session", "latest"],
            cwd=workspace,
            timeout=120,
        ),
        _run_command(
            "preview-rewind",
            [sys.executable, "-m", "minicode.main", "--preview-rewind", "latest"],
            cwd=workspace,
            timeout=120,
        ),
    ]

    runtime_profile_json = BENCHMARKS_DIR / "runtime_profile_eval_results.json"
    provider_diagnostics: list[dict[str, object]] = []
    if runtime_profile_json.exists():
        payload = json.loads(runtime_profile_json.read_text(encoding="utf-8"))
        provider_diagnostics = list(payload.get("provider_diagnostics", []) or [])

    if not provider_diagnostics:
        fallback_check = _run_command(
            "headless-provider-smoke",
            [sys.executable, "-m", "minicode.headless", "Reply with exactly OK."],
            cwd=REPO_ROOT,
            timeout=180,
        )
        outcome, summary = classify_provider_outcome(
            exit_code=fallback_check.exit_code,
            stdout=fallback_check.stdout,
            stderr=fallback_check.stderr,
        )
        provider_diagnostics = [
            {
                "label": fallback_check.label,
                "outcome": outcome,
                "command": fallback_check.command,
                "exit_code": fallback_check.exit_code,
                "summary": summary,
                "stdout": fallback_check.stdout,
                "stderr": fallback_check.stderr,
            }
        ]

    readiness_report = build_readiness_report(REPO_ROOT)

    readiness_snapshot = {
        "provider": readiness_report.provider,
        "provider_ready": readiness_report.provider_ready,
        "provider_channel": readiness_report.provider_channel,
        "fallback_ready": readiness_report.fallback_ready,
        "fallback_candidates": readiness_report.fallback_candidates,
        "viable_fallbacks": readiness_report.viable_fallbacks,
        "fallback_guidance": readiness_report.fallback_guidance,
        "issues": readiness_report.issues,
        "summary": readiness_report.summary,
    }

    status = summarize_release_status(
        compile_check=compile_check,
        test_check=test_check,
        runtime_eval_check=runtime_eval_check,
        smoke_checks=smoke_checks,
        provider_outcomes=[str(item.get("outcome", "error")) for item in provider_diagnostics],
        readiness_report=readiness_snapshot,
    )

    runtime_profile_artifacts = {
        "json": str(runtime_profile_json),
        "markdown": str(BENCHMARKS_DIR / "runtime_profile_eval_results.md"),
    }
    payload = release_readiness_as_dict(
        generated_at=generated_at,
        status=status,
        compile_check=compile_check,
        test_check=test_check,
        runtime_eval_check=runtime_eval_check,
        smoke_checks=smoke_checks,
        provider_diagnostics=provider_diagnostics,
        runtime_profile_artifacts=runtime_profile_artifacts,
        readiness_report=readiness_snapshot,
    )
    markdown = release_readiness_as_markdown(
        generated_at=generated_at,
        status=status,
        compile_check=compile_check,
        test_check=test_check,
        runtime_eval_check=runtime_eval_check,
        smoke_checks=smoke_checks,
        provider_diagnostics=provider_diagnostics,
        runtime_profile_artifacts=runtime_profile_artifacts,
        readiness_report=readiness_snapshot,
    )

    json_path = BENCHMARKS_DIR / "release_readiness_results.json"
    markdown_path = BENCHMARKS_DIR / "release_readiness_results.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    print(json_path)
    print(markdown_path)


if __name__ == "__main__":
    main()
