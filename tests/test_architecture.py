"""Executable dependency rules for the restructured Python package."""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = ROOT / "minicode"
LAYERED_PACKAGES = {
    "core",
    "config",
    "providers",
    "context",
    "memory",
    "persistence",
    "safety",
    "integrations",
    "observability",
    "control",
    "runtime",
    "cli",
    "tui",
    "web",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _package_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(PACKAGE_ROOT)
        source = relative.parts[0] if len(relative.parts) > 1 else None
        if source not in LAYERED_PACKAGES:
            continue
        graph[source]
        for imported in _imports(path):
            parts = imported.split(".")
            if len(parts) >= 2 and parts[0] == "minicode" and parts[1] in LAYERED_PACKAGES:
                target = parts[1]
                if target != source:
                    graph[source].add(target)
    return graph


def _cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()

    def visit(node: str, path: tuple[str, ...]) -> None:
        if node in path:
            cycle = path[path.index(node) :]
            rotations = [cycle[index:] + cycle[:index] for index in range(len(cycle))]
            found.add(min(rotations))
            return
        for target in graph.get(node, set()):
            visit(target, path + (node,))

    for node in graph:
        visit(node, ())
    return sorted(found)


def test_layered_packages_have_no_import_cycles() -> None:
    assert _cycles(_package_graph()) == []


def test_core_depends_only_on_standard_library() -> None:
    violations = []
    for path in (PACKAGE_ROOT / "core").rglob("*.py"):
        for imported in _imports(path):
            if (
                imported == "minicode"
                or imported.startswith("minicode.")
                and not imported.startswith("minicode.core")
            ):
                violations.append(f"{path.relative_to(ROOT)} -> {imported}")
    assert violations == []


def test_runtime_never_imports_product_surfaces() -> None:
    forbidden = ("minicode.tui", "minicode.web")
    violations = []
    for path in (PACKAGE_ROOT / "runtime").rglob("*.py"):
        for imported in _imports(path):
            if imported.startswith(forbidden):
                violations.append(f"{path.relative_to(ROOT)} -> {imported}")
    assert violations == []


def test_known_config_provider_context_cycle_is_absent() -> None:
    config_imports = _imports(PACKAGE_ROOT / "config" / "__init__.py")
    adapter_imports = _imports(PACKAGE_ROOT / "providers" / "openai.py")
    assert "minicode.providers.registry" not in config_imports
    assert "minicode.context.manager" not in adapter_imports


def test_legacy_core_imports_are_identity_preserving() -> None:
    from minicode.core.state import AppState as CoreAppState
    from minicode.core.types import AgentStep as CoreAgentStep
    from minicode.core.workspace import resolve_tool_path as core_resolve_tool_path
    from minicode.state import AppState
    from minicode.types import AgentStep
    from minicode.workspace import resolve_tool_path

    assert AppState is CoreAppState
    assert AgentStep is CoreAgentStep
    assert resolve_tool_path is core_resolve_tool_path
