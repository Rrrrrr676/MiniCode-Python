from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
import re

from .chrome import (
    _cached_terminal_size,
    RESET,
    DIM,
    BOLD,
    ICON_DIVIDER,
    ICON_DOT,
)
from .markdown import render_markdownish
from .theme import theme
from .types import TranscriptEntry

# Pre-build the separator string once (immutable)
_SEPARATOR = f"  {DIM}{ICON_DOT} {ICON_DIVIDER * 3} {ICON_DOT}{RESET}"
_SEPARATOR_LINES = ["", _SEPARATOR, ""]
_SEPARATOR_LINE_COUNT = 3

# Tool output preview limits (match Rust TOOL_PREVIEW_LINES / TOOL_PREVIEW_CHARS)
_TOOL_PREVIEW_LINES = 6
_TOOL_PREVIEW_CHARS = 180
_COMPACT_TRANSCRIPT_WIDTH = 72
_COMPACT_ASSISTANT_CHARS = 62
_COMPACT_PROGRESS_CHARS = 58
_COMPACT_TOOL_CHARS = 54
_COMPACT_PATH_TOKEN_CHARS = 32
_COMPACT_TABLE_COLUMNS = 3


def _indent_block(text: str, prefix: str = "  ") -> str:
    """Indent all lines in a block of text."""
    return "\n".join(prefix + line for line in text.split("\n"))


def _transcript_render_columns() -> int:
    cols, _ = _cached_terminal_size()
    return max(40, cols)


def _should_compact_transcript_preview() -> bool:
    return _transcript_render_columns() <= _COMPACT_TRANSCRIPT_WIDTH


def _center_ellipsize(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 5:
        return text[:max_chars]

    visible = max_chars - 3
    left = visible // 2
    right = visible - left
    return f"{text[:left]}...{text[-right:]}"


def _tail_weighted_ellipsize(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 5:
        return text[:max_chars]

    visible = max_chars - 3
    tail = max(visible // 2, int(visible * 0.65))
    tail = min(visible - 1, tail)
    head = visible - tail
    return f"{text[:head].rstrip()}...{text[-tail:]}"


def _ellipsize_structured_followup(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if ": " not in text:
        return _tail_weighted_ellipsize(text, max_chars)

    label, detail = text.split(": ", 1)
    prefix = f"{label}: "
    if len(prefix) >= max_chars:
        return _tail_weighted_ellipsize(prefix.rstrip(), max_chars)

    detail_budget = max(6, max_chars - len(prefix))
    if label == "table" and "|" in detail:
        cells = [cell.strip() for cell in detail.split("|")]
        cells = [cell for cell in cells if cell]
        if cells:
            first = cells[0]
            last = cells[-1]
            candidates = []
            if len(cells) >= 2:
                candidates.extend(
                    [
                        f"{first} | ... | {last}",
                        f"{first} |...| {last}",
                        f"{first}|...|{last}",
                        f"{first} |...|{last}",
                        f"{first}|...| {last}",
                        f"{first}...{last}",
                        f"{first} | {last}",
                        f"... | {last}",
                    ]
                )
            candidates.append(first)
            for candidate in candidates:
                if len(candidate) <= detail_budget:
                    return f"{prefix}{candidate}"
    if label == "quote":
        compact_quote = _compact_quote_detail(detail, detail_budget)
        if compact_quote:
            return f"{prefix}{compact_quote}"
    if label == "list":
        compact_list = _compact_list_detail(detail, detail_budget)
        if compact_list:
            return f"{prefix}{compact_list}"
    if label.endswith("code"):
        compact_code = _compact_code_detail(detail, detail_budget)
        if compact_code:
            return f"{prefix}{compact_code}"
    return f"{prefix}{_tail_weighted_ellipsize(detail, detail_budget)}"


def _compact_plain_followup_text(
    text: str, max_chars: int, *, prefer_tail: bool = False
) -> str:
    if len(text) <= max_chars:
        return text

    normalized = " ".join(text.split())
    tokens = [token for token in normalized.split() if token]
    if tokens:
        boundary_words = {
            "should",
            "stays",
            "stay",
            "remains",
            "remain",
            "is",
            "are",
            "was",
            "were",
            "can",
            "could",
            "may",
            "might",
            "will",
            "would",
            "as",
            "before",
            "after",
            "while",
            "during",
            "when",
            "to",
        }
        leading_words = {"use", "keep", "preserve", "retain"}
        articles = {"the", "a", "an"}
        start_index = 0
        if tokens[0].lower() in leading_words and len(tokens) > 1:
            start_index = 1
        if start_index < len(tokens) and tokens[start_index].lower() in articles:
            start_index += 1

        subject_tokens: list[str] = []
        single_token_candidate: str | None = None
        for token in tokens[start_index:]:
            stripped = token.strip(",;:()[]{}")
            if not stripped:
                continue
            if stripped.lower() in boundary_words:
                break
            subject_tokens.append(stripped)
            if len(subject_tokens) >= 5:
                break

        if subject_tokens:
            if len(subject_tokens) == 1:
                single_token_candidate = subject_tokens[0]
            else:
                tail_candidates: list[str] = []
                if len(subject_tokens) == 2:
                    if prefer_tail:
                        tail_candidates.append(subject_tokens[-1])
                        tail_candidates.append(" ".join(subject_tokens))
                        tail_candidates.append(subject_tokens[0])
                    else:
                        tail_candidates.append(" ".join(subject_tokens))
                        tail_candidates.append(subject_tokens[0])
                        tail_candidates.append(subject_tokens[-1])
                elif len(subject_tokens) >= 2:
                    tail_candidates.append(" ".join(subject_tokens[-2:]))
                if len(subject_tokens) >= 3:
                    tail_candidates.append(subject_tokens[len(subject_tokens) // 2])
                tail_candidates.append(subject_tokens[-1])
                if len(subject_tokens) >= 3:
                    tail_candidates.append(" ".join(subject_tokens[-3:]))
                for tail_candidate in tail_candidates:
                    if len(tail_candidate) <= max_chars:
                        return tail_candidate

    words = normalized.split()
    if len(words) <= 3:
        short_candidates: list[str] = []
        if len(words) == 1:
            short_candidates.append(words[0])
        elif len(words) == 2:
            short_candidates.extend([normalized, words[0], words[1]])
        else:
            short_candidates.extend(
                [
                    " ".join(words[-2:]),
                    words[1],
                    words[-1],
                    " ".join(words[:2]),
                ]
            )
        for candidate in short_candidates:
            if len(candidate) <= max_chars:
                return candidate

    candidate_patterns = (
        r"\bon ([^.,;]+)",
        r"\bfor ([^.,;]+)",
        r"\bwith ([^.,;]+)",
        r"\babout ([^.,;]+)",
        r"\bto ([^.,;]+)",
        r"\bafter ([^.,;]+)",
    )
    for pattern in candidate_patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(1).strip()
        for splitter in (" before ", " after ", " while ", " during ", " when "):
            if splitter in candidate:
                candidate = candidate.split(splitter, 1)[0].strip()
                break
        candidate = re.sub(r"^(?:the|a|an)\s+", "", candidate, flags=re.IGNORECASE)
        if candidate and len(candidate) <= max_chars:
            return candidate

    if single_token_candidate and len(single_token_candidate) <= max_chars:
        return single_token_candidate

    return _center_ellipsize(normalized, max_chars)


def _compact_quote_detail(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized

    if "..." in normalized:
        head, tail = normalized.split("...", 1)
        head = head.strip()
        tail = tail.strip()
        if head and tail:
            candidates = []
            tail_words = tail.split()
            if len(tail_words) >= 2:
                candidates.append(f"...{' '.join(tail_words[-2:])}")
            if tail_words:
                candidates.append(f"...{tail_words[-1]}")
            candidates.extend(
                [
                    f"{head}...{tail}",
                    f"{head} ... {tail}",
                    f"...{tail}",
                    f"{head}...",
                ]
            )
            for candidate in candidates:
                if len(candidate) <= max_chars:
                    return candidate

    words = normalized.split()
    if len(words) < 2:
        return _tail_weighted_ellipsize(normalized, max_chars)

    head = words[0]
    for tail_count in (2, 1):
        tail = " ".join(words[-tail_count:])
        candidate = f"{head}...{tail}"
        if len(candidate) <= max_chars:
            return candidate
        candidate = f"{head} ... {tail}"
        if len(candidate) <= max_chars:
            return candidate
        candidate = f"...{tail}"
        if len(candidate) <= max_chars:
            return candidate

    return _tail_weighted_ellipsize(normalized, max_chars)


def _compact_code_detail(text: str, max_chars: int) -> str:
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped

    core, markers = _split_trailing_followup_markers(stripped)
    if markers:
        core_budget = max(6, max_chars - len(markers))
        compact_core = _compact_code_detail_core(core, core_budget)
        candidate = f"{compact_core}{markers}"
        if len(candidate) <= max_chars:
            return candidate
        stripped = core

    return _compact_code_detail_core(stripped, max_chars)


def _compact_code_detail_core(stripped: str, max_chars: int) -> str:
    identifier = stripped.split("(", 1)[0].strip()
    if not identifier:
        return _tail_weighted_ellipsize(stripped, max_chars)
    if len(identifier) <= max_chars:
        return identifier

    if "_" in identifier:
        parts = [part for part in identifier.split("_") if part]
        if parts:
            tail = parts[-1]
            for head_parts in range(min(2, len(parts) - 1), 0, -1):
                head = "_".join(parts[:head_parts])
                candidate = f"{head}...{tail}"
                if len(candidate) <= max_chars:
                    return candidate
            if len(tail) + 3 <= max_chars:
                return f"...{tail}"
            if max_chars > 3:
                return f"...{tail[-(max_chars - 3):]}"

    return _tail_weighted_ellipsize(identifier, max_chars)


def _compact_list_detail(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized

    if "..." in normalized:
        head, tail = normalized.split("...", 1)
        head = head.strip()
        tail = tail.strip()
        if head and tail:
            candidates = [
                f"{head} {tail}",
                f"{head}...{tail}",
                f"...{tail}",
            ]
            for candidate in candidates:
                if len(candidate) <= max_chars:
                    return candidate

    words = normalized.split()
    if len(words) < 2:
        return _tail_weighted_ellipsize(normalized, max_chars)

    head = words[0]
    tail = words[-1]
    candidates = [f"{head} {tail}", f"{head}...{tail}", f"{head}..."]
    if len(words) >= 3:
        candidates.extend(
            [
                f"{head} {words[1]}...{tail}",
                f"{head} {words[1]}...",
                f"{head} {words[1]}",
            ]
        )
    candidates.append(head)

    for candidate in candidates:
        if len(candidate) <= max_chars:
            return candidate

    if len(head) + 3 <= max_chars:
        return f"{head}..."
    if len(tail) + 3 <= max_chars:
        return f"...{tail}"

    return _tail_weighted_ellipsize(normalized, max_chars)


def _split_trailing_followup_markers(text: str) -> tuple[str, str]:
    match = re.search(r"^(.*?)(\s(?:\[[A-Za-z_]+\]\s*)+)$", text)
    if not match:
        return text, ""
    markers = re.findall(r"\[[A-Za-z_]+\]", match.group(2))
    normalized_markers = ""
    if markers:
        normalized_markers = " " + " ".join(markers)
    return match.group(1).rstrip(), normalized_markers


def _fit_trailing_followup_markers(
    prefix: str,
    detail_core: str,
    existing_markers: str,
    new_marker: str,
    max_chars: int,
) -> str | None:
    marker_tokens = re.findall(r"\[[A-Za-z_]+\]", existing_markers)
    marker_tokens.append(f"[{new_marker}]")

    for keep_count in range(len(marker_tokens), 0, -1):
        suffix = " " + " ".join(marker_tokens[-keep_count:])
        prefix_budget = max(12, max_chars - len(detail_core) - len(suffix) - 3)
        compact_prefix = prefix
        if len(compact_prefix) > prefix_budget:
            compact_prefix = _ellipsize_structured_followup(compact_prefix, prefix_budget)
        candidate = f"{compact_prefix} - {detail_core}{suffix}"
        if len(candidate) <= max_chars:
            return candidate

    prefix_budget = max(12, max_chars - len(detail_core) - 3)
    compact_prefix = prefix
    if len(compact_prefix) > prefix_budget:
        compact_prefix = _ellipsize_structured_followup(compact_prefix, prefix_budget)
    candidate = f"{compact_prefix} - {detail_core}"
    if len(candidate) <= max_chars:
        return candidate
    return None


def _score_table_followup_candidate(text: str) -> tuple[int, int, int]:
    prefix, detail = text.rsplit(" - ", 1)
    marker_count = len(re.findall(r"\[[A-Za-z_]+\]", detail))
    table_detail = prefix.split(": ", 1)[1] if ": " in prefix else prefix
    preserves_column_shape = int(
        ("|" in table_detail and table_detail.count("|") >= 2)
        or any(token in table_detail for token in (" | ... | ", " |...| ", "|...|", " |...|"))
    )
    return (preserves_column_shape, marker_count, len(prefix))


def _fit_table_followup_markers(
    prefix: str,
    detail_core: str,
    existing_markers: str,
    new_marker: str,
    max_chars: int,
) -> str | None:
    marker_tokens = re.findall(r"\[[A-Za-z_]+\]", existing_markers)
    marker_tokens.append(f"[{new_marker}]")
    best_candidate: str | None = None
    best_score: tuple[int, int, int] | None = None

    for keep_count in range(len(marker_tokens), 0, -1):
        suffix = " " + " ".join(marker_tokens[-keep_count:])
        prefix_budget = max(12, max_chars - len(detail_core) - len(suffix) - 3)
        compact_prefix = prefix
        if len(compact_prefix) > prefix_budget:
            compact_prefix = _ellipsize_structured_followup(compact_prefix, prefix_budget)
        candidate = f"{compact_prefix} - {detail_core}{suffix}"
        if len(candidate) <= max_chars:
            score = _score_table_followup_candidate(candidate)
            if best_score is None or score > best_score:
                best_candidate = candidate
                best_score = score

    prefix_budget = max(12, max_chars - len(detail_core) - 3)
    compact_prefix = prefix
    if len(compact_prefix) > prefix_budget:
        compact_prefix = _ellipsize_structured_followup(compact_prefix, prefix_budget)
    candidate = f"{compact_prefix} - {detail_core}"
    if len(candidate) <= max_chars:
        score = _score_table_followup_candidate(candidate)
        if best_score is None or score > best_score:
            best_candidate = candidate
    return best_candidate


def _compact_followup_detail_preserving_markers(text: str, max_chars: int) -> str:
    core, markers = _split_trailing_followup_markers(text)
    if not markers:
        return _compact_plain_followup_text(text, max_chars)
    if len(text) <= max_chars:
        return text

    marker_budget = len(markers)
    core_budget = max(6, max_chars - marker_budget)
    if len(core) > core_budget:
        core = _compact_plain_followup_text(core, core_budget)
    return f"{core}{markers}"


def _compact_plain_prefix_fragment(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized

    words = [word for word in normalized.split() if word]
    if len(words) >= 2:
        tail_phrase = " ".join(words[-2:])
        if len(tail_phrase) <= max_chars:
            return tail_phrase
    if words:
        if len(words[-1]) <= max_chars:
            return words[-1]
        if len(words[0]) <= max_chars:
            return words[0]
    return _compact_plain_followup_text(normalized, max_chars)


def _compact_code_preview_line(code_line: str) -> str:
    stripped = _strip_assistant_markdown_prefix(code_line)
    if not stripped:
        return ""

    if match := re.match(r"(?:async\s+)?def\s+([A-Za-z_]\w*)", stripped):
        return match.group(1)
    if match := re.match(r"class\s+([A-Za-z_]\w*)", stripped):
        return match.group(1)
    if match := re.match(r"([A-Za-z_]\w*)\s*=\s*", stripped):
        return f"{match.group(1)} = ..."
    return stripped


def _is_pathlike_token(token: str) -> bool:
    stripped = token.strip(",;:()[]{}")
    return (
        "\\" in stripped
        or "/" in stripped
        or stripped.startswith(("path=", "file=", "cwd="))
        or stripped.endswith(
            (
                ".py",
                ".ts",
                ".tsx",
                ".js",
                ".jsx",
                ".md",
                ".json",
                ".yaml",
                ".yml",
                ".toml",
                ".txt",
            )
        )
    )


def _compact_pathlike_tokens(text: str, max_chars: int) -> str:
    tokens = text.split()
    if not tokens:
        return text

    token_budget = min(_COMPACT_PATH_TOKEN_CHARS, max(14, max_chars // 2))
    compacted: list[str] = []
    for token in tokens:
        if _is_pathlike_token(token) and len(token) > token_budget:
            compacted.append(_compact_pathlike_token(token, token_budget))
        else:
            compacted.append(token)
    return " ".join(compacted)


def _compact_pathlike_token(token: str, max_chars: int) -> str:
    if len(token) <= max_chars:
        return token

    leading_len = len(token) - len(token.lstrip(",;:()[]{}"))
    trailing_len = len(token) - len(token.rstrip(",;:()[]{}"))
    leading = token[:leading_len]
    trailing = token[len(token) - trailing_len :] if trailing_len else ""
    core = token[leading_len : len(token) - trailing_len if trailing_len else len(token)]

    prefix = ""
    path_value = core
    if "=" in core:
        candidate_prefix, candidate_value = core.split("=", 1)
        if candidate_prefix in {"path", "file", "cwd"}:
            prefix = f"{candidate_prefix}="
            path_value = candidate_value

    if "\\" in path_value or "/" in path_value:
        separator = "\\" if "\\" in path_value else "/"
        segments = [segment for segment in re.split(r"[\\/]+", path_value) if segment]
        basename = segments[-1] if segments else path_value
        drive = ""
        if segments and segments[0].endswith(":"):
            drive = f"{segments[0]}{separator}"
        compact = f"{prefix}{drive}...{separator}{basename}"
        if len(compact) > max_chars:
            basename_budget = max(8, max_chars - len(prefix) - len(drive) - 4)
            compact = f"{prefix}{drive}...{separator}{_tail_weighted_ellipsize(basename, basename_budget)}"
        return f"{leading}{compact}{trailing}"

    return f"{leading}{_center_ellipsize(core, max_chars - leading_len - trailing_len)}{trailing}"


def _compact_transcript_preview(body: str, max_chars: int) -> str:
    """Return a first-screen preview that stays readable on narrow terminals."""
    if not body:
        return body

    lines = body.splitlines()
    summary = ""
    summary_index = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped:
            summary = stripped
            summary_index = i
            break
    if not summary and lines:
        summary = lines[0].strip()

    more_content = any(line.strip() for line in lines[summary_index + 1 :])
    if not summary:
        return "..."

    summary = _compact_pathlike_tokens(summary, max_chars)
    has_pathlike = any(_is_pathlike_token(token) for token in summary.split())
    suffix = " ..."
    truncated = False
    if len(summary) > max_chars:
        summary = (
            _tail_weighted_ellipsize(summary, max_chars)
            if has_pathlike
            else _center_ellipsize(summary, max_chars)
        )
        truncated = True
    elif more_content:
        if len(summary) + len(suffix) > max_chars:
            summary = summary[: max_chars - len(suffix)].rstrip()
        summary = f"{summary}{suffix}"
        truncated = True

    if not truncated and len(lines) > 1:
        summary = f"{summary}{suffix}"

    return summary


def _strip_assistant_markdown_prefix(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return stripped

    stripped = stripped.lstrip("#").strip() if stripped.startswith("#") else stripped
    if stripped.startswith("> "):
        stripped = stripped[2:].strip()
    stripped = re.sub(r"^[-*+]\s+", "", stripped)
    stripped = re.sub(r"^\d+\.\s+", "", stripped)
    stripped = re.sub(r"^- \[[ xX]\]\s+", "", stripped)
    return stripped.strip()


def _is_list_line(line: str) -> bool:
    stripped = line.lstrip()
    return bool(
        re.match(r"^(?:[-*+]\s+|\d+\.\s+|- \[[ xX]\]\s+)", stripped)
    )


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_table_separator(line: str) -> bool:
    stripped = line.strip().strip("|").strip()
    if not stripped:
        return False
    cells = [cell.strip() for cell in stripped.split("|")]
    return bool(cells) and all(cell and set(cell) <= {":", "-"} for cell in cells)


def _table_preview_summary(header_line: str) -> str:
    cells = [cell.strip() for cell in header_line.strip().strip("|").split("|")]
    cells = [cell for cell in cells if cell]
    if not cells:
        return "table"
    preview_cells = cells[:_COMPACT_TABLE_COLUMNS]
    summary = " | ".join(preview_cells)
    return f"table: {summary}"


def _list_preview_summary(line: str) -> str:
    item = _strip_assistant_markdown_prefix(line)
    if _should_compact_transcript_preview():
        item_budget = min(_COMPACT_ASSISTANT_CHARS - 6, max(32, _transcript_render_columns() - 8))
        if len(item) > item_budget:
            item = f"{item[: item_budget - 3].rstrip()}..."
    return f"list: {item}"


def _first_list_preview(meaningful_lines: list[tuple[int, str]]) -> str | None:
    if not meaningful_lines:
        return None
    _, first_line = meaningful_lines[0]
    if not _is_list_line(first_line):
        return None

    list_count = 0
    for _, item_line in meaningful_lines:
        stripped = item_line.strip()
        if _is_list_line(item_line):
            list_count += 1
            continue
        if stripped:
            break
    summary = _list_preview_summary(first_line.strip())
    return f"{summary}\n..." if list_count > 1 else summary


def _first_quote_preview(meaningful_lines: list[tuple[int, str]]) -> str | None:
    quote_lines = []
    for _, quote_line in meaningful_lines:
        stripped_quote = quote_line.strip()
        if not stripped_quote.startswith(">"):
            break
        normalized = _strip_assistant_markdown_prefix(stripped_quote)
        if normalized:
            quote_lines.append(normalized)
    if not quote_lines:
        return None
    return (
        f"quote: {quote_lines[0]}\n..."
        if len(quote_lines) > 1
        else f"quote: {quote_lines[0]}"
    )


def _find_followup_table_summary(lines: list[str], start_index: int) -> str | None:
    for idx in range(start_index + 1, len(lines) - 1):
        row = lines[idx].strip()
        if _is_table_row(row) and _is_table_separator(lines[idx + 1]):
            return _table_preview_summary(row)
    return None


def _find_followup_quote_summary(lines: list[str], start_index: int) -> str | None:
    for idx in range(start_index + 1, len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            normalized = _strip_assistant_markdown_prefix(stripped)
            if normalized:
                return f"quote: {normalized}"
        if stripped and not stripped.startswith((">", "```")):
            continue
    return None


def _find_followup_list_summary(lines: list[str], start_index: int) -> str | None:
    for idx in range(start_index + 1, len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if _is_list_line(lines[idx]):
            return _list_preview_summary(stripped)
    return None


def _find_followup_code_summary(lines: list[str], start_index: int) -> str | None:
    for idx in range(start_index + 1, len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if not stripped.startswith("```"):
            continue

        lang = stripped[3:].strip()
        for code_idx in range(idx + 1, len(lines)):
            code_line = lines[code_idx].strip()
            if not code_line:
                continue
            if code_line.startswith("```"):
                break
            code_summary = _compact_code_preview_line(code_line)
            if code_summary:
                label = f"{lang} code" if lang else "code"
                return f"{label}: {code_summary}"
        return f"{lang} code" if lang else "code"
    return None


def _find_followup_candidates_with_end_indices(
    lines: list[str], start_index: int
) -> list[tuple[str, str, int]]:
    candidates: list[tuple[str, str, int]] = []
    seen_kinds: set[str] = set()
    idx = start_index + 1

    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            continue

        if "code" not in seen_kinds and stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_summary = f"{lang} code" if lang else "code"
            block_end_index = idx
            idx += 1
            while idx < len(lines):
                code_line = lines[idx].strip()
                if code_line.startswith("```"):
                    block_end_index = idx
                    break
                compact = _compact_code_preview_line(code_line)
                if compact and code_summary == (f"{lang} code" if lang else "code"):
                    label = f"{lang} code" if lang else "code"
                    code_summary = f"{label}: {compact}"
                block_end_index = idx
                idx += 1
            candidates.append(("code", code_summary, block_end_index))
            seen_kinds.add("code")
        elif "table" not in seen_kinds and idx + 1 < len(lines) and _is_table_row(stripped) and _is_table_separator(lines[idx + 1]):
            block_end_index = idx + 1
            scan_index = idx + 2
            while scan_index < len(lines):
                scan_stripped = lines[scan_index].strip()
                if _is_table_row(scan_stripped):
                    block_end_index = scan_index
                    scan_index += 1
                    continue
                if scan_stripped:
                    break
                scan_index += 1
            candidates.append(("table", _table_preview_summary(stripped), block_end_index))
            seen_kinds.add("table")
            idx += 1
        elif "quote" not in seen_kinds and stripped.startswith(">"):
            normalized = _strip_assistant_markdown_prefix(stripped)
            block_end_index = idx
            if normalized:
                candidates.append(("quote", f"quote: {normalized}", block_end_index))
                seen_kinds.add("quote")
            while idx + 1 < len(lines) and lines[idx + 1].strip().startswith(">"):
                idx += 1
                block_end_index = idx
            if normalized:
                candidates[-1] = ("quote", f"quote: {normalized}", block_end_index)
        elif "list" not in seen_kinds and _is_list_line(lines[idx]):
            block_end_index = idx
            while idx + 1 < len(lines):
                next_stripped = lines[idx + 1].strip()
                if not next_stripped:
                    break
                if not _is_list_line(lines[idx + 1]):
                    break
                idx += 1
                block_end_index = idx
            candidates.append(("list", _list_preview_summary(stripped), block_end_index))
            seen_kinds.add("list")

        idx += 1

    return candidates


def _find_followup_candidates(lines: list[str], start_index: int) -> list[tuple[str, str]]:
    return [
        (kind, summary)
        for kind, summary, _ in _find_followup_candidates_with_end_indices(lines, start_index)
    ]


def _find_followup_plain_text_summary_with_index(
    lines: list[str], start_index: int
) -> tuple[str, int] | None:
    candidates = _find_followup_plain_text_summaries_with_indices(lines, start_index)
    if candidates:
        return candidates[0]
    return None


def _find_followup_plain_text_summaries_with_indices(
    lines: list[str], start_index: int
) -> list[tuple[str, int]]:
    idx = start_index + 1
    candidates: list[tuple[str, int]] = []

    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            continue

        if stripped.startswith("```"):
            idx += 1
            while idx < len(lines):
                if lines[idx].strip().startswith("```"):
                    break
                idx += 1
            idx += 1
            continue

        if _is_table_row(stripped):
            idx += 1
            continue

        if stripped.startswith(">") or _is_list_line(lines[idx]):
            idx += 1
            continue

        normalized = _strip_assistant_markdown_prefix(stripped)
        if normalized:
            candidates.append((normalized, idx))
        idx += 1

    return candidates


def _find_followup_plain_text_summary(lines: list[str], start_index: int) -> str | None:
    match = _find_followup_plain_text_summary_with_index(lines, start_index)
    if match:
        return match[0]
    return None


def _finalize_primary_assistant_preview(
    summary: str,
    lines: list[str],
    start_index: int,
    *,
    force_more: bool = False,
    closing_text_summary: str | None = None,
) -> str:
    followup_candidates = _find_followup_candidates_with_end_indices(lines, start_index)
    plain_followup_candidates = _find_followup_plain_text_summaries_with_indices(
        lines, start_index
    )
    plain_followup = plain_followup_candidates[0] if plain_followup_candidates else None
    remaining_followups = followup_candidates

    if followup_candidates and plain_followup:
        first_followup_summary, first_followup_index = plain_followup
        first_marker_kind, first_marker_summary, first_marker_end_index = followup_candidates[0]
        preferred_plain_followup = first_followup_summary
        if len(plain_followup_candidates) > 1:
            preferred_plain_followup = plain_followup_candidates[-1][0]
        if first_marker_end_index < first_followup_index:
            summary = _compose_assistant_followup_summary(summary, first_marker_summary)
            summary = _compose_assistant_followup_summary(summary, preferred_plain_followup)
            remaining_followups = followup_candidates[1:]
        else:
            summary = _compose_assistant_followup_summary(summary, preferred_plain_followup)
    elif plain_followup:
        summary = _compose_assistant_followup_summary(summary, plain_followup[0])
    elif closing_text_summary:
        summary = _compose_assistant_followup_summary(summary, closing_text_summary)

    for marker_kind, _, _ in remaining_followups:
        summary = _append_assistant_followup_marker(summary, marker_kind)

    if force_more or remaining_followups:
        inline_more_budget = max(16, _transcript_render_columns() - 2)
        if len(summary) + 4 <= inline_more_budget:
            return f"{summary} ..."
        return f"{summary}\n..."
    return summary


def _compose_assistant_followup_summary(summary: str, followup: str) -> str:
    compact_budget = _COMPACT_ASSISTANT_CHARS
    if " code:" in followup:
        compact_budget = min(compact_budget, max(44, _transcript_render_columns() - 6))

    combined = f"{summary} - {followup}"
    if len(combined) <= compact_budget:
        return combined

    if ": " in summary and ": " in followup:
        followup_budget = max(20, compact_budget - len(summary) - 3)
        if len(followup) > followup_budget:
            followup = _ellipsize_structured_followup(followup, followup_budget)
        combined = f"{summary} - {followup}"
        if len(combined) <= compact_budget:
            return combined

        followup_kind = None
        if "code:" in followup:
            followup_kind = "code"
        elif followup.startswith("table:"):
            followup_kind = "table"
        elif followup.startswith("quote:"):
            followup_kind = "quote"
        elif followup.startswith("list:"):
            followup_kind = "list"

        if followup_kind:
            reduced = f"{summary} [{followup_kind}]"
            if len(reduced) <= compact_budget:
                return reduced

        summary_budget = max(20, compact_budget - len(followup) - 3)
        if len(summary) > summary_budget:
            summary = _ellipsize_structured_followup(summary, summary_budget)
        return f"{summary} - {followup}"

    if ": " in summary and ": " not in followup:
        followup_budget = max(16, compact_budget - len(summary) - 3)
        if len(followup) > followup_budget:
            followup = _compact_plain_followup_text(followup, followup_budget)
        combined = f"{summary} - {followup}"
        if len(combined) <= compact_budget:
            return combined

        if " - " in summary:
            first_segment, second_segment = summary.split(" - ", 1)
            if ": " in first_segment and ": " in second_segment:
                second_budget = max(10, compact_budget - len(first_segment) - len(followup) - 6)
                reduced_second = second_segment
                if len(reduced_second) > second_budget:
                    reduced_second = _ellipsize_structured_followup(reduced_second, second_budget)
                reduced = f"{first_segment} - {reduced_second} - {followup}"
                if len(reduced) <= compact_budget:
                    return reduced

                second_kind = None
                if "code:" in second_segment:
                    second_kind = "code"
                elif second_segment.startswith("table:"):
                    second_kind = "table"
                elif second_segment.startswith("quote:"):
                    second_kind = "quote"
                elif second_segment.startswith("list:"):
                    second_kind = "list"

                if second_kind:
                    reduced = f"{first_segment} [{second_kind}] - {followup}"
                    if len(reduced) <= compact_budget:
                        return reduced
                    first_budget = max(
                        14,
                        compact_budget - len(f" [{second_kind}]") - len(followup) - 3,
                    )
                    compact_first = first_segment
                    if len(compact_first) > first_budget:
                        compact_first = _ellipsize_structured_followup(
                            compact_first, first_budget
                        )
                    reduced = f"{compact_first} [{second_kind}] - {followup}"
                    if len(reduced) <= compact_budget:
                        return reduced

            plain_prefix, structured_prefix = summary.split(" - ", 1)
            if ": " not in plain_prefix and ": " in structured_prefix:
                reduced_followup_budget = max(12, compact_budget - len(structured_prefix) - 3)
                reduced_followup = followup
                if len(reduced_followup) > reduced_followup_budget:
                    reduced_followup = _compact_plain_followup_text(
                        reduced_followup, reduced_followup_budget
                    )
                reduced = f"{structured_prefix} - {reduced_followup}"
                if len(reduced) <= compact_budget:
                    return reduced

                structured_budget = max(20, compact_budget - len(reduced_followup) - 3)
                compact_structured = structured_prefix
                if len(compact_structured) > structured_budget:
                    compact_structured = _ellipsize_structured_followup(
                        compact_structured, structured_budget
                    )
                reduced = f"{compact_structured} - {reduced_followup}"
                if len(reduced) <= compact_budget:
                    return reduced
        return combined

    summary_budget = max(16, compact_budget - len(followup) - 3)
    if len(summary) > summary_budget:
        if ": " in followup and ": " not in summary:
            summary = _compact_plain_followup_text(summary, summary_budget)
        else:
            summary = _tail_weighted_ellipsize(summary, summary_budget)
    return f"{summary} - {followup}"


def _append_assistant_followup_marker(summary: str, marker: str) -> str:
    compact_budget = min(_COMPACT_ASSISTANT_CHARS - 6, max(40, _transcript_render_columns() - 8))
    compact_marker = f" [{marker}]"
    combined = f"{summary}{compact_marker}"
    if len(combined) <= compact_budget:
        return combined

    if " - " in summary:
        prefix, detail = summary.rsplit(" - ", 1)
        if ": " in prefix and ": " not in detail:
            structured_budget = min(_COMPACT_ASSISTANT_CHARS, max(44, _transcript_render_columns() - 3))
            detail_core, detail_markers = _split_trailing_followup_markers(detail)
            if prefix.startswith("table:"):
                fitted_table = _fit_table_followup_markers(
                    prefix,
                    detail_core,
                    detail_markers,
                    marker,
                    structured_budget,
                )
                if fitted_table and not detail_markers:
                    return fitted_table
            if detail_markers and detail_core:
                prioritized_detail = f"{detail_core}{detail_markers}"
                prefix_budget = max(
                    12,
                    structured_budget - len(prioritized_detail) - len(compact_marker) - 3,
                )
                compact_prefix = prefix
                if len(compact_prefix) > prefix_budget:
                    compact_prefix = _ellipsize_structured_followup(
                        compact_prefix, prefix_budget
                    )
                prioritized = (
                    f"{compact_prefix} - {prioritized_detail}{compact_marker}"
                )
                prioritized_candidate = (
                    prioritized if len(prioritized) <= structured_budget else None
                )
                if prefix.startswith("table:"):
                    fitted_markers = _fit_table_followup_markers(
                        prefix,
                        detail_core,
                        detail_markers,
                        marker,
                        structured_budget,
                    )
                else:
                    fitted_markers = _fit_trailing_followup_markers(
                        prefix,
                        detail_core,
                        detail_markers,
                        marker,
                        structured_budget,
                    )
                if prioritized_candidate and fitted_markers:
                    if prefix.startswith("table:") and _score_table_followup_candidate(
                        fitted_markers
                    ) > _score_table_followup_candidate(prioritized_candidate):
                        return fitted_markers
                    return prioritized_candidate
                if prioritized_candidate:
                    return prioritized_candidate
                if fitted_markers:
                    return fitted_markers
            detail_budget = max(14, structured_budget - len(compact_marker) - len(prefix) - 3)
            if len(detail) > detail_budget:
                detail = _compact_followup_detail_preserving_markers(
                    detail, detail_budget
                )
            combined = f"{prefix} - {detail}{compact_marker}"
            if len(combined) <= structured_budget:
                return combined

            if ": " in prefix:
                prefix_label, prefix_detail = prefix.split(": ", 1)
                if prefix_label.endswith("code"):
                    cleaned_prefix = prefix.split(" - ", 1)[1] if " - " in prefix else prefix
                    preserved_detail = f"{cleaned_prefix} - {detail}{compact_marker}"
                    if len(preserved_detail) <= structured_budget:
                        return preserved_detail

                    prefix_detail_budget = max(
                        12,
                        structured_budget - len(compact_marker) - len(prefix_label) - 2,
                    )
                    compact_prefix_detail = _compact_code_detail(
                        prefix_detail, prefix_detail_budget
                    )
                    reduced = f"{prefix_label}: {compact_prefix_detail}{compact_marker}"
                    if len(reduced) <= structured_budget:
                        return reduced

            if " - " in prefix:
                plain_prefix, structured_prefix = prefix.split(" - ", 1)
                structured_combined = f"{plain_prefix} - {structured_prefix} - {detail}{compact_marker}"
                if len(structured_combined) > structured_budget:
                    plain_budget = max(
                        10,
                        structured_budget
                        - len(structured_prefix)
                        - len(detail)
                        - len(compact_marker)
                        - 6,
                    )
                    if len(plain_prefix) > plain_budget:
                        if ": " in plain_prefix:
                            plain_prefix = _ellipsize_structured_followup(
                                plain_prefix, plain_budget
                            )
                        else:
                            plain_prefix = _compact_plain_prefix_fragment(
                                plain_prefix, plain_budget
                            )
                    structured_combined = f"{plain_prefix} - {structured_prefix} - {detail}{compact_marker}"
                if len(structured_combined) <= structured_budget:
                    return structured_combined

                reduced_detail = detail
                reduced_budget = max(
                    10,
                    structured_budget - len(structured_prefix) - len(compact_marker) - 3,
                )
                if len(reduced_detail) > reduced_budget:
                    reduced_detail = _compact_followup_detail_preserving_markers(
                        reduced_detail, reduced_budget
                    )

                nested_marker_kind = None
                if structured_prefix.startswith("code:"):
                    nested_marker_kind = "code"
                elif structured_prefix.startswith("table:"):
                    nested_marker_kind = "table"
                elif structured_prefix.startswith("quote:"):
                    nested_marker_kind = "quote"
                elif structured_prefix.startswith("list:"):
                    nested_marker_kind = "list"

                if nested_marker_kind and ": " in plain_prefix:
                    primary_prefix = plain_prefix
                    primary_budget = max(
                        14,
                        structured_budget
                        - len(f" [{nested_marker_kind}]")
                        - len(reduced_detail)
                        - len(compact_marker)
                        - 3,
                    )
                    if len(primary_prefix) > primary_budget:
                        primary_prefix = _ellipsize_structured_followup(
                            primary_prefix, primary_budget
                        )
                    reduced = (
                        f"{primary_prefix} [{nested_marker_kind}]"
                        f" - {reduced_detail}{compact_marker}"
                    )
                    if len(reduced) <= structured_budget:
                        return reduced

                reduced = f"{structured_prefix} - {reduced_detail}{compact_marker}"
                if len(reduced) <= structured_budget:
                    return reduced

        prefix_budget = max(6, compact_budget - len(compact_marker) - len(detail) - 3)
        if len(prefix) > prefix_budget:
            if ": " in prefix:
                prefix = _ellipsize_structured_followup(prefix, prefix_budget)
            else:
                prefix = _compact_plain_prefix_fragment(prefix, prefix_budget)

        combined = f"{prefix} - {detail}{compact_marker}"
        if len(combined) <= compact_budget:
            return combined

        detail_budget = max(20, compact_budget - len(compact_marker) - len(prefix) - 3)
        if len(detail) > detail_budget:
            detail = _ellipsize_structured_followup(detail, detail_budget)
        return f"{prefix} - {detail}{compact_marker}"

    summary_budget = max(16, compact_budget - len(compact_marker))
    if len(summary) > summary_budget:
        summary = _tail_weighted_ellipsize(summary, summary_budget)
    return f"{summary}{compact_marker}"


def _assistant_preview_source(body: str) -> str:
    lines = body.splitlines()
    meaningful = [(i, line) for i, line in enumerate(lines) if line.strip()]
    if not meaningful:
        return body

    first_index, first_line = meaningful[0]
    stripped_first = first_line.strip()

    if (
        _is_table_row(stripped_first)
        and len(meaningful) > 1
        and _is_table_separator(meaningful[1][1])
    ):
        table_end_index = first_index + 1
        for idx in range(first_index + 2, len(lines)):
            if _is_table_row(lines[idx].strip()):
                table_end_index = idx
                continue
            if lines[idx].strip():
                break
        closing_text_summary = _find_followup_plain_text_summary(lines, table_end_index)
        return _finalize_primary_assistant_preview(
            _table_preview_summary(stripped_first),
            lines,
            table_end_index,
            force_more=True,
            closing_text_summary=closing_text_summary,
        )

    if stripped_first.startswith("```"):
        lang = stripped_first[3:].strip()
        code_line = ""
        code_end_index = first_index
        for later_index, later_line in meaningful[1:]:
            later = later_line.strip()
            if later.startswith("```"):
                code_end_index = later_index
                break
            if not code_line:
                code_line = _compact_code_preview_line(later)
        label = f"{lang} code" if lang else "code"
        closing_text_summary = _find_followup_plain_text_summary(lines, code_end_index)
        if code_line:
            return _finalize_primary_assistant_preview(
                f"{label}: {code_line}",
                lines,
                code_end_index,
                force_more=True,
                closing_text_summary=closing_text_summary,
            )
        return _finalize_primary_assistant_preview(
            f"{label} block",
            lines,
            code_end_index,
            force_more=True,
            closing_text_summary=closing_text_summary,
        )

    if stripped_first.startswith(">"):
        quote_preview = _first_quote_preview(meaningful)
        if quote_preview:
            quote_end_index = first_index
            for idx in range(first_index + 1, len(lines)):
                stripped = lines[idx].strip()
                if not stripped:
                    continue
                if stripped.startswith(">"):
                    quote_end_index = idx
                    continue
                break
            closing_text_summary = _find_followup_plain_text_summary(lines, quote_end_index)
            return _finalize_primary_assistant_preview(
                quote_preview.split("\n", 1)[0],
                lines,
                quote_end_index,
                force_more="\n..." in quote_preview,
                closing_text_summary=closing_text_summary,
            )

    if _is_list_line(stripped_first):
        list_preview = _first_list_preview(meaningful)
        if list_preview:
            list_end_index = first_index
            for idx in range(first_index + 1, len(lines)):
                stripped = lines[idx].strip()
                if not stripped:
                    continue
                if _is_list_line(lines[idx]):
                    list_end_index = idx
                    continue
                break
            closing_text_summary = _find_followup_plain_text_summary(lines, list_end_index)
            return _finalize_primary_assistant_preview(
                list_preview.split("\n", 1)[0],
                lines,
                list_end_index,
                force_more="\n..." in list_preview,
                closing_text_summary=closing_text_summary,
            )

    summary = _strip_assistant_markdown_prefix(stripped_first)
    has_more = len(meaningful) > 1
    followup_candidates = _find_followup_candidates_with_end_indices(lines, first_index)

    if followup_candidates:
        kind, followup, first_followup_end_index = followup_candidates[0]
        summary = _compose_assistant_followup_summary(summary, followup)
        has_more = True

        plain_followup_candidates = _find_followup_plain_text_summaries_with_indices(
            lines, first_followup_end_index
        )
        closing_text_summary = None
        if plain_followup_candidates:
            if len(followup_candidates) > 1:
                closing_text_summary = plain_followup_candidates[-1][0]
            else:
                closing_text_summary = plain_followup_candidates[0][0]
        if closing_text_summary:
            summary = _compose_assistant_followup_summary(summary, closing_text_summary)

        for marker_kind, _, _ in followup_candidates[1:]:
            summary = _append_assistant_followup_marker(summary, marker_kind)
            has_more = True

    return f"{summary}\n..." if has_more and summary else summary


def preview_tool_body(tool_name: str, body: str) -> str:
    """Truncate tool output based on tool name and content size."""
    max_chars = 1000 if tool_name == "read_file" else 1800
    max_lines = 20 if tool_name == "read_file" else 36

    lines = body.split("\n")
    limited_lines = lines[:max_lines] if len(lines) > max_lines else lines
    limited = "\n".join(limited_lines)

    if len(limited) > max_chars:
        limited = limited[:max_chars] + "..."

    if limited != body:
        return f"{limited}\n{DIM}... output truncated in transcript{RESET}"

    return limited


def _render_transcript_entry(entry: TranscriptEntry) -> str:
    """Render a single TranscriptEntry with Morandi theme colors."""
    t = theme()

    if entry.kind == "assistant":
        label = f"{t.assistant}{t.bold}{ICON_DOT} assistant{t.reset}"
        if _should_compact_transcript_preview() and (
            "\n" in entry.body or len(entry.body) > _COMPACT_ASSISTANT_CHARS
        ):
            assistant_preview = _assistant_preview_source(entry.body)
            body = render_markdownish(
                assistant_preview
                if assistant_preview != entry.body
                else _compact_transcript_preview(assistant_preview, _COMPACT_ASSISTANT_CHARS)
            )
        else:
            body = render_markdownish(entry.body)
        return f"{label}\n{_indent_block(body)}"

    if entry.kind == "user":
        label = f"{t.user}{t.bold}鈻?you{t.reset}"
        return f"{label}\n{_indent_block(entry.body)}"

    if entry.kind == "assistant":
        label = f"{t.assistant}{t.bold}鈻?assistant{t.reset}"
        return f"{label}\n{_indent_block(render_markdownish(entry.body))}"

    if entry.kind == "progress":
        label = f"{t.progress}{t.bold}鈻?progress{t.reset}"
        body = (
            render_markdownish(
                _compact_transcript_preview(entry.body, _COMPACT_PROGRESS_CHARS)
            )
            if _should_compact_transcript_preview()
            else render_markdownish(entry.body)
        )
        return f"{label}\n{_indent_block(body)}"

    if entry.kind == "tool":
        if entry.status == "running":
            status_label = f"{t.tool}{ICON_DOT} running{t.reset}"
        elif entry.status == "success":
            status_label = f"{t.assistant}ok{t.reset}"
        else:
            status_label = f"{t.tool_error}err{t.reset}"

        tool_name_display = f"{t.tool}{t.bold}{entry.toolName}{t.reset}"

        body_lines = entry.body.split("\n") if entry.body else []
        total_lines = len(body_lines)
        collapsible_by_lines = total_lines > _TOOL_PREVIEW_LINES
        collapsible_by_chars = any(
            len(ln) > _TOOL_PREVIEW_CHARS for ln in body_lines[:_TOOL_PREVIEW_LINES]
        )
        is_collapsed = entry.collapsed or entry.collapsePhase == 3
        is_collapsing = entry.collapsePhase in (1, 2)
        can_toggle = collapsible_by_lines or collapsible_by_chars or is_collapsing

        if can_toggle:
            if is_collapsing:
                toggle_text = f"  {t.expandable}{t.bold}[collapsing]{t.reset}"
            else:
                toggle_text = (
                    f"  {t.expandable}{t.bold}[鏀惰捣]{t.reset}"
                    if not is_collapsed
                    else f"  {t.expandable}{t.bold}[灞曞紑]{t.reset}"
                )
        else:
            toggle_text = ""

        label = (
            f"{t.tool}{t.bold}鈻?tool{t.reset} {tool_name_display}"
            f" {status_label}{toggle_text}"
        )

        if entry.status == "running":
            body = (
                _compact_transcript_preview(entry.body, _COMPACT_TOOL_CHARS)
                if _should_compact_transcript_preview()
                else entry.body
            )
        elif is_collapsing:
            if collapsible_by_lines:
                preview = "\n".join(body_lines[:_TOOL_PREVIEW_LINES])
                hidden = max(0, total_lines - _TOOL_PREVIEW_LINES)
                body = (
                    preview_tool_body(entry.toolName or "", render_markdownish(preview))
                    + (f"\n{t.subtle}  ... {hidden} more lines{t.reset}" if hidden > 0 else "")
                )
            else:
                body = preview_tool_body(entry.toolName or "", render_markdownish(entry.body))
        elif is_collapsed:
            summary = entry.collapsedSummary or "output collapsed"
            if _should_compact_transcript_preview():
                summary = _compact_transcript_preview(summary, _COMPACT_TOOL_CHARS)
            body = f"{t.subtle}{t.italic}{summary}{t.reset}"
        else:
            if collapsible_by_lines:
                preview = "\n".join(body_lines[:_TOOL_PREVIEW_LINES])
                hidden = total_lines - _TOOL_PREVIEW_LINES
                body = (
                    preview_tool_body(entry.toolName or "", render_markdownish(preview))
                    + f"\n{t.subtle}  ... {hidden} more lines{t.reset}"
                )
            else:
                body = preview_tool_body(entry.toolName or "", render_markdownish(entry.body))

        return f"{label}\n{_indent_block(body)}"

    return ""


def get_transcript_window_size(window_size: int | None = None) -> int:
    if window_size is not None:
        return max(4, window_size)
    _, rows = _cached_terminal_size()
    return max(8, rows - 15)


@dataclass(slots=True)
class TranscriptLayout:
    revision: int
    total_lines: int
    entry_line_starts: list[int]
    entry_line_counts: list[int]


_EntryCacheKey = tuple[
    str,
    str,
    str | None,
    bool,
    int | None,
    str | None,
    str | None,
    int,
]
_entry_cache: dict[_EntryCacheKey, list[str]] = {}
_line_count_cache: dict[_EntryCacheKey, int] = {}
_LayoutCacheKey = tuple[int, int, int, int]
_layout_cache: dict[_LayoutCacheKey, TranscriptLayout] = {}
_CACHE_MAX_SIZE = 500
_LAYOUT_CACHE_MAX_SIZE = 64


def _entry_cache_key(entry: TranscriptEntry) -> _EntryCacheKey:
    """Build a collision-free key from entry render-affecting state."""
    return (
        entry.kind,
        entry.body,
        entry.status,
        entry.collapsed,
        entry.collapsePhase,
        entry.collapsedSummary,
        entry.toolName,
        _transcript_render_columns(),
    )


def _get_entry_lines(entry: TranscriptEntry) -> list[str]:
    cache_key = _entry_cache_key(entry)

    cached = _entry_cache.get(cache_key)
    if cached is not None:
        return cached

    lines = _render_transcript_entry(entry).split("\n")

    if len(_entry_cache) > _CACHE_MAX_SIZE:
        keys = list(_entry_cache.keys())
        for k in keys[: len(keys) // 2]:
            del _entry_cache[k]
            _line_count_cache.pop(k, None)

    _entry_cache[cache_key] = lines
    return lines


def _get_entry_line_count(entry: TranscriptEntry) -> int:
    cache_key = _entry_cache_key(entry)

    cached_lc = _line_count_cache.get(cache_key)
    if cached_lc is not None:
        return cached_lc

    cached_full = _entry_cache.get(cache_key)
    if cached_full is not None:
        count = len(cached_full)
        _line_count_cache[cache_key] = count
        return count

    lines = _get_entry_lines(entry)
    count = len(lines)
    _line_count_cache[cache_key] = count
    return count


def _layout_cache_key(
    entries: list[TranscriptEntry],
    revision: int | None,
) -> _LayoutCacheKey | None:
    if revision is None:
        return None
    return (id(entries), revision, len(entries), _transcript_render_columns())


def _build_transcript_layout(
    entries: list[TranscriptEntry],
    revision: int | None,
) -> TranscriptLayout:
    cache_key = _layout_cache_key(entries, revision)
    if cache_key is not None:
        cached = _layout_cache.get(cache_key)
        if cached is not None:
            return cached

    entry_line_starts: list[int] = []
    entry_line_counts: list[int] = []
    current_line = 0

    for i, entry in enumerate(entries):
        if i > 0:
            current_line += _SEPARATOR_LINE_COUNT
        entry_line_starts.append(current_line)
        line_count = _get_entry_line_count(entry)
        entry_line_counts.append(line_count)
        current_line += line_count

    layout = TranscriptLayout(
        revision=revision or 0,
        total_lines=current_line,
        entry_line_starts=entry_line_starts,
        entry_line_counts=entry_line_counts,
    )

    if cache_key is not None:
        if len(_layout_cache) >= _LAYOUT_CACHE_MAX_SIZE:
            for key in list(_layout_cache.keys())[: len(_layout_cache) // 2]:
                del _layout_cache[key]
        _layout_cache[cache_key] = layout
    return layout


def _compute_total_lines(entries: list[TranscriptEntry], revision: int | None = None) -> int:
    if not entries:
        return 0
    return _build_transcript_layout(entries, revision).total_lines


def _render_visible_window(
    entries: list[TranscriptEntry],
    start_line: int,
    end_line: int,
    revision: int | None = None,
) -> list[str]:
    if not entries:
        return []

    layout = _build_transcript_layout(entries, revision)
    result: list[str] = []
    if not layout.entry_line_starts:
        return result

    start_index = bisect_left(layout.entry_line_starts, start_line)
    if start_index > 0:
        start_index -= 1

    for i in range(start_index, len(entries)):
        entry_start = layout.entry_line_starts[i]
        entry_line_count = layout.entry_line_counts[i]
        entry_end = entry_start + entry_line_count

        if i > 0:
            sep_start = entry_start - _SEPARATOR_LINE_COUNT
            sep_end = entry_start
            if sep_start < end_line and sep_end > start_line:
                vis_start = max(0, start_line - sep_start)
                vis_end = min(_SEPARATOR_LINE_COUNT, end_line - sep_start)
                result.extend(_SEPARATOR_LINES[vis_start:vis_end])

        if entry_start >= end_line:
            break

        if entry_start < end_line and entry_end > start_line:
            lines = _get_entry_lines(entries[i])
            vis_start = max(0, start_line - entry_start)
            vis_end = min(entry_line_count, end_line - entry_start)
            result.extend(lines[vis_start:vis_end])

    return result


def get_transcript_max_scroll_offset(
    entries: list[TranscriptEntry],
    window_size: int | None = None,
    revision: int | None = None,
) -> int:
    if not entries:
        return 0
    total = _compute_total_lines(entries, revision)
    ws = get_transcript_window_size(window_size)
    return max(0, total - ws)


def render_transcript(
    entries: list[TranscriptEntry],
    scroll_offset: int,
    window_size: int | None = None,
    revision: int | None = None,
) -> str:
    """Render a windowed view of the transcript. O(visible)."""
    t = theme()
    if not entries:
        return ""

    layout = _build_transcript_layout(entries, revision)
    total_lines = layout.total_lines
    ws = get_transcript_window_size(window_size)
    max_offset = max(0, total_lines - ws)
    offset = max(0, min(scroll_offset, max_offset))

    if offset == 0:
        end = total_lines
        start = max(0, end - ws)
        visible_lines = _render_visible_window(entries, start, end, revision)
        return "\n".join(visible_lines)

    content_ws = max(1, ws - 1)
    end = total_lines - offset
    start = max(0, end - content_ws)
    visible_lines = _render_visible_window(entries, start, end, revision)
    body = "\n".join(visible_lines)

    return (
        f"{body}\n"
        f"{t.subtle}  {ICON_DIVIDER * 2} scroll {offset}/{max_offset} "
        f"(PgUp/PgDn or scroll){ICON_DIVIDER * 2}{t.reset}"
    )


# ---------------------------------------------------------------------------
# Legacy full-render API (backward compat)
# ---------------------------------------------------------------------------

def _render_transcript_lines(entries: list[TranscriptEntry]) -> list[str]:
    """Render all entries into lines with separators. Kept for backward compat."""
    all_lines: list[str] = []
    for i, entry in enumerate(entries):
        if i > 0:
            all_lines.extend(_SEPARATOR_LINES)
        all_lines.extend(_get_entry_lines(entry))
    return all_lines


def format_transcript_text(entries: list[TranscriptEntry]) -> str:
    """Format transcript entries as plain text (no ANSI) for file saving."""
    parts = []
    for entry in entries:
        label = "you" if entry.kind == "user" else entry.kind
        if entry.kind == "tool":
            status_text = f" ({entry.status})" if entry.status else ""
            label = f"{entry.toolName or 'tool'}{status_text}"
        indented = "\n".join("  " + line for line in entry.body.splitlines())
        parts.append(f"{label}\n{indented}")
    return "\n\n---\n\n".join(parts)
