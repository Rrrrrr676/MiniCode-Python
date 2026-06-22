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
LEGACY_ROOT_MODULES = {
    "adaptive_pid_tuner", "agent_intelligence", "agent_metrics", "agent_reflection",
    "agent_router", "anthropic_adapter", "api_retry", "auto_mode", "background_tasks",
    "capability_registry", "circuit_breaker", "cli_commands", "context_compactor",
    "context_cybernetics", "context_manager", "cost_control", "cost_tracker",
    "cybernetic_ablation", "cybernetic_orchestrator", "cybernetic_supervisor",
    "decision_audit", "decoupling_controller", "domain_classifier",
    "feedback_controller", "feedforward_controller", "file_review", "history", "hooks",
    "install", "intent_parser", "layered_context", "local_tool_shortcuts",
    "logging_config", "manage_cli", "mcp", "memory_curator_agent", "memory_injector",
    "memory_pipeline", "memory_reranker", "micro_compact", "mock_model",
    "model_registry", "model_switcher", "openai_adapter", "permissions",
    "pipeline_engine", "predictive_controller", "product_surfaces", "progress_controller",
    "prompt", "prompt_pipeline", "release_readiness", "runtime_profile_eval",
    "runtime_profiles", "self_healing_engine", "skills", "smart_router",
    "stability_monitor", "state", "state_observer", "task_graph", "task_object",
    "task_tracker", "timeline_memory", "turn_kernel", "types", "user_profile",
    "vector_memory", "verification_controller", "working_memory", "workspace",
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


def test_runtime_never_imports_tui_or_web() -> None:
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


def test_internal_modules_do_not_import_legacy_root_facades() -> None:
    violations = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        for imported in _imports(path):
            parts = imported.split(".")
            if len(parts) == 2 and parts[0] == "minicode" and parts[1] in LEGACY_ROOT_MODULES:
                violations.append(f"{path.relative_to(ROOT)} -> {imported}")
    assert violations == []


def test_cross_package_imports_do_not_use_private_names() -> None:
    violations = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(PACKAGE_ROOT)
        source = relative.parts[0] if len(relative.parts) > 1 else None
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            parts = node.module.split(".")
            target = parts[1] if len(parts) >= 2 and parts[0] == "minicode" else None
            if source and target and target != source:
                for alias in node.names:
                    if alias.name.startswith("_"):
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} -> "
                            f"{node.module}.{alias.name}"
                        )
    assert violations == []


def test_required_legacy_public_imports_still_work() -> None:
    from minicode.agent_loop import run_agent_turn
    from minicode.config import load_runtime_config
    from minicode.memory import MemoryManager
    from minicode.session import SessionData

    assert callable(run_agent_turn)
    assert callable(load_runtime_config)
    assert MemoryManager.__name__ == "MemoryManager"
    assert SessionData.__name__ == "SessionData"
