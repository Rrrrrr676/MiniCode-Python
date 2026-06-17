from __future__ import annotations

import importlib
import json
import subprocess
import sys
import threading
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def test_console_script_entry_points_import() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    failures = []
    for name, target in pyproject["project"]["scripts"].items():
        module_name, _, attr_name = target.partition(":")
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: cannot import {module_name}: {exc}")
            continue
        if not hasattr(module, attr_name):
            failures.append(f"{name}: {module_name}.{attr_name} does not exist")

    assert failures == []


def test_legacy_root_smoke_scripts_are_not_pytest_collected() -> None:
    import conftest

    root_smoke_scripts = {
        path.name
        for pattern in ("test_*.py", "*_test.py")
        for path in ROOT.glob(pattern)
    }

    # After cleanup: root smoke scripts were migrated to tests/ or deleted.
    # If any remain, they must be excluded from pytest collection.
    if root_smoke_scripts:
        assert root_smoke_scripts.issubset(set(conftest.collect_ignore))
    assert "benchmarks/*.py" in conftest.collect_ignore_glob


def test_ci_workflow_runs_release_quality_gates() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"

    assert workflow.exists()
    content = workflow.read_text(encoding="utf-8")
    assert "python -m compileall -q minicode tests" in content
    assert "python -m pytest -q" in content
    assert "tests/test_packaging.py" in content
