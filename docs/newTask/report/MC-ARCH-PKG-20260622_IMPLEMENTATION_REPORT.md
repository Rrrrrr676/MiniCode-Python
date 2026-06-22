# MC-ARCH-PKG-20260622 实现与完成度报告

| 项目 | 结果 |
|---|---|
| 任务 | Python Runtime 包分类、依赖治理与大模块安全拆分 |
| 日期 | 2026-06-22 |
| 当前完成度 | **84%（未达到任务书 Definition of Done，不标记全部完成）** |
| 行为回归 | Python 1180 passed；前端 28 passed；构建、wheel、三个入口通过 |
| P0/P1 回归 | 未发现 |
| 主要未完成项 | Timeline/Memory/Session/Compaction/Config/CLI 仍需继续做物理职责拆分 |

## 1. 结论

本轮完成了目标 package 建立、已知循环依赖治理、架构测试、73 个旧根路径兼容门面、Agent Runtime 真拆分、Memory package 转换、Session/Context 兼容迁移、全量回归和隔离 wheel 验收。

但任务书明确要求的多个超大模块尚未全部从“集中实现 + 分层 API”演进为“物理职责拆分”。因此本报告不把目录归类等同于任务全部完成。当前成果可作为稳定的第一阶段架构基座，后续应继续按本报告第 8 节逐模块拆分。

## 2. 工作区保护

开始时已存在以下非本任务改动，实施期间未回退：

- `.mini-code-memory/MEMORY.md`
- `minicode/tui/input_handler.py`
- `minicode/types.py`（内容迁移到 `core/types.py` 时原样保留）
- `tests/test_tty_app.py`
- `.agents/`、`.codex/`、`docs/LEARNING_GUIDE.md`

## 3. 已完成工作

### 3.1 架构护栏与循环治理

- 新增 `tests/test_architecture.py`，检测 package 循环、Core 边界、Runtime→UI 禁止依赖和已知循环边。
- 提取 `providers.spec.Provider/detect_provider`，配置不再导入完整模型注册表。
- 提取 `context.tokens`，OpenAI adapter 不再依赖 `ContextManager`。
- Provider fallback 选择下沉到 `providers.fallbacks`，消除 `config ↔ providers` 回边。
- ContextManager 的默认状态路径不再反向导入配置 package。
- 当前架构测试报告 package 级循环为 0。

### 3.2 Core 与稳定类型

- `types.py` → `core/types.py`
- `state.py` → `core/state.py`
- `workspace.py` → `core/workspace.py`
- 旧路径显式导出，测试验证旧/新对象身份一致。
- `core.workspace` 使用窄 Protocol，移除对工具实现的反向依赖。

### 3.3 Agent Runtime 真拆分

- `agent_loop.py` 从 2403 行降为 9 行稳定门面。
- `runtime/runner.py` 保存 `run_agent_turn()` 总编排。
- 已物理提取：
  - `runtime/lifecycle.py`
  - `runtime/model_execution.py`
  - `runtime/tool_execution.py`
  - `runtime/policy.py`
- `runtime/kernel.py` 承载 turn policy、widen、verification 与终态决策。
- 函数签名、callback、fallback、工具顺序和终态通过 Agent/集成/压力测试。

### 3.4 数据子系统迁移

- `minicode.memory` 已转换为 package；旧 `MemoryManager` 等导入保持可用。
- `context_manager.py`、`context_compactor.py`、`timeline_memory.py`、`session.py` 转为兼容门面。
- Session 门面同步 `MINI_CODE_DIR`/`SESSIONS_DIR`，保留旧 monkeypatch 语义。
- Memory 私有 helper 的既有调用已审计并在兼容窗口内保留。
- 建立 Memory Timeline、Compaction、Session models/rewind/formatters 等目标 API 边界。

### 3.5 领域归包与兼容门面

共 73 个根模块成为薄兼容门面。对存在 monkeypatch 或模块级可变状态的模块，旧路径和新路径共享同一模块对象；这修复了普通 re-export 无法保持权限路径、后台任务 registry、CLI 依赖和模型工厂 patch 的问题。

### 3.6 入口修复

新增 `minicode-headless -h/--help` 标准帮助分支，帮助请求不再启动 Runtime 或初始化用户日志；新增回归测试。

## 4. 迁移映射

### Core / Config / Provider

| 旧路径 | 新实现路径 |
|---|---|
| `minicode.types` | `minicode.core.types` |
| `minicode.state` | `minicode.core.state` |
| `minicode.workspace` | `minicode.core.workspace` |
| `minicode.config` | `minicode.config` package（实现暂在 `__init__.py`） |
| `minicode.model_registry` | `minicode.providers.registry` |
| `minicode.model_switcher` | `minicode.providers.switching` |
| `minicode.openai_adapter` | `minicode.providers.openai` |
| `minicode.anthropic_adapter` | `minicode.providers.anthropic` |
| `minicode.api_retry` | `minicode.providers.retry` |
| `minicode.mock_model` | `minicode.providers.mock` |
| `minicode.cost_tracker` | `minicode.providers.cost` |

### Runtime / Context

| 旧路径 | 新实现路径 |
|---|---|
| `minicode.agent_loop` | `minicode.runtime.runner` |
| `minicode.turn_kernel` | `minicode.runtime.kernel` |
| `minicode.agent_intelligence` | `minicode.runtime.intelligence` |
| `minicode.agent_router` | `minicode.runtime.routing` |
| `minicode.agent_reflection` | `minicode.runtime.reflection` |
| `minicode.pipeline_engine` | `minicode.runtime.pipeline` |
| `minicode.smart_router` | `minicode.runtime.smart_routing` |
| `minicode.intent_parser` | `minicode.runtime.intent` |
| `minicode.capability_registry` | `minicode.runtime.capabilities` |
| `minicode.runtime_profiles` | `minicode.runtime.profiles` |
| `minicode.runtime_profile_eval` | `minicode.runtime.profile_eval` |
| `minicode.release_readiness` | `minicode.runtime.release_readiness` |
| `minicode.product_surfaces` | `minicode.runtime.product_surfaces` |
| `minicode.task_object` | `minicode.runtime.tasks.object` |
| `minicode.task_graph` | `minicode.runtime.tasks.graph` |
| `minicode.task_tracker` | `minicode.runtime.tasks.tracker` |
| `minicode.context_manager` | `minicode.context.manager` |
| `minicode.context_compactor` | `minicode.context.compaction.dispatcher` |
| `minicode.layered_context` | `minicode.context.layered` |
| `minicode.working_memory` | `minicode.context.working` |
| `minicode.prompt` | `minicode.context.prompt` |
| `minicode.prompt_pipeline` | `minicode.context.prompt_pipeline` |
| `minicode.micro_compact` | `minicode.context.compaction.micro_legacy` |
| `minicode.circuit_breaker` | `minicode.context.compaction.circuit_breaker` |

### Memory / Persistence

| 旧路径 | 新实现路径 |
|---|---|
| `minicode.memory` | `minicode.memory` package / `memory.manager` |
| `minicode.timeline_memory` | `minicode.memory.timeline.reasoner` |
| `minicode.memory_pipeline` | `minicode.memory.pipeline` |
| `minicode.memory_curator_agent` | `minicode.memory.curator` |
| `minicode.memory_injector` | `minicode.memory.injector` |
| `minicode.memory_reranker` | `minicode.memory.reranker` |
| `minicode.vector_memory` | `minicode.memory.vector` |
| `minicode.domain_classifier` | `minicode.memory.domain` |
| `minicode.session` | `minicode.persistence.session_storage` |
| `minicode.history` | `minicode.persistence.history` |
| `minicode.user_profile` | `minicode.persistence.user_profile` |

### Control / Safety / Integration / Observability / CLI

| 旧路径族 | 新实现路径族 |
|---|---|
| `adaptive_pid_tuner` | `control.adaptive_pid` |
| `cybernetic_ablation` | `control.ablation` |
| `cybernetic_orchestrator` | `control.orchestrator` |
| `cybernetic_supervisor` | `control.supervisor` |
| `feedback_controller` / `feedforward_controller` | `control.feedback` / `control.feedforward` |
| `predictive_controller` / `decoupling_controller` | `control.predictive` / `control.decoupling` |
| `context_cybernetics` / `cost_control` | `control.context` / `control.cost` |
| `stability_monitor` / `verification_controller` | `control.stability` / `control.verification` |
| `self_healing_engine` / `state_observer` | `control.recovery` / `control.state_observer` |
| `progress_controller` | `control.progress` |
| `permissions` / `auto_mode` / `file_review` | `safety.permissions` / `safety.auto_mode` / `safety.file_review` |
| `mcp` / `skills` / `hooks` / `background_tasks` | `integrations.*` |
| `logging_config` / `agent_metrics` / `decision_audit` | `observability.*` |
| `cli_commands` / `manage_cli` / `local_tool_shortcuts` / `install` | `cli.*` |

## 5. 公共 API 兼容表

| API | 状态 |
|---|---|
| `minicode.agent_loop.run_agent_turn` | 保持，转发 Runtime runner |
| `minicode.memory.MemoryManager` | 保持，Memory package 导出 |
| `minicode.session.SessionData` | 保持，对象来自 persistence 实现 |
| `minicode.config.load_runtime_config` | 保持，package API |
| 三个 console scripts | 保持并通过隔离安装冒烟 |
| 旧模块 monkeypatch | 模块身份别名保持 |
| 旧 session JSON | 原模型与默认值逻辑保持，测试通过 |

## 6. 规模与依赖对比

| 指标 | 重构前 | 当前 | 说明 |
|---|---:|---:|---|
| 根目录 Python LOC | 38,004 | 3,526 | 下降 90.7%，当前包含 73 个兼容门面与稳定入口 |
| 根目录 Python 文件 | 约 80 | 78 | 数量变化小是因为保留旧路径；业务实现已移入 package |
| `agent_loop.py` | 2,403 | 9 | 新 runner 2,052 行，另有 4 个已提取模块 |
| 最大实现文件 | 3,513 | 3,513 | Timeline 尚未物理拆完，属于未完成项 |
| 已知 package 循环 | 1 | 0 | 由架构测试持续保护 |
| `runtime.runner` 直接模块导入 | 约 37 | 41 | 原始模块扇出尚未下降；按目标 package 聚合后为 5 个领域包，仍需组合根/依赖对象继续收敛 |

## 7. 任务项完成度

| 编号 | 完成度 | 状态 |
|---|---:|---|
| ARCH-001 基线 | 100% | 完成 |
| ARCH-002 架构测试 | 100% | 完成 |
| ARCH-003 打断循环 | 100% | 完成 |
| ARCH-004 目标 package | 100% | 完成 |
| ARCH-005 Agent Runtime | 90% | 主要完成；runner 仍偏大 |
| ARCH-006 Context/Compaction | 70% | token 真拆分；dispatcher 尚大 |
| ARCH-007 Memory/Timeline | 55% | package/API 完成；物理职责拆分未完成 |
| ARCH-008 Session | 65% | package/API/兼容完成；storage 尚大 |
| ARCH-009 Control 等归类 | 100% | 完成 |
| ARCH-010 Config/CLI | 55% | 归包完成；内部职责拆分未完成 |
| ARCH-011 入口/打包 | 100% | 完成 |
| ARCH-012 回归/报告 | 100% | 完成 |

加权完成度按 P0 未完成项下调后为 **84%**。

## 8. 未完成项与下一批建议

必须继续完成后才能宣布任务书 DoD：

1. 将 `memory/timeline/reasoner.py` 的模型、StateReasoner、日期/数值/旅行/事件规则物理拆到现有目标模块。
2. 将 `memory/manager.py` 的 models、validation/storage、BM25/TF-IDF、manager、prompt formatting 物理拆分。
3. 将 `persistence/session_storage.py` 的 models、delta/index I/O、rewind、autosave、formatters 物理拆分。
4. 将 `context/compaction/dispatcher.py` 的 models、budget、dedup、reactive、session-memory 物理拆分。
5. 将 `config/__init__.py` 与 `cli/commands.py` 从 API 边界继续拆为真实实现模块。
6. 通过显式依赖对象进一步降低 `runtime.runner` 的直接模块扇出与 2,052 行规模。

上述工作应继续遵守“一子系统一批次、测试绿色后再前进”，不得一次合并拆分。
