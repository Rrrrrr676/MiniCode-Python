"""Guard the intentionally small public surface of the ``minicode`` package.

During the facade-removal migration ``LEGACY_ROOT_FACADES`` is an explicit,
shrinking inventory.  The final migration removes that set entirely.
"""

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "minicode"

ROOT_PYTHON_ALLOWLIST = {
    "__init__.py",
    "agent_loop.py",
    "headless.py",
    "main.py",
    "session.py",
    "tooling.py",
    "tty_app.py",
}

LEGACY_ROOT_FACADES = {
    "background_tasks.py",
    "cli_commands.py",
    "domain_classifier.py",
    "history.py",
    "hooks.py",
    "install.py",
    "local_tool_shortcuts.py",
    "manage_cli.py",
    "mcp.py",
    "memory_curator_agent.py",
    "memory_injector.py",
    "memory_pipeline.py",
    "memory_reranker.py",
    "skills.py",
    "state.py",
    "timeline_memory.py",
    "types.py",
    "user_profile.py",
    "vector_memory.py",
    "workspace.py",
}


def test_root_python_files_match_migration_allowlist() -> None:
    actual = {path.name for path in PACKAGE_ROOT.glob("*.py")}
    assert actual == ROOT_PYTHON_ALLOWLIST | LEGACY_ROOT_FACADES
