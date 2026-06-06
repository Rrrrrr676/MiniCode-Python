import re

from minicode.tty_app import (
    _ThrottledRenderer,
    _apply_tool_result_visual_state,
    _format_history,
    _mark_unfinished_tools,
    _save_transcript,
    summarize_tool_input,
    summarize_tool_output,
)
import minicode.tui.input_handler as input_handler_module
import minicode.tui.chrome as chrome_module
import minicode.tui.transcript as transcript_module
from minicode.context_manager import ContextManager
from minicode.permissions import PermissionManager
from minicode.tooling import ToolCapability, ToolDefinition, ToolMetadata, ToolRegistry, ToolResult
from minicode.tui.tool_helpers import _record_recent_tool
from minicode.tui.runtime_control import _ThrottledRenderer as RuntimeThrottledRenderer
from minicode.tui.event_flow import _handle_event
from minicode.tui.input_parser import KeyEvent
from minicode.tui.state import ScreenState, TtyAppArgs
from minicode.tui.transcript import format_transcript_text
from minicode.tui.types import TranscriptEntry


def test_tty_app_uses_runtime_control_throttled_renderer() -> None:
    assert _ThrottledRenderer is RuntimeThrottledRenderer


def test_summarize_tool_output_prefers_first_meaningful_line() -> None:
    output = "\n\nFILE: README.md\nOFFSET: 0\nEND: 100"
    assert summarize_tool_output("read_file", output).startswith("FILE: README.md")


def test_summarize_tool_output_truncates_long_lines() -> None:
    output = "x" * 400
    summary = summarize_tool_output("run_command", output)
    assert len(summary) < 200
    assert summary.endswith("...")


def test_format_history_shows_recent_entries_with_numbers() -> None:
    rendered = _format_history(["/help", "build parser", "/cmd pytest -q"], limit=2)
    assert rendered == "2. build parser\n3. /cmd pytest -q"


def test_save_transcript_writes_plain_text(tmp_path) -> None:
    state_entries = [
        TranscriptEntry(id=1, kind="user", body="hello"),
        TranscriptEntry(id=2, kind="assistant", body="world"),
    ]
    permissions = PermissionManager(str(tmp_path), prompt=lambda request: {"decision": "allow_once"})

    path = _save_transcript(
        type("State", (), {"transcript": state_entries})(),
        str(tmp_path),
        permissions,
        "logs/session.txt",
    )

    assert path.endswith("logs\\session.txt") or path.endswith("logs/session.txt")
    assert (tmp_path / "logs" / "session.txt").read_text(encoding="utf-8") == "you\n  hello\n\n---\n\nassistant\n  world"


def test_format_transcript_text_uses_clean_separator() -> None:
    rendered = format_transcript_text(
        [
            TranscriptEntry(id=1, kind="user", body="one"),
            TranscriptEntry(id=2, kind="assistant", body="two"),
        ]
    )

    assert "\n\n---\n\n" in rendered


def test_summarize_tool_input_formats_patch_file() -> None:
    summary = summarize_tool_input(
        "patch_file",
        {"path": "demo.txt", "replacements": [{"search": "a", "replace": "b"}, {"search": "c", "replace": "d"}]},
    )

    assert summary == "patch_file path=demo.txt replacements=2"


def test_mark_unfinished_tools_marks_running_entries_as_errors() -> None:
    state = type(
        "State",
        (),
        {
            "transcript": [TranscriptEntry(id=1, kind="tool", body="running", toolName="run_command", status="running")],
            "recent_tools": [],
            "pending_tool_runs": {"run_command": [{"entry": "placeholder"}]},
            "active_tool": "run_command",
        },
    )()

    count = _mark_unfinished_tools(state)

    assert count == 1
    assert state.transcript[0].status == "error"
    assert "did not report a final result" in state.transcript[0].body
    assert state.recent_tools[-1]["name"] == "run_command"
    assert state.recent_tools[-1]["status"] == "error"
    assert state.pending_tool_runs == {}
    assert state.active_tool is None


def test_record_recent_tool_merges_duplicates_and_caps_history() -> None:
    state = type("State", (), {"recent_tools": []})()

    _record_recent_tool(state, "read_file", "success", display_name="read_file (1.2s)", max_items=3)
    _record_recent_tool(state, "read_file", "success", display_name="read_file (0.8s)", max_items=3)
    _record_recent_tool(state, "run_command", "error", max_items=3)
    _record_recent_tool(state, "list_files", "success", max_items=3)
    _record_recent_tool(state, "write_file", "success", max_items=3)

    assert state.recent_tools == [
        {"tool": "run_command", "name": "run_command", "status": "error", "count": 1},
        {"tool": "list_files", "name": "list_files", "status": "success", "count": 1},
        {"tool": "write_file", "name": "write_file", "status": "success", "count": 1},
    ]


def test_record_recent_tool_uses_compact_label_for_consecutive_duplicates() -> None:
    state = type("State", (), {"recent_tools": []})()

    _record_recent_tool(state, "read_file", "success", display_name="read_file (1.2s)")
    _record_recent_tool(state, "read_file", "success", display_name="read_file (0.8s)")

    assert state.recent_tools == [
        {"tool": "read_file", "name": "read_file x2", "status": "success", "count": 2},
    ]


def test_render_tool_panel_truncates_long_labels_for_narrow_terminal(monkeypatch) -> None:
    monkeypatch.setattr(chrome_module, "_cached_terminal_size", lambda: (52, 20))

    rendered = chrome_module.render_tool_panel(
        "run_command python scripts/very/deep/path/to/long_runner.py --flag value",
        [
            {"name": r"read_file path=C:\Users\question\projects\minicode\src\very_long_file_name.py", "status": "success"},
            {"name": "apply_patch with a very long summary that should not stretch the panel forever", "status": "error"},
        ],
        background_tasks=[{"status": "running", "label": "background synchronization task with a long label"}],
    )
    plain = re.sub(r"\x1b\[[0-9;]*m", "", rendered)

    assert "..." in plain
    assert "very_long_file_name.py" not in plain
    assert "background synchronization task with a long label" not in plain
    assert "apply_patch with a very long summary that should not stretch the panel forever" not in plain


def test_render_footer_bar_compacts_right_side_on_narrow_terminal(monkeypatch) -> None:
    monkeypatch.setattr(chrome_module, "_cached_terminal_size", lambda: (44, 20))

    rendered = chrome_module.render_footer_bar(
        "Running extremely long tool status for verification",
        tools_enabled=True,
        skills_enabled=False,
        background_tasks=[{"status": "running"}, {"status": "running"}],
    )
    plain = re.sub(r"\x1b\[[0-9;]*m", "", rendered)

    assert chrome_module.string_display_width(rendered) <= 44
    assert "tools" not in plain
    assert "skills" not in plain
    assert "..." in plain
    assert "2 bg" not in plain


def test_render_transcript_compacts_progress_preview_on_narrow_terminal(monkeypatch) -> None:
    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))

    rendered = transcript_module.render_transcript(
        [
            TranscriptEntry(
                id=1,
                kind="progress",
                body="Scanning project for matching files across several directories\nsecond detail line\nthird detail line",
            )
        ],
        scroll_offset=0,
        window_size=8,
        revision=1,
    )
    plain = re.sub(r"\x1b\[[0-9;]*m", "", rendered)

    assert "Scanning project for matchi" in plain
    assert "directories" in plain
    assert "..." in plain
    assert "second detail line" not in plain


def test_render_transcript_compacts_assistant_list_preview_on_narrow_terminal(monkeypatch) -> None:
    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))

    rendered = transcript_module.render_transcript(
        [
            TranscriptEntry(
                id=1,
                kind="assistant",
                body=(
                    "1. Inspect transcript renderer for narrow terminal layout\n"
                    "2. Run focused pytest\n"
                    "3. Summarize findings"
                ),
            )
        ],
        scroll_offset=0,
        window_size=8,
        revision=11,
    )
    plain = re.sub(r"\x1b\[[0-9;]*m", "", rendered)

    assert "Inspect transcript renderer" in plain
    assert "..." in plain
    assert "Run focused pytest" not in plain


def test_render_transcript_compacts_assistant_code_block_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body="```python\ndef build_turn_state(state):\n    return state\n```",
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=12)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=12)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "python code:" in narrow_plain
    assert "build_turn_state" in narrow_plain
    assert "return state" not in narrow_plain
    assert "return state" in wide_plain


def test_render_transcript_compacts_assistant_table_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "| Step | Owner | Status | Notes |\n"
                "| --- | --- | --- | --- |\n"
                "| transcript | codex | done | narrowed preview |\n"
                "| tty | codex | next | verify quote layout |"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=13)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=13)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "table: Step | Owner | Status" in narrow_plain
    assert "Notes" not in narrow_plain
    assert "narrowed preview" not in narrow_plain
    assert "transcript" in wide_plain
    assert "codex" in wide_plain
    assert "done" in wide_plain
    assert "narrowed preview" in wide_plain


def test_render_transcript_compacts_assistant_quote_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "> Keep the first screen focused on the next action.\n"
                "> Trim repeated context before showing tool details.\n\n"
                "Then continue with the wider explanation."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=14)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=14)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "quote: Keep the first screen focused on the next action." in narrow_plain
    assert "Trim repeated context before showing tool details." not in narrow_plain
    assert "Trim repeated context before showing tool details." in wide_plain


def test_render_transcript_compacts_nested_list_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "- Tighten transcript preview ordering\n"
                "  - Keep progress ahead of tool results\n"
                "  - Collapse repeated tool chatter\n"
                "- Re-run focused pytest"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=17)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=17)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "list: Tighten transcript preview ordering" in narrow_plain
    assert "Keep progress ahead of tool results" not in narrow_plain
    assert "Keep progress ahead of tool results" in wide_plain


def test_render_transcript_compacts_intro_plus_table_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Deployment summary for this turn.\n\n"
                "| Step | Owner | Status | Notes |\n"
                "| --- | --- | --- | --- |\n"
                "| transcript | codex | done | narrowed preview |\n"
                "| tty | codex | next | verify quote layout |"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=15)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "table: Step | Owner | Status" in narrow_plain
    assert "this turn" in narrow_plain
    assert "narrowed preview" not in narrow_plain


def test_render_transcript_compacts_intro_plus_list_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Next pass priorities.\n\n"
                "- Tighten transcript preview ordering\n"
                "  - Keep progress ahead of tool results\n"
                "- Re-run focused pytest"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=18)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert " - list:" in narrow_plain
    assert "Tighten transcript preview orde" in narrow_plain
    assert "Keep progress ahead of tool results" not in narrow_plain


def test_render_transcript_compacts_intro_plus_quote_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Recommendation for the next pass.\n\n"
                "> Keep the first screen focused on the next action.\n"
                "> Trim repeated context before showing tool details."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=16)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert " - quote:" in narrow_plain
    assert "next pass" in narrow_plain
    assert "focused on the next action." in narrow_plain
    assert "Trim repeated context before showing tool details." not in narrow_plain


def test_render_transcript_compacts_intro_plus_code_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Patch walkthrough for the next turn.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=19)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=19)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "python code:" in narrow_plain
    assert "build_turn_state" in narrow_plain
    assert "return state" not in narrow_plain
    assert "return state" in wide_plain


def test_render_transcript_compacts_intro_plus_code_and_list_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Patch walkthrough for the next turn.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "- Re-run focused pytest\n"
                "- Save transcript snapshot"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=20)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=20)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "python code:" in narrow_plain
    assert "build_turn_state" in narrow_plain
    assert "[list]" in narrow_plain
    assert "Re-run focused pytest" not in narrow_plain
    assert "Re-run focused pytest" in wide_plain


def test_render_transcript_keeps_inline_more_indicator_for_code_preview_when_it_fits(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "Keep verification focused on state anchors before broadening retrieval.\n\n"
                "- Re-run focused pytest\n"
                "- Save transcript snapshot"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=201)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    lines = narrow_plain.splitlines()
    assert any("python code: build_turn_state" in line for line in lines)
    assert lines[-1].endswith("...")
    assert "anchors [list]" in narrow_plain
    assert "\n..." not in narrow_plain


def test_render_transcript_compacts_intro_plus_code_and_table_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Patch walkthrough for the next turn.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "| Step | Owner | Status | Notes |\n"
                "| --- | --- | --- | --- |\n"
                "| transcript | codex | done | narrowed preview |\n"
                "| tty | codex | next | verify quote layout |"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=21)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=21)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "python code:" in narrow_plain
    assert "build_turn_state" in narrow_plain
    assert "[table]" in narrow_plain
    assert "Step | Owner | Status" not in narrow_plain
    assert "narrowed preview" not in narrow_plain
    assert "narrowed preview" in wide_plain


def test_render_transcript_compacts_intro_plus_code_and_quote_preview_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Patch walkthrough for the next turn.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "> Keep the first screen focused on the next action.\n"
                "> Trim repeated context before showing tool details."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=22)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=22)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "python code:" in narrow_plain
    assert "build_turn_state" in narrow_plain
    assert "[quote]" in narrow_plain
    assert "focused on the next action." not in narrow_plain
    assert "focused on the next action." in wide_plain


def test_render_transcript_compacts_intro_plus_code_then_closing_text_then_list_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Patch walkthrough for the next turn.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "Keep verification focused on state anchors before broadening retrieval.\n\n"
                "- Re-run focused pytest\n"
                "- Save transcript snapshot"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=30)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=30)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "python code:" in narrow_plain
    assert "build_turn_state" in narrow_plain
    assert "state anchors" in narrow_plain
    assert "[list]" in narrow_plain
    assert "Re-run focused pytest" not in narrow_plain
    assert "Re-run focused pytest" in wide_plain


def test_render_transcript_compacts_intro_plus_code_then_closing_text_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Patch walkthrough for the next turn.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "Return to the terminal after the focused rerun."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=32)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=32)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "python code:" in narrow_plain
    assert "build_turn_state" in narrow_plain
    assert "terminal" in narrow_plain
    assert "Return to the terminal after the focused rerun." in wide_plain


def test_render_transcript_compacts_intro_plus_table_then_closing_text_then_quote_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Deployment summary for this turn.\n\n"
                "| Step | Owner | Status | Notes |\n"
                "| --- | --- | --- | --- |\n"
                "| transcript | codex | done | narrowed preview |\n"
                "| tty | codex | next | verify quote layout |\n\n"
                "Keep verification focused on state anchors before broadening retrieval.\n\n"
                "> Keep the first screen focused on the next action.\n"
                "> Trim repeated context before showing tool details."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=31)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=31)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "table: Step | Owner | Status" in narrow_plain
    assert "state anchors" in narrow_plain
    assert "[quote]" in narrow_plain
    assert "focused on the next action." not in narrow_plain
    assert "focused on the next action." in wide_plain


def test_render_transcript_compacts_intro_plus_table_then_closing_text_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Deployment summary for this turn.\n\n"
                "| Step | Owner | Status | Notes |\n"
                "| --- | --- | --- | --- |\n"
                "| transcript | codex | done | narrowed preview |\n"
                "| tty | codex | next | verify quote layout |\n\n"
                "Return to the terminal after the focused rerun."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=33)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=33)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "table: Step | Owner | Status" in narrow_plain
    assert "terminal" in narrow_plain
    assert "Return to the terminal after the focused rerun." in wide_plain


def test_render_transcript_compacts_quote_first_then_closing_text_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "> Keep the first screen focused on the next action.\n"
                "> Trim repeated context before showing tool details.\n\n"
                "Return to the terminal after the focused rerun."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=34)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=34)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "[quote]" in narrow_plain or "quote:" in narrow_plain
    assert "terminal" in narrow_plain
    assert "Return to the terminal after the focused rerun." in wide_plain


def test_render_transcript_compacts_list_first_then_closing_text_on_narrow_terminal(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "- Tighten transcript preview ordering\n"
                "- Re-run focused pytest\n\n"
                "Return to the terminal after the focused rerun."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=35)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=35)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "list:" in narrow_plain
    assert "terminal" in narrow_plain
    assert "Return to the terminal after the focused rerun." in wide_plain


def test_render_transcript_preserves_followup_order_for_intro_plus_quote_then_code(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Patch walkthrough for the next turn.\n\n"
                "> Keep the first screen focused on the next action.\n"
                "> Trim repeated context before showing tool details.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=23)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert " - quote:" in narrow_plain
    assert "[code]" in narrow_plain
    assert "python code:" not in narrow_plain


def test_render_transcript_preserves_followup_order_for_intro_plus_table_then_code(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Patch walkthrough for the next turn.\n\n"
                "| Step | Owner | Status | Notes |\n"
                "| --- | --- | --- | --- |\n"
                "| transcript | codex | done | narrowed preview |\n"
                "| tty | codex | next | verify quote layout |\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=24)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert " - table:" in narrow_plain
    assert "[code]" in narrow_plain
    assert "python code:" not in narrow_plain


def test_render_transcript_compacts_code_block_first_with_quote_marker(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "> Keep the first screen focused on the next action.\n"
                "> Trim repeated context before showing tool details."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=25)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "python code:" in narrow_plain
    assert "build_turn_state" in narrow_plain
    assert "[quote]" in narrow_plain


def test_render_transcript_compacts_table_first_with_code_marker(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "| Step | Owner | Status | Notes |\n"
                "| --- | --- | --- | --- |\n"
                "| transcript | codex | done | narrowed preview |\n"
                "| tty | codex | next | verify quote layout |\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=26)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "table: Step | Owner | Status" in narrow_plain
    assert "[code]" in narrow_plain


def test_render_transcript_compacts_list_first_with_quote_marker(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "- Tighten transcript preview ordering\n"
                "- Re-run focused pytest\n\n"
                "> Keep the first screen focused on the next action.\n"
                "> Trim repeated context before showing tool details."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=27)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "list: Tighten" in narrow_plain
    assert "[quote]" in narrow_plain


def test_render_transcript_compacts_code_block_first_with_closing_text_preview(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "Keep verification focused on state anchors before broadening retrieval."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=28)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "python code:" in narrow_plain
    assert "build_turn_state" in narrow_plain
    assert "state anchors" in narrow_plain


def test_render_transcript_compacts_table_first_with_code_marker_and_closing_text_preview(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "| Step | Owner | Status | Notes |\n"
                "| --- | --- | --- | --- |\n"
                "| transcript | codex | done | narrowed preview |\n"
                "| tty | codex | next | verify quote layout |\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "Keep verification focused on state anchors before broadening retrieval."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=29)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "table: Step | Owner | Status" in narrow_plain
    assert "state anchors" in narrow_plain
    assert "[code]" in narrow_plain


def test_render_transcript_compacts_code_first_then_quote_then_closing_text_on_narrow_terminal(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "> Keep the first screen focused on the next action.\n"
                "> Trim repeated context before showing tool details.\n\n"
                "Return to the terminal after the focused rerun."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=30)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=31)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "python code:" in narrow_plain
    assert "build_turn_state" in narrow_plain
    assert "[quote]" in narrow_plain or "quote:" in narrow_plain
    assert "terminal" in narrow_plain
    assert "..." in narrow_plain
    assert "Return to the terminal after the focused rerun." in wide_plain


def test_render_transcript_compacts_quote_first_with_word_boundary_preview_on_narrow_terminal(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "> Keep the first screen focused on the next action.\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n\n"
                "Return to the terminal after the focused rerun."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=130)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "quote: Keep...next action." in narrow_plain
    assert "table: Step" in narrow_plain
    assert "terminal" in narrow_plain
    assert "Keep th..." not in narrow_plain


def test_render_transcript_compacts_code_first_with_identifier_tail_preview_on_narrow_terminal(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "```python\n"
                "def build_turn_state_from_checkpoint(state):\n"
                "    return state\n"
                "```\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n\n"
                "Return to the terminal after the focused rerun.\n\n"
                "> Keep the first screen focused on the next action."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=131)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "python code: build_turn...checkpoint" in narrow_plain
    assert "[table]" in narrow_plain
    assert "[quote]" in narrow_plain
    assert "terminal" not in narrow_plain
    assert "...eckpoint" not in narrow_plain


def test_render_transcript_compacts_table_first_then_list_then_closing_text_on_narrow_terminal(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n"
                "| followup | codex | next |\n\n"
                "- Re-run focused pytest\n"
                "- Capture the narrow preview\n\n"
                "Return to the terminal after the focused rerun."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=32)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=33)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert "table: Step | Owner | Status" in narrow_plain
    assert "list:" in narrow_plain
    assert "terminal" in narrow_plain
    assert "..." in narrow_plain
    assert "Return to the terminal after the focused rerun." in wide_plain


def test_render_transcript_prefers_trailing_action_text_after_quote_and_code_on_narrow_terminal(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Start with the focused rerun so the first signal is easy to compare.\n\n"
                "> Keep the first screen focused on the next action.\n\n"
                "Use the narrow terminal output as the baseline before changing ordering.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```\n\n"
                "Return to the terminal after the focused rerun."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=34)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "quote:" in narrow_plain
    assert "[code]" in narrow_plain or "python code:" in narrow_plain
    assert "terminal" in narrow_plain
    assert "changing ordering" not in narrow_plain


def test_render_transcript_keeps_quote_action_word_when_multiple_followup_markers_compact(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "> Keep the first screen focused on the next action.\n"
                "> Trim repeated context before showing tool details.\n\n"
                "Use the narrow terminal output as the baseline before changing ordering.\n\n"
                "- Re-run focused pytest\n"
                "- Capture the narrow preview\n\n"
                "Return to the terminal after the focused rerun.\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n"
                "| followup | codex | next |\n\n"
                "```python\n"
                "def build_turn_state_from_checkpoint(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=134)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "quote: ...action." in narrow_plain
    assert "terminal" in narrow_plain
    assert "[list]" in narrow_plain
    assert "[table]" in narrow_plain
    assert "[code]" in narrow_plain
    assert "...ction." not in narrow_plain


def test_render_transcript_keeps_quote_action_and_latest_markers_on_tighter_terminal(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "> Keep the first screen focused on the next action.\n\n"
                "The quote should stay readable while we compress the extra details.\n\n"
                "- Re-run focused pytest\n"
                "- Capture the narrow preview\n\n"
                "Return to the terminal after the focused rerun.\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n\n"
                "```python\n"
                "def build_turn_state_from_checkpoint(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (44, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=142)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "quote: ...action." in narrow_plain
    assert "terminal" in narrow_plain
    assert "[table]" in narrow_plain
    assert "[code]" in narrow_plain
    assert "t...al...st]" not in narrow_plain


def test_render_transcript_prefers_trailing_action_text_after_list_and_table_on_narrow_terminal(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "Tighten the first screen before widening the transcript again.\n\n"
                "- Re-run focused pytest\n"
                "- Capture the narrow preview\n\n"
                "Compare the summary before and after the code marker fallback.\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n"
                "| followup | codex | next |\n\n"
                "Return to the terminal after the focused rerun."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=35)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "list:" in narrow_plain
    assert "[table]" in narrow_plain or "table:" in narrow_plain
    assert "terminal" in narrow_plain
    assert "marker fallback" not in narrow_plain


def test_render_transcript_keeps_list_label_when_quote_closing_and_table_marker_compact(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "- Re-run focused pytest\n"
                "- Capture the narrow preview\n\n"
                "> Keep the first screen focused on the next action.\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n"
                "| preview | codex | next |\n\n"
                "Return to the terminal after the focused rerun."
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=36)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "list:" in narrow_plain
    assert "[quote]" in narrow_plain or "quote:" in narrow_plain
    assert "terminal" in narrow_plain
    assert "[table]" in narrow_plain


def test_render_transcript_keeps_quote_label_across_multiple_followup_markers(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "> Keep the first screen focused on the next action.\n\n"
                "Return to the terminal after the focused rerun.\n\n"
                "- Re-run focused pytest\n"
                "- Capture the narrow preview\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n"
                "| preview | codex | next |\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=37)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "quote:" in narrow_plain
    assert "terminal" in narrow_plain
    assert "[list]" in narrow_plain
    assert "[table]" in narrow_plain
    assert "[code]" in narrow_plain


def test_render_transcript_prefers_trailing_action_text_for_structure_first_with_multiple_plain_blocks(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "> Keep the first screen focused on the next action.\n\n"
                "The quote should stay visible before we compress the followup details.\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n\n"
                "Return to the terminal after the focused rerun.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=39)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "quote:" in narrow_plain
    assert "terminal" in narrow_plain
    assert "[table]" in narrow_plain
    assert "[code]" in narrow_plain
    assert "The q...tails." not in narrow_plain


def test_render_transcript_prefers_trailing_action_text_for_table_first_with_multiple_plain_blocks(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n\n"
                "The table should stay visible before we compress the followup details.\n\n"
                "> Keep the first screen focused on the next action.\n\n"
                "Return to the terminal after the focused rerun.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=40)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "table:" in narrow_plain
    assert "Step | ... | Status" in narrow_plain
    assert "terminal" in narrow_plain
    assert "[quote]" in narrow_plain
    assert "[code]" in narrow_plain
    assert "The t...tails." not in narrow_plain


def test_render_transcript_prefers_trailing_action_text_for_list_first_with_multiple_plain_blocks(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "- Re-run focused pytest\n"
                "- Capture the narrow preview\n\n"
                "The checklist should stay visible before we compress the followup details.\n\n"
                "> Keep the first screen focused on the next action.\n\n"
                "Return to the terminal after the focused rerun.\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=41)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "list:" in narrow_plain
    assert "terminal" in narrow_plain
    assert "[quote]" in narrow_plain
    assert "[table]" in narrow_plain
    assert "The c...tails." not in narrow_plain


def test_render_transcript_keeps_list_action_head_when_marker_budget_is_tight(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "- Re-run focused pytest\n"
                "- Capture the narrow preview\n\n"
                "The checklist should stay visible before we compress the followup details.\n\n"
                "> Keep the first screen focused on the next action.\n\n"
                "Return to the terminal after the focused rerun.\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (48, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=141)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "list: Re-run" in narrow_plain
    assert "...pytest" not in narrow_plain
    assert "terminal" in narrow_plain
    assert "[quote]" in narrow_plain
    assert "[table]" in narrow_plain


def test_render_transcript_keeps_table_column_shape_when_marker_budget_is_tight(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n\n"
                "The table should stay visible before we compress the followup details.\n\n"
                "> Keep the first screen focused on the next action.\n\n"
                "Return to the terminal after the focused rerun.\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (44, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=143)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "table: Step |...| Status" in narrow_plain
    assert "terminal" in narrow_plain
    assert "[code]" in narrow_plain
    assert "Ste...tatus" not in narrow_plain


def test_render_transcript_keeps_list_summary_with_quote_table_and_code_markers_compact(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "- Re-run focused pytest\n"
                "- Capture the narrow preview\n\n"
                "The checklist should stay visible before we compress the followup details.\n\n"
                "> Keep the first screen focused on the next action.\n\n"
                "Return to the terminal after the focused rerun.\n\n"
                "| Step | Owner | Status |\n"
                "| --- | --- | --- |\n"
                "| replay | codex | done |\n"
                "| preview | codex | next |\n\n"
                "```python\n"
                "def build_turn_state_from_checkpoint(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=42)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "list: Re-run pytest" in narrow_plain
    assert "terminal" in narrow_plain
    assert "[quote]" in narrow_plain
    assert "[table]" in narrow_plain
    assert "[code]" in narrow_plain
    assert "Re...est" not in narrow_plain


def test_render_transcript_compacts_plain_intro_before_structured_followups(
    monkeypatch,
) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="assistant",
            body=(
                "We should keep the terminal focused on the narrow replay while we tighten the summary.\n\n"
                "First trim the intro, then preserve the strongest structured signal.\n\n"
                "> Keep the first screen focused on the next action.\n\n"
                "- Re-run focused pytest\n"
                "- Capture the narrow preview\n\n"
                "```python\n"
                "def build_turn_state(state):\n"
                "    return state\n"
                "```"
            ),
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=38)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    assert "replay" in narrow_plain
    assert "quote:" in narrow_plain
    assert "[list]" in narrow_plain
    assert "[code]" in narrow_plain
    assert "We...." not in narrow_plain


def test_render_transcript_running_tool_preview_tracks_terminal_width(monkeypatch) -> None:
    entries = [
        TranscriptEntry(
            id=1,
            kind="tool",
            body="Inspecting src/minicode/agent_loop.py for orchestration flow\nsecond detail line\nthird detail line",
            toolName="read_file",
            status="running",
        )
    ]

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))
    narrow = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=7)
    narrow_plain = re.sub(r"\x1b\[[0-9;]*m", "", narrow)

    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (120, 20))
    wide = transcript_module.render_transcript(entries, scroll_offset=0, window_size=8, revision=7)
    wide_plain = re.sub(r"\x1b\[[0-9;]*m", "", wide)

    assert ".py" in narrow_plain
    assert "orchestration flo" in narrow_plain
    assert "..." in narrow_plain
    assert "second detail line" not in narrow_plain
    assert "second detail line" in wide_plain


def test_render_transcript_narrow_tool_preview_preserves_filename(monkeypatch) -> None:
    monkeypatch.setattr(transcript_module, "_cached_terminal_size", lambda: (56, 20))

    rendered = transcript_module.render_transcript(
        [
            TranscriptEntry(
                id=1,
                kind="tool",
                body=r"Reading path=C:\Users\question\projects\minicode\src\very_long_file_name.py for context before patching",
                toolName="read_file",
                status="running",
            )
        ],
        scroll_offset=0,
        window_size=8,
        revision=8,
    )
    plain = re.sub(r"\x1b\[[0-9;]*m", "", rendered)

    assert ".py for context before patching" in plain
    assert r"C:\Users\question\projects\minicode\src\very_long_file_name.py" not in plain
    assert "..." in plain


def test_error_tool_entry_stays_expanded_for_visibility() -> None:
    entry = TranscriptEntry(id=1, kind="tool", body="boom", toolName="run_command", status="running")
    _apply_tool_result_visual_state(entry, "run_command", "boom", is_error=True)

    assert entry.status == "error"
    assert entry.collapsed is False
    assert entry.collapsedSummary is None


def test_success_tool_entry_collapses_to_summary() -> None:
    entry = TranscriptEntry(id=1, kind="tool", body="running", toolName="read_file", status="running")
    _apply_tool_result_visual_state(entry, "read_file", "FILE: README.md\nhello", is_error=False)

    assert entry.status == "success"
    assert entry.collapsed is True
    assert entry.collapsedSummary == "FILE: README.md"
    assert entry.collapsePhase == 3


def test_empty_tty_return_does_not_start_input_handler(tmp_path) -> None:
    calls = []
    state = ScreenState(input="   ", cursor_offset=3)
    args = TtyAppArgs(
        runtime=None,
        tools=None,
        model=None,
        messages=[],
        cwd=str(tmp_path),
        permissions=PermissionManager(str(tmp_path)),
    )

    def rerender() -> None:
        calls.append("rerender")

    def handle_input(*_args, **_kwargs):
        calls.append("handle_input")
        return False

    _handle_event(
        args,
        state,
        KeyEvent(name="return", ctrl=False, meta=False),
        rerender,
        __import__("threading").Event(),
        {},
        handle_input,
    )

    assert "handle_input" not in calls
    assert state.input == ""


def test_tty_input_passes_and_persists_context_manager(tmp_path, monkeypatch) -> None:
    captured: dict = {}
    saved: list[ContextManager] = []
    context_manager = ContextManager(messages=[], context_window=1000)

    def fake_run_agent_turn(**kwargs):
        captured.update(kwargs)
        manager = kwargs["context_manager"]
        manager.messages = list(kwargs["messages"])
        return [*kwargs["messages"], {"role": "assistant", "content": "done"}]

    monkeypatch.setattr(input_handler_module, "run_agent_turn", fake_run_agent_turn)
    monkeypatch.setattr(input_handler_module, "save_context_state", saved.append, raising=False)

    state = ScreenState(input="Please inspect context", cursor_offset=22)
    args = TtyAppArgs(
        runtime={"model": "default"},
        tools=ToolRegistry([]),
        model=object(),
        messages=[{"role": "system", "content": "sys"}],
        cwd=str(tmp_path),
        permissions=PermissionManager(str(tmp_path)),
        context_manager=context_manager,
    )

    assert input_handler_module._handle_input(args, state, lambda: None) is False
    state.agent_thread.join(timeout=5)

    assert captured["context_manager"] is context_manager
    assert saved == [context_manager]
    assert state.agent_result["messages"][-1] == {"role": "assistant", "content": "done"}


def test_tool_entry_elapsed_is_tracked_per_entry() -> None:
    pending_tool_started_at: dict[int, float] = {}

    input_handler_module._record_tool_entry_start(
        pending_tool_started_at,
        11,
        started_at=100.0,
    )
    input_handler_module._record_tool_entry_start(
        pending_tool_started_at,
        22,
        started_at=103.0,
    )

    first_elapsed = input_handler_module._consume_tool_entry_elapsed(
        pending_tool_started_at,
        11,
        finished_at=104.4,
    )
    second_elapsed = input_handler_module._consume_tool_entry_elapsed(
        pending_tool_started_at,
        22,
        finished_at=104.4,
    )

    assert first_elapsed == " (4.4s)"
    assert second_elapsed == " (1.4s)"
    assert pending_tool_started_at == {}


def test_build_tool_display_output_uses_ascii_recovery_hint() -> None:
    rendered = input_handler_module._build_tool_display_output(
        "No such file or directory: missing.txt",
        True,
    )

    assert rendered.startswith("ERROR: No such file or directory: missing.txt")
    assert "Hint: file not found. Try /ls to inspect available paths." in rendered


def test_tty_input_keeps_progress_tools_and_await_user_in_terminal_order(tmp_path, monkeypatch) -> None:
    saved: list[ContextManager] = []

    def fake_run_agent_turn(**kwargs):
        kwargs["on_progress_message"]("Scanning project")
        kwargs["on_tool_start"]("read_file", {"path": "a.py"})
        kwargs["on_tool_start"]("list_files", {"path": "."})
        kwargs["on_tool_result"]("read_file", "FILE: a.py\nprint('hi')", False)
        kwargs["on_tool_result"]("list_files", "a.py\nb.py", False)
        kwargs["on_assistant_message"]("Need approval")
        return [*kwargs["messages"], {"role": "assistant", "content": "Need approval"}]

    monkeypatch.setattr(input_handler_module, "run_agent_turn", fake_run_agent_turn)
    monkeypatch.setattr(input_handler_module, "save_context_state", saved.append, raising=False)

    state = ScreenState(input="Inspect repo", cursor_offset=11)
    context_manager = ContextManager(messages=[], context_window=1000)
    args = TtyAppArgs(
        runtime={"model": "default"},
        tools=ToolRegistry([]),
        model=object(),
        messages=[{"role": "system", "content": "sys"}],
        cwd=str(tmp_path),
        permissions=PermissionManager(str(tmp_path)),
        context_manager=context_manager,
    )

    assert input_handler_module._handle_input(args, state, lambda: None) is False
    state.agent_thread.join(timeout=5)

    transcript_kinds = [entry.kind for entry in state.transcript]
    assert transcript_kinds == ["user", "progress", "tool", "tool", "assistant"]
    assert state.transcript[1].body == "Scanning project"
    assert state.transcript[2].toolName == "read_file"
    assert state.transcript[2].status == "success"
    assert state.transcript[3].toolName == "list_files"
    assert state.transcript[3].status == "success"
    assert state.transcript[4].body == "Need approval"
    assert all(entry.status != "running" for entry in state.transcript if entry.kind == "tool")
    assert state.status is None
    assert saved == [context_manager]


def test_tty_input_replays_concurrent_await_user_without_dangling_tool_entries(tmp_path, monkeypatch) -> None:
    def fake_run_agent_turn(**kwargs):
        kwargs["on_tool_start"]("ask_user", {"question": "Approve?"})
        kwargs["on_tool_start"]("list_files", {"path": "."})
        kwargs["on_tool_result"]("ask_user", "Need approval", False)
        kwargs["on_tool_result"]("list_files", "a.py\nb.py", False)
        kwargs["on_assistant_message"]("Need approval")
        return [*kwargs["messages"], {"role": "assistant", "content": "Need approval"}]

    monkeypatch.setattr(input_handler_module, "run_agent_turn", fake_run_agent_turn)
    state = ScreenState(input="Inspect repo", cursor_offset=11)
    args = TtyAppArgs(
        runtime={"model": "default"},
        tools=ToolRegistry([]),
        model=object(),
        messages=[{"role": "system", "content": "sys"}],
        cwd=str(tmp_path),
        permissions=PermissionManager(str(tmp_path)),
        context_manager=ContextManager(messages=[], context_window=1000),
    )

    assert input_handler_module._handle_input(args, state, lambda: None) is False
    state.agent_thread.join(timeout=5)

    transcript_kinds = [entry.kind for entry in state.transcript]
    assert transcript_kinds == ["user", "tool", "tool", "assistant"]
    assert [entry.toolName for entry in state.transcript if entry.kind == "tool"] == [
        "ask_user",
        "list_files",
    ]
    assert all(entry.status == "success" for entry in state.transcript if entry.kind == "tool")
    assert state.transcript[-1].body == "Need approval"
    assert state.status is None
    assert state.active_tool is None
    assert all("running" not in entry.body.lower() for entry in state.transcript if entry.kind == "tool")


def test_tty_input_tracks_concurrent_tool_status_without_flicker(tmp_path, monkeypatch) -> None:
    status_snapshots: list[tuple[str | None, str | None]] = []

    def fake_run_agent_turn(**kwargs):
        kwargs["on_tool_start"]("ask_user", {"question": "Approve?"})
        kwargs["on_tool_start"]("list_files", {"path": "."})
        kwargs["on_tool_result"]("ask_user", "Need approval", False)
        kwargs["on_tool_result"]("list_files", "a.py\nb.py", False)
        return [*kwargs["messages"], {"role": "assistant", "content": "done"}]

    monkeypatch.setattr(input_handler_module, "run_agent_turn", fake_run_agent_turn)
    monkeypatch.setattr(input_handler_module, "save_context_state", lambda *_args, **_kwargs: None, raising=False)

    state = ScreenState(input="Inspect repo", cursor_offset=11)
    args = TtyAppArgs(
        runtime={"model": "default"},
        tools=ToolRegistry([]),
        model=object(),
        messages=[{"role": "system", "content": "sys"}],
        cwd=str(tmp_path),
        permissions=PermissionManager(str(tmp_path)),
        context_manager=ContextManager(messages=[], context_window=1000),
    )

    def capture_status() -> None:
        status_snapshots.append((state.status, state.active_tool))

    assert input_handler_module._handle_input(args, state, capture_status) is False
    state.agent_thread.join(timeout=5)

    assert ("Running ask_user...", "ask_user") in status_snapshots
    assert ("2 tool(s) running...", "2 tool(s)") in status_snapshots
    assert ("Running list_files...", "list_files") in status_snapshots
    assert state.status is None
    assert state.active_tool is None
