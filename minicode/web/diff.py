"""Read-only, workspace-scoped Git diff collection."""

from __future__ import annotations

import difflib
import subprocess
from pathlib import Path

from minicode.web.schemas import DiffFile, DiffResponse


MAX_DIFF_BYTES = 1_000_000


def _run_git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )


def _numstat(cwd: Path) -> dict[str, tuple[int, int]]:
    result = _run_git(cwd, ["diff", "--numstat", "--", "."])
    stats: dict[str, tuple[int, int]] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added = int(parts[0]) if parts[0].isdigit() else 0
        deleted = int(parts[1]) if parts[1].isdigit() else 0
        stats[parts[2]] = (added, deleted)
    return stats


def _patches(raw_diff: str) -> dict[str, str]:
    patches: dict[str, str] = {}
    current_path = ""
    current_lines: list[str] = []
    for line in raw_diff.splitlines(keepends=True):
        if line.startswith("diff --git a/"):
            if current_path:
                patches[current_path] = "".join(current_lines)
            marker = line.removeprefix("diff --git a/")
            current_path = marker.split(" b/", 1)[0]
            current_lines = [line]
        elif current_path:
            current_lines.append(line)
    if current_path:
        patches[current_path] = "".join(current_lines)
    return patches


def read_workspace_diff(workspace: str | Path) -> DiffResponse:
    cwd = Path(workspace).resolve()
    if not (cwd / ".git").exists():
        return DiffResponse(files=[], additions=0, deletions=0)

    diff_result = _run_git(cwd, ["diff", "--no-ext-diff", "--unified=3", "--", "."])
    raw = diff_result.stdout
    was_truncated = len(raw.encode("utf-8")) > MAX_DIFF_BYTES
    if was_truncated:
        raw = raw.encode("utf-8")[:MAX_DIFF_BYTES].decode("utf-8", errors="ignore")
    patches = _patches(raw)
    stats = _numstat(cwd)

    untracked = _run_git(cwd, ["ls-files", "--others", "--exclude-standard", "--", "."])
    for relative_path in untracked.stdout.splitlines():
        candidate = (cwd / relative_path).resolve()
        try:
            candidate.relative_to(cwd)
        except ValueError:
            continue
        if not candidate.is_file() or candidate.stat().st_size > MAX_DIFF_BYTES:
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = content.splitlines(keepends=True)
        patches[relative_path] = "".join(
            difflib.unified_diff([], lines, fromfile="/dev/null", tofile=f"b/{relative_path}")
        )
        stats[relative_path] = (len(lines), 0)

    files = [
        DiffFile(
            path=path,
            additions=stats.get(path, (0, 0))[0],
            deletions=stats.get(path, (0, 0))[1],
            patch=patch,
        )
        for path, patch in sorted(patches.items())
    ]
    return DiffResponse(
        files=files,
        additions=sum(item.additions for item in files),
        deletions=sum(item.deletions for item in files),
        truncated=was_truncated,
    )
