# MC-ARCH-CLEAN-20260622 实现报告

| 项目 | 结果 |
|---|---|
| 任务 | 根兼容门面退场、内部导入迁移与超大模块物理拆分 |
| 日期 | 2026-06-22 |
| 代码与测试状态 | **完成，最终验收绿色** |
| 根目录 | 7 个 Python 文件，严格符合白名单 |
| 删除门面 | 71 个 |
| 已知 package 循环 | 0 |
| Python 回归 | 1183 passed，0 failed |
| 前端回归 | 28 passed，build passed |
| 提交状态 | 全部子系统均已独立提交；文档作为最终验收批次提交 |

## 1. 结论

任务书要求的代码重构、行为回归、架构护栏、wheel/入口验收和文档交付已完成。根目录不再保留 Provider、Context、Control、Memory、Integration、CLI、Core 等旧门面；仓库内部旧路径引用为零，未使用 import hook 或集中 `sys.modules` 别名。

Timeline、Memory、Session、Compaction、Config、CLI 和 Runtime runner 均已承载真实物理职责拆分。稳定入口、旧 session/delta/checkpoint/rewind、配置优先级、TUI、Headless 和 Web 行为由全量测试覆盖。

平台曾在尾部阶段临时拒绝 Git index 写入；恢复授权后已继续完成 Compaction、Config、CLI、Runner 和最终文档提交，未采用绕过方式操作 `.git`。

## 2. 工作区保护

开始时已存在并保留的用户改动：

- `.mini-code-memory/MEMORY.md`；
- `minicode/tui/input_handler.py` 的计时修复；
- `tests/test_tty_app.py` 的对应回归测试；
- `.agents/`、`.codex/`、`docs/LEARNING_GUIDE.md`。

涉及脏文件的路径迁移均使用精确 index patch 分离提交，没有把用户改动带入本任务提交。最终工作树只保留上述用户改动，未做回退。

## 3. 根目录清理

最终白名单：

```text
__init__.py
agent_loop.py
headless.py
main.py
session.py
tooling.py
tty_app.py
```

删除的 71 个根门面：

```text
adaptive_pid_tuner, agent_intelligence, agent_metrics, agent_reflection,
agent_router, anthropic_adapter, api_retry, auto_mode, background_tasks,
capability_registry, circuit_breaker, cli_commands, context_compactor,
context_cybernetics, context_manager, cost_control, cost_tracker,
cybernetic_ablation, cybernetic_orchestrator, cybernetic_supervisor,
decision_audit, decoupling_controller, domain_classifier,
feedback_controller, feedforward_controller, file_review, history, hooks,
install, intent_parser, layered_context, local_tool_shortcuts,
logging_config, manage_cli, mcp, memory_curator_agent, memory_injector,
memory_pipeline, memory_reranker, micro_compact, mock_model, model_registry,
model_switcher, openai_adapter, permissions, pipeline_engine,
predictive_controller, product_surfaces, progress_controller, prompt,
prompt_pipeline, release_readiness, runtime_profile_eval, runtime_profiles,
self_healing_engine, skills, smart_router, stability_monitor, state,
state_observer, task_graph, task_object, task_tracker, timeline_memory,
turn_kernel, types, user_profile, vector_memory, verification_controller,
working_memory, workspace
```

## 4. 旧路径到新路径迁移

| 旧路径族 | 新路径 |
|---|---|
| `types/state/workspace` | `core.types/core.state/core.workspace` |
| Provider adapters、registry、retry、cost、mock | `providers.*` |
| `permissions/auto_mode/file_review` | `safety.*` |
| logging、metrics、decision audit | `observability.*` |
| cybernetic/controller 模块 | `control.*` |
| intent、pipeline、routing、task、profile、kernel | `runtime.*` / `runtime.tasks.*` |
| context manager、prompt、layered、working | `context.*` |
| context compactor、micro、circuit breaker | `context.compaction.*` |
| timeline、memory pipeline/curator/injector/reranker/vector/domain | `memory.*` / `memory.timeline.*` |
| history、user profile | `persistence.*` |
| MCP、skills、hooks、background tasks | `integrations.*` |
| CLI commands、management、shortcuts、install | `cli.*` |

稳定兼容面仍为：

| 稳定 API | 实现 |
|---|---|
| `minicode.agent_loop.run_agent_turn` | `runtime.runner.run_agent_turn` |
| `minicode.memory.MemoryManager` | `memory.manager.MemoryManager` |
| `minicode.session.SessionData` | `persistence.session_models.SessionData` |
| `minicode.config.load_runtime_config` | `config.settings.load_runtime_config` |

## 5. 依赖治理

- Provider 识别原语迁入 `core.provider_spec`，Config 与 Provider 不再互相依赖；
- 纯 token 估算迁入 `core.tokens`，Provider 不依赖 Context；
- Intent 数据模型迁入 `core.intent`，Control 不反向依赖 Runtime；
- ToolScheduler/ErrorClassifier 真实实现迁入 `control.intelligence`；
- Reflection 真实实现迁入 `memory.reflection`；
- Product surface 快照迁入 `integrations.product_surfaces`；
- Runtime package initializer 保持无副作用；
- 当前 package 图无循环，Runtime 不依赖 TUI/Web。

## 6. 超大模块拆分

| 模块 | 拆分前 | 拆分后集中模块 | 新职责模块 |
|---|---:|---:|---|
| Timeline Reasoner | 3,513 | 183 | models、extractors、index、numeric/event reasoning、4 类 rules |
| Memory Manager | 1,986 | 521 | models、storage、retrieval、retrieval manager、prompt |
| Session Storage | 1,378 | 420 | session models、rewind、autosave、formatters |
| Compaction Dispatcher | 1,150 | 288 | models、budgets、micro、session memory、reactive、service |
| Config API | 798 | 16 | paths、settings、providers、mcp、diagnostics |
| CLI Commands | 862 | 12 | registry、matching、handlers、formatters |
| Runtime Runner | 2,052 | 1,125 | composition、prelude、control runtime、coda |

拆分不是 re-export 伪装：上述目标模块包含原类、函数和策略的真实实现；集中模块只做 API 聚合、策略分发或时序组合。

## 7. 架构测试

新增/扩展的自动护栏：

- `test_root_python_files_match_allowlist`；
- `test_internal_modules_do_not_import_legacy_root_facades`；
- `test_layered_packages_have_no_import_cycles`；
- `test_core_depends_only_on_standard_library`；
- `test_runtime_never_imports_tui_or_web`；
- `test_cross_package_imports_do_not_use_private_names`；
- `test_required_legacy_public_imports_still_work`。

## 8. 分阶段提交

已完成提交：

1. `f251333` inventory 与 root allowlist；
2. `cce9041` Provider/Observability/Safety；
3. `b699f1d` Control；
4. `fb37893` Runtime 辅助门面与依赖解环；
5. `c33e0a0` Context；
6. `3e513a0` Memory 门面；
7. `c7069f2` Persistence 门面；
8. `cb5c81b` Integration/CLI/Core 最终门面；
9. `fada01c` Timeline 物理拆分；
10. `66567c2` Memory 物理拆分；
11. `a711a6d` Session 物理拆分；
12. `d1fd572` Compaction 物理拆分；
13. `63f708d` Config 物理拆分；
14. `bce4b6a` CLI 物理拆分；
15. `038136a` Runtime runner 收敛；
16. 最终结构文档、实现报告与测试报告批次。

## 9. 验收状态

代码、行为、架构、测试、构建、wheel、入口、分阶段提交和文档验收项全部满足。用户既有工作树改动仍保持未提交状态，未纳入本任务提交。
