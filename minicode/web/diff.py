"""Read-only, workspace-scoped Git diff collection."""

from __future__ import annotations

import difflib
import hashlib
import subprocess
from pathlib import Path

from minicode.web.schemas import DiffFile, DiffPatchResponse, DiffResponse


MAX_DIFF_BYTES = 1_000_000
MAX_EXPANDED_DIFF_BYTES = 5_000_000


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


def _numstat(cwd: Path) -> dict[str, tuple[int, int, bool]]:
    result = _run_git(cwd, ["diff", "--numstat", "--", "."])
    stats: dict[str, tuple[int, int, bool]] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        is_binary = parts[0] == "-" or parts[1] == "-"
        added = int(parts[0]) if parts[0].isdigit() else 0
        deleted = int(parts[1]) if parts[1].isdigit() else 0
        stats[parts[2]] = (added, deleted, is_binary)
    return stats


def _name_status(cwd: Path) -> dict[str, str]:
    result = _run_git(cwd, ["diff", "--name-status", "--", "."])
    statuses: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code = parts[0]
        path = parts[-1]
        if code.startswith("A"):
            status = "added"
        elif code.startswith("D"):
            status = "deleted"
        elif code.startswith("R"):
            status = "renamed"
        elif code.startswith("C"):
            status = "copied"
        else:
            status = "modified"
        statuses[path] = status
    return statuses


def _untracked_files(cwd: Path) -> list[str]:
    result = _run_git(cwd, ["ls-files", "--others", "--exclude-standard", "--", "."])
    return [line for line in result.stdout.splitlines() if line]


def _workspace_file(cwd: Path, relative_path: str) -> Path:
    if Path(relative_path).is_absolute():
        raise ValueError("Diff paths must be relative to the workspace.")
    candidate = (cwd / relative_path).resolve()
    # Resolution must never allow encoded traversal or symlinks to leave the workspace.
    try:
        candidate.relative_to(cwd)
    except ValueError as exc:
        raise ValueError("Diff path escapes the workspace.") from exc
    return candidate


def _is_binary_file(path: Path, *, sample_size: int = 8192) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\0" in handle.read(sample_size)
    except OSError:
        return True


def _read_untracked_patch(
    cwd: Path,
    relative_path: str,
    *,
    max_bytes: int,
) -> tuple[str, int, bool, bool]:
    candidate = _workspace_file(cwd, relative_path)
    if not candidate.is_file():
        return "", 0, False, False
    if _is_binary_file(candidate):
        return "", 0, True, False

    size = candidate.stat().st_size
    truncated = size > max_bytes
    try:
        data = candidate.read_bytes()[:max_bytes]
        content = data.decode("utf-8", errors="replace")
    except OSError:
        return "", 0, False, False
    lines = content.splitlines(keepends=True)
    patch = "".join(
        difflib.unified_diff([], lines, fromfile="/dev/null", tofile=f"b/{relative_path}")
    )
    return patch, len(lines), False, truncated


def _revision(cwd: Path, stats: dict[str, tuple[int, int, bool]], untracked: list[str]) -> str:
    digest = hashlib.sha1()
    digest.update(_run_git(cwd, ["diff", "--raw", "--", "."]).stdout.encode("utf-8", errors="replace"))
    for path in sorted(untracked):
        digest.update(path.encode("utf-8", errors="replace"))
        try:
            stat = _workspace_file(cwd, path).stat()
        except (OSError, ValueError):
            continue
        digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode("ascii"))
    for path, (added, deleted, is_binary) in sorted(stats.items()):
        digest.update(f"{path}:{added}:{deleted}:{is_binary}".encode("utf-8", errors="replace"))
    return digest.hexdigest()[:16]


def read_workspace_diff(workspace: str | Path) -> DiffResponse:
    cwd = Path(workspace).resolve()
    if not (cwd / ".git").exists():
        return DiffResponse(files=[], additions=0, deletions=0)

    stats = _numstat(cwd)
    statuses = _name_status(cwd)
    untracked = _untracked_files(cwd)

    for relative_path in untracked:
        try:
            candidate = _workspace_file(cwd, relative_path)
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        if _is_binary_file(candidate):
            stats[relative_path] = (0, 0, True)
        else:
            try:
                line_count = sum(1 for _line in candidate.open(encoding="utf-8", errors="replace"))
            except OSError:
                line_count = 0
            stats[relative_path] = (line_count, 0, False)
        statuses[relative_path] = "untracked"

    revision = _revision(cwd, stats, untracked)

    files = [
        DiffFile(
            path=path,
            additions=stats.get(path, (0, 0, False))[0],
            deletions=stats.get(path, (0, 0, False))[1],
            status=statuses.get(path, "modified"),
            isBinary=stats.get(path, (0, 0, False))[2],
        )
        for path in sorted(stats)
    ]
    return DiffResponse(
        files=files,
        additions=sum(item.additions for item in files),
        deletions=sum(item.deletions for item in files),
        truncated=False,
        revision=revision,
    )


def read_workspace_diff_file(
    workspace: str | Path,
    relative_path: str,
    *,
    max_bytes: int = MAX_DIFF_BYTES,
) -> DiffPatchResponse:
    cwd = Path(workspace).resolve()
    if not (cwd / ".git").exists():
        return DiffPatchResponse(path=relative_path, patch="", additions=0, deletions=0)

    max_bytes = min(max(1, max_bytes), MAX_EXPANDED_DIFF_BYTES)
    _workspace_file(cwd, relative_path)
    summary = read_workspace_diff(cwd)
    by_path = {item.path: item for item in summary.files}
    file_summary = by_path.get(relative_path)
    if file_summary is None:
        raise FileNotFoundError(relative_path)

    if file_summary.isBinary:
        return DiffPatchResponse(
            path=relative_path,
            patch="",
            additions=file_summary.additions,
            deletions=file_summary.deletions,
            status=file_summary.status,
            isBinary=True,
            revision=summary.revision,
        )

    if file_summary.status == "untracked":
        patch, additions, is_binary, truncated = _read_untracked_patch(
            cwd,
            relative_path,
            max_bytes=max_bytes,
        )
        return DiffPatchResponse(
            path=relative_path,
            patch=patch,
            additions=additions,
            deletions=0,
            status=file_summary.status,
            isBinary=is_binary,
            truncated=truncated,
            revision=summary.revision,
        )

    result = _run_git(
        cwd,
        ["diff", "--no-ext-diff", "--unified=3", "--", relative_path],
    )
    raw_bytes = result.stdout.encode("utf-8", errors="replace")
    truncated = len(raw_bytes) > max_bytes
    if truncated:
        raw_bytes = raw_bytes[:max_bytes]
    return DiffPatchResponse(
        path=relative_path,
        patch=raw_bytes.decode("utf-8", errors="ignore"),
        additions=file_summary.additions,
        deletions=file_summary.deletions,
        status=file_summary.status,
        isBinary=False,
        truncated=truncated,
        revision=summary.revision,
    )
