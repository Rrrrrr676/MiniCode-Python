"""Guard the intentionally small public surface of the ``minicode`` package."""

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

def test_root_python_files_match_allowlist() -> None:
    actual = {path.name for path in PACKAGE_ROOT.glob("*.py")}
    assert actual == ROOT_PYTHON_ALLOWLIST
