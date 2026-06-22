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
    "adaptive_pid_tuner.py",
    "agent_intelligence.py",
    "agent_reflection.py",
    "agent_router.py",
    "background_tasks.py",
    "capability_registry.py",
    "circuit_breaker.py",
    "cli_commands.py",
    "context_compactor.py",
    "context_cybernetics.py",
    "context_manager.py",
    "cost_control.py",
    "cybernetic_ablation.py",
    "cybernetic_orchestrator.py",
    "cybernetic_supervisor.py",
    "decoupling_controller.py",
    "domain_classifier.py",
    "feedback_controller.py",
    "feedforward_controller.py",
    "history.py",
    "hooks.py",
    "install.py",
    "intent_parser.py",
    "layered_context.py",
    "local_tool_shortcuts.py",
    "manage_cli.py",
    "mcp.py",
    "memory_curator_agent.py",
    "memory_injector.py",
    "memory_pipeline.py",
    "memory_reranker.py",
    "micro_compact.py",
    "pipeline_engine.py",
    "predictive_controller.py",
    "product_surfaces.py",
    "progress_controller.py",
    "prompt.py",
    "prompt_pipeline.py",
    "release_readiness.py",
    "runtime_profile_eval.py",
    "runtime_profiles.py",
    "self_healing_engine.py",
    "skills.py",
    "smart_router.py",
    "stability_monitor.py",
    "state.py",
    "state_observer.py",
    "task_graph.py",
    "task_object.py",
    "task_tracker.py",
    "timeline_memory.py",
    "turn_kernel.py",
    "types.py",
    "user_profile.py",
    "vector_memory.py",
    "verification_controller.py",
    "working_memory.py",
    "workspace.py",
}


def test_root_python_files_match_migration_allowlist() -> None:
    actual = {path.name for path in PACKAGE_ROOT.glob("*.py")}
    assert actual == ROOT_PYTHON_ALLOWLIST | LEGACY_ROOT_FACADES
