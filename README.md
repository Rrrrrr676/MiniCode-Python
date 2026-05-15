# MiniCode Python

> Python implementation of the [MiniCode](https://github.com/LiuMengxuan04/MiniCode) ecosystem.
>
> **AI 编程智能体 · 钱学森工程控制论架构 · DDD 领域驱动设计**

## MiniCode Ecosystem

- Main repository: [LiuMengxuan04/MiniCode](https://github.com/LiuMengxuan04/MiniCode)
- Python version: [QUSETIONS/MiniCode-Python](https://github.com/QUSETIONS/MiniCode-Python)
- Rust version: [harkerhand/MiniCode-rs](https://github.com/harkerhand/MiniCode-rs)
- Submodule sync guide: [docs/SUBMODULE_SYNC.md](docs/SUBMODULE_SYNC.md)

## Architecture

MiniCode Python is built on **Engineering Cybernetics** (钱学森工程控制论) + **DDD** (Domain-Driven Design), forming a complete closed-loop intelligent agent system:

### Control Theory Closed Loop

```
[Feedforward] IntentParser → FeedforwardController → PreemptiveConfig
     ↓
[Execution]  TaskObject → PipelineEngine → AgentLoop → Tools
     ↓
[Monitoring] StabilityMonitor → MetricSnapshot → StabilityReport
     ↓
[Feedback]  FeedbackController → ControlSignal → System Adjustment
     ↑                               ↓
     └──── SystemState ◄─── Sensors ◄─── Agent Metrics ────┘

[Positive Feedback] Pattern Tracking → Skill Update → Memory Persistence
[Negative Feedback] Error Detection → PID Adjustment → Stability Recovery
```

### Three Core Controllers

| Controller | Cybernetics Principle | Key Features |
|-----------|----------------------|-------------|
| **Feedback Controller** | Negative feedback correction + Positive feedback reinforcement + PID adaptive tuning | Auto-concurrency reduction, timeout adjustment, force compaction, pattern reinforcement |
| **Feedforward Controller** | Preemptive optimization, open-loop control | Intent-based pre-configuration, risk pre-assessment, complexity/entity-aware tuning |
| **Stability Monitor** | Multi-dimensional health scoring + Real-time anomaly detection | Health grading (healthy/degraded/warning/critical), robustness assessment, oscillation detection |

### Work Chain

```
User Input → Intent Parser → Task Object → Pipeline Plan → Execution → Result
              (14 intent types)   (stable)     (DAG steps)    (tools)    (audit)
```

### DDD Domain Boundaries

| Domain | Module | Role |
|--------|--------|------|
| Intent Parsing | `intent_parser.py` | Sensor — perceives user input, extracts feature signals |
| Task Domain | `task_object.py` | Setpoint — defines target state and constraints |
| Memory Domain | `memory.py` | Historical state storage — cross-session knowledge persistence |
| Context Domain | `layered_context.py` | State observer — maintains current system state |
| Capability Domain | `capability_registry.py` | Actuator collection — callable control methods |
| Execution Domain | `agent_loop.py` | Controller — run_agent_turn closed-loop control |
| Decision Audit | `decision_audit.py` | Logger — full-state traceability |
| Feedback Control | `feedback_controller.py` | Regulator — negative correction + positive reinforcement |
| Feedforward Control | `feedforward_controller.py` | Predictor — task prediction + risk prediction |
| Stability Monitor | `stability_monitor.py` | Observer — health scoring + anomaly detection |

## What This Repository Provides

MiniCode Python is a terminal AI coding assistant implemented in Python, focused on:

- **Terminal-first** coding workflows
- **Tool calling** and agent loop execution
- **TUI-based** interactive experience
- **Session persistence** and recovery
- **Permission-gated** local execution
- **MCP integration**
- **Cybernetics-driven** self-regulation
- **DDD-based** modular architecture
- **Pipeline orchestration** for complex tasks
- **Decision audit** for full traceability
- **Layered context** with token budget management
- **Working memory** protection with priority-based eviction

## Key Features

### Engineering Cybernetics Integration
- **Negative feedback**: Auto-corrects when system stability drops (reduces concurrency, shortens timeouts, forces context compaction)
- **Positive feedback**: Reinforces successful patterns (skill updates, memory persistence)
- **PID adaptive tuning**: Gradual parameter optimization for smooth transitions
- **Feedforward control**: Pre-emptively configures based on task intent, complexity, and entities
- **Risk pre-assessment**: Identifies permission, resource, timeout, and complexity risks before execution
- **Stability monitoring**: Real-time health scoring with 6-dimensional metrics (error rate, context usage, latency, CPU, memory, throughput)

### DDD Architecture
- Clear bounded contexts with single responsibility
- Entity/Value Object/Aggregate Root patterns
- Repository pattern for memory and capability management
- Domain events for decoupled cross-domain communication

### Work Chain Deepening
- **Intent Parser**: 14 intent types, entity extraction (files/functions/classes/languages), complexity estimation
- **Task Object**: Stable task representation with constraints, expected outputs, state machine
- **Pipeline Engine**: DAG-based step planning with dependency resolution and retry logic
- **Capability Registry**: Self-describing tools with domain/scope classification and dependency tracking

### Memory System
- **3-layer physical storage**: USER (cross-project) → PROJECT (shared) → LOCAL (project-specific)
- **BM25 search** with CJK support and 80+ programming term expansions
- **Working memory protection** with importance-based eviction
- **Batch save** with dirty tracking and 5s interval flush
- **Index structures** for O(1) lookup (ID, tag, category)

## Project Positioning

This repository is the Python version of MiniCode, maintained as a language-specific subproject in the broader MiniCode ecosystem.

If you came here from the main MiniCode repository, the important thing to know is:

- the main repository syncs a submodule commit
- it does not automatically mirror the full live state of this repository
- so the submodule pointer in the main repo may lag behind the latest changes here

In other words, what gets synced upstream is a specific commit, not the whole repository state. If the main repo has not updated its submodule pointer yet, the content shown there can be older than what you see here.

For the exact maintainer workflow, see [docs/SUBMODULE_SYNC.md](docs/SUBMODULE_SYNC.md).

## Related Repositories

| Repository | Role |
| --- | --- |
| [MiniCode](https://github.com/LiuMengxuan04/MiniCode) | Main project entry and ecosystem hub |
| [MiniCode-Python](https://github.com/QUSETIONS/MiniCode-Python) | Python implementation |
| [MiniCode-rs](https://github.com/harkerhand/MiniCode-rs) | Rust implementation |

## Current Status

This repository is an actively developed Python implementation, not just a mirror of the main repository.

It includes ongoing work in areas such as:

- Python-side feature parity with the main MiniCode experience
- TUI architecture cleanup
- Transcript and rendering performance improvements
- MCP and tool execution improvements
- Session, context, and memory handling
- **Engineering Cybernetics integration** (feedback/feedforward/stability)
- **DDD architecture** (domain-driven design with bounded contexts)
- **Work chain deepening** (Intent → Task → Pipeline → Execution → Audit)
- **Performance optimization** (BM25 indexing, batch save, lazy cache invalidation)
- **Security hardening** (SSRF protection, atomic writes, timeout control)

## Quick Start

```bash
git clone https://github.com/QUSETIONS/MiniCode-Python.git
cd MiniCode-Python
python -m minicode.main --install
```

Run directly:

```bash
python -m minicode.main
```

## Tests

### Cybernetics Integration Tests

Verify the Engineering Cybernetics controllers:

```bash
python tests/test_cybernetics_integration.py
```

All 7 tests verify the closed-loop architecture:
1. **Negative Feedback** — auto-corrects instability (concurrency reduction, timeout adjustment)
2. **Positive Feedback** — reinforces successful patterns (skill update, memory persistence)
3. **PID Adaptive Tuning** — gradual parameter optimization
4. **Feedforward Pre-configuration** — intent-based preemptive setup
5. **Risk Pre-assessment** — identifies permission/resource/complexity risks
6. **Stability Monitoring** — multi-dimensional health scoring
7. **Full Integration** — feedforward → execution → monitoring → feedback closed loop

### Unit Tests

```bash
pytest
```

## Configuration

Configure your model in `~/.mini-code/settings.json`:

```json
{
  "model": "claude-sonnet-4-20250514",
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
    "ANTHROPIC_AUTH_TOKEN": "your-token-here"
  }
}
```

## Development

Install dev dependencies and run tests:

```bash
pip install -e ".[dev]"
pytest
```

Mock mode:

```bash
MINI_CODE_MODEL_MODE=mock python -m minicode.main
```

## Sync Note For Main Repository Maintainers

If this repository is consumed as a submodule from the main MiniCode repository:

1. update the submodule pointer in the main repository
2. commit that submodule pointer update upstream
3. do not assume new commits here are automatically reflected there

This distinction matters for README visibility, feature status, and release communication.

## Acknowledgments

- MiniCode main project: [LiuMengxuan04/MiniCode](https://github.com/LiuMengxuan04/MiniCode)
- Rust implementation: [harkerhand/MiniCode-rs](https://github.com/harkerhand/MiniCode-rs)
- Engineering Cybernetics: 钱学森《工程控制论》(Engineering Cybernetics, 1954)
