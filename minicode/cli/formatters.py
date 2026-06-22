"""Slash-command and cybernetics display formatting."""
from __future__ import annotations

def format_slash_commands() -> str:
    lines = [
        "╔══════════════════════════════════════════════════════════╗",
        "║  📚 Available Commands                                  ║",
        "╠══════════════════════════════════════════════════════════╣",
    ]

    command_groups = {
        "🔧 Core Commands": [
            ("/help", "Show this help message"),
            ("/exit", "Exit mini-code"),
            ("/clear", "Clear the current transcript view"),
            ("/history", "Show recent prompt history"),
        ],
        "🛠️ Tool Commands": [
            ("/tools", "List all available tools"),
            ("/skills", "List discovered SKILL.md workflows"),
            ("/mcp", "Show MCP servers and connection state"),
            ("/cmd", "Run development commands directly"),
        ],
        "📊 Status & Info": [
            ("/status", "Show application state summary"),
            ("/model", "Show or change current model"),
            ("/user", "Show or manage user profile"),
            ("/cost", "Show API cost and usage report"),
            ("/context", "Show context window usage"),
            ("/cybernetics", "Show control-system status"),
            ("/tasks", "Show current task list"),
            ("/memory", "Show memory system status"),
        ],
        "✏️ File Operations": [
            ("/ls [path]", "List files in directory"),
            ("/grep <pattern>", "Search text in files"),
            ("/read <path>", "Read a file directly"),
            ("/write <path>", "Write content to file"),
            ("/edit <path>", "Edit file by exact replacement"),
            ("/patch <path>", "Apply multiple replacements in one go"),
            ("/modify <path>", "Replace file with reviewable diff"),
        ],
        "💾 Session Management": [
            ("/session", "Inspect current session state"),
            ("/session <id>", "Inspect saved session or latest"),
            ("/session-replay", "Replay active session timeline"),
            ("/session-replay <id>", "Replay saved session timeline"),
            ("/sessions", "List saved sessions for workspace"),
            ("/instructions", "Inspect active instruction layering"),
            ("/hooks", "Inspect hook telemetry and failures"),
            ("/delegation", "Inspect background task capacity"),
            ("/extensions", "Inspect local extension manifests"),
            ("/extension-inspect <name>", "Inspect one extension in detail"),
            ("/extension-enable <name>", "Enable a local extension"),
            ("/extension-disable <name>", "Disable a local extension"),
            ("/readiness", "Inspect provider/runtime readiness"),
            ("/checkpoints", "List active session checkpoints"),
            ("/checkpoints <id>", "List saved session checkpoints"),
            ("/rewind-preview [arg]", "Preview active session rewind plan"),
            ("/rewind [arg]", "Rewind active session file edits"),
            ("/session-rewind-preview <id> [arg]", "Preview saved session rewind plan"),
            ("/session-rewind <id> [arg]", "Rewind saved session file edits"),
            ("/transcript-save <path>", "Save transcript to text file"),
            ("/retry", "Retry the last prompt"),
            ("/permissions", "Show permission storage path"),
            ("/config-paths", "Show settings file paths"),
        ],
    }

    for group_name, commands in command_groups.items():
        lines.append(f"║  {group_name:<54}║")
        for cmd, desc in commands:
            cmd_display = f"    {cmd}"
            lines.append(f"║  {cmd_display:<20} {desc:<33} ║")
        lines.append("╠══════════════════════════════════════════════════════════╣")

    lines.extend([
        "║  💡 Tips:                                              ║",
        "║  - Use Tab to autocomplete commands                    ║",
        "║  - Prefix with / to access any command                 ║",
        "║  - Type naturally - I'll understand Chinese & English  ║",
        "╚══════════════════════════════════════════════════════════╝",
    ])

    return "\n".join(lines)

def format_cybernetics_status() -> str:
    """Format cybernetic controller inventory and persisted state hints."""
    from minicode.control.supervisor import CyberneticSupervisor, load_supervisor_report
    from minicode.context.manager import load_context_state

    controllers = [
        ("ContextCyberneticsOrchestrator", "context pressure PID + prediction"),
        ("CostControlLoop", "budget PID for tool-result persistence"),
        ("VerificationController", "risk-adaptive verification planning"),
        ("ToolSchedulerController", "error/latency-aware concurrency control"),
        ("MemoryInjectionController", "context-aware memory injection"),
        ("ModelSelectionController", "cost/latency/failure-aware model routing"),
        ("ProgressController", "health/stall task progress control"),
        ("CyberneticSupervisor", "global health and risk aggregation"),
    ]

    ctx = load_context_state()
    snapshots = []
    if ctx:
        stats = ctx.get_stats()
        usage = stats.usage_percentage / 100.0
        snapshots.append(CyberneticSupervisor().snapshot_from_context({
            "sensor": {"current_usage": usage},
            "predictor": {"urgency": 0.0},
        }))
    persisted_report = load_supervisor_report()
    report = persisted_report or CyberneticSupervisor().report(snapshots)

    lines = [
        "Cybernetic Control System",
        "=" * 50,
        f"overall_health: {report.overall_health:.2f}",
        f"risk_level: {report.risk_level.value}",
        f"source: {'latest agent-loop report' if persisted_report else 'current persisted context'}",
        "",
        "Controllers:",
    ]
    for name, desc in controllers:
        lines.append(f"  - {name}: {desc}")
    lines.extend([
        "",
        "Runtime aggregation:",
        "  - pipeline outputs: progress_control + verification_plan + cybernetic_supervisor",
        "  - agent loop logs: context + cost + tool scheduling supervisor report",
    ])
    if report.recommended_actions:
        lines.append("")
        lines.append("Current actions:")
        for action in report.recommended_actions[:5]:
            lines.append(f"  - {action}")
    return "\n".join(lines)

__all__ = ["format_slash_commands", "format_cybernetics_status"]
