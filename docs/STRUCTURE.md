# MiniCode Python — 包结构（STRUCTURE）

> 规范实现：仓库根目录的 `minicode/` 包。本文按子系统列出当前真实结构与模块职责（以实际文件为准，2026-06-19 校对）。

---

## 入口与运行时

| 模块 | 职责 |
|---|---|
| `main.py` | CLI 入口；参数解析（`--log-level`/`--structured-logs`/`--allow-edits`/`--rewind` 等），启动 TTY 或 headless。 |
| `headless.py` | 非交互一次性执行（CI/CD）；`run_headless`，支持 `--allow-edits`/`MINI_CODE_ALLOW_EDITS` 免交互编辑。 |
| `tty_app.py` | 全屏 TTY 应用主循环（事件驱动、raw 输入、节流渲染、自动保存）。 |
| `manage_cli.py` | `/model`、`/mcp` 等管理子命令。 |
| `install.py` | 跨平台启动器安装（PATH 指引）。 |
| `config.py` | 运行时配置加载（`~/.mini-code/settings.json`、`.env`、环境变量）。 |
| `workspace.py` | 工作区路径解析（`resolve_tool_path`、cwd 边界）。 |
| `state.py` | 应用状态 Store（busy/cost/context-usage 等状态机）。 |

## Web 产品面

Web 是可选产品面，核心 Runtime 不反向依赖 Web。Python 服务位于 `minicode/web/`，React 浏览器端位于仓库根目录 `web/`。

| 模块 | 职责 |
|---|---|
| `web/app.py` | FastAPI 应用工厂、统一异常响应、生产静态资源挂载。 |
| `web/api.py` | 会话、消息、取消、权限、Diff REST API 与 WebSocket 事件端点。 |
| `web/events.py` | 稳定事件信封与事件类型。 |
| `web/broker.py` | 线程安全序号分配、历史保留、断线重放与等待订阅。 |
| `web/runner.py` | `run_agent_turn` callback 适配、单活跃 turn、终态、审批协调与会话保存。 |
| `web/schemas.py` | Pydantic 请求/响应协议。 |
| `web/security.py` | 浏览器序列化边界的 Secret 脱敏。 |
| `web/diff.py` | 工作区内只读 Git Diff 与 untracked 文件统计。 |
| `web/cli.py` | `minicode-web` 入口，固定监听 `127.0.0.1`。 |

浏览器端按 `src/api/`、`src/features/`、`src/store/`、`src/styles/` 分层；React 只消费 REST/WebSocket 协议，不复制 Agent 决策。

## Agent 循环与编排

| 模块 | 职责 |
|---|---|
| `agent_loop.py` | 核心 agent 循环（think/act/verify 递归、工具调度、压缩触发、控制信号反馈）。 |
| `turn_kernel.py` | 单轮状态机（max_steps、widen、重试、verification）。 |
| `agent_intelligence.py` | 运行时智能启发（并发/模式信号）。 |
| `agent_router.py` | 任务复杂度分类 → 模型路由。 |
| `agent_reflection.py` | 任务后自省引擎。 |
| `smart_router.py` | 智能工具/路径路由。 |
| `intent_parser.py` | 用户意图解析（CODE/DEBUG/REFACTOR/SEARCH…）。 |
| `domain_classifier.py` | 领域分类。 |
| `pipeline_engine.py` | 多步流水线引擎。 |
| `task_graph.py` / `task_object.py` / `task_tracker.py` | 任务图、任务对象、任务追踪。 |

## 工具系统

| 模块 | 职责 |
|---|---|
| `tooling.py` | `ToolRegistry`/`ToolDefinition`/`ToolResult`；`execute` 带异常兜底 + 工具执行日志。 |
| `local_tool_shortcuts.py` | `/ls` `/grep` `/read` `/write` `/edit` `/cmd` 等快捷解析。 |
| `capability_registry.py` | 能力注册与执行统计。 |
| `tools/` | 内置工具集（见下）。 |

### `tools/`（30 个内置工具）
- **文件**：`read_file` `write_file` `edit_file` `modify_file` `patch_file` `list_files` `file_tree` `grep_files` `batch_ops` `archive_utils`
- **执行**：`run_command`（支持 `MINI_CODE_COMMAND_ENCODING` 编码开关）`test_runner` `git`
- **代码**：`code_nav` `code_review` `diff_viewer`
- **网络**：`web_fetch` `web_search` `http_utils`
- **交互**：`ask_user` `todo_write` `task`（子 agent）`load_skill`
- **工具函数**：`text_utils` `regex_utils` `json_utils` `csv_utils` `encoding_utils`

## TUI（终端界面，`tui/`）

| 模块 | 职责 |
|---|---|
| `renderer.py` | 整屏渲染（缓存 header/footer、增量 hash）。 |
| `screen.py` | alt-screen / VT 处理 / Windows VT 启用 / dumb 终端判定。 |
| `transcript.py` | 会话流渲染 + BM25/CJK 视觉换行滚动（端口自 TS `wrapPanelBodyLine`）。 |
| `input_parser.py` | raw 输入 → 事件（按键/文本/滚轮/粘贴，多行粘贴不提交）。 |
| `input_handler.py` | `_handle_input`（命令分发、agent turn 启动、工具生命周期）。 |
| `event_flow.py` | 事件路由（普通/审批/反馈模式）。 |
| `navigation.py` | 滚动/历史/斜杠命令匹配。 |
| `chrome.py` | banner/panel/footer/permission 渲染原语 + 终端尺寸缓存。 |
| `session_flow.py` | TTY 会话加载/创建/快照/收尾。 |
| `runtime_control.py` | 节流渲染器、alt-screen 进出、SIGWINCH。 |
| `tool_lifecycle.py` / `tool_helpers.py` | 工具条目推送/折叠/收尾。 |
| `state.py` | `ScreenState`/`TtyAppArgs`。 |
| `theme.py` `markdown.py` `input.py` `ui_hints.py` `types.py` | 主题、markdown 渲染、输入提示框、UI 提示、类型。 |

## 模型适配与注册

| 模块 | 职责 |
|---|---|
| `anthropic_adapter.py` | Anthropic Messages API（流式/工具/缓存计费）。 |
| `openai_adapter.py` | OpenAI 兼容 API（流式/工具/计费，支持代理）。 |
| `mock_model.py` | 测试用 ScriptedModel 基类。 |
| `model_registry.py` | 模型注册表、`create_model_adapter`、Provider 解析、模型状态格式化。 |
| `model_switcher.py` | 运行时模型热切换（`switch_to`/fallback）。 |
| `api_retry.py` | 可重试状态判定 + 指数退避 + Retry-After 解析。 |

## 上下文与压缩

| 模块 | 职责 |
|---|---|
| `context_manager.py` | token 估算（CJK 感知）、`get_model_context_window`、`compute_context_stats`、`token_count_with_estimation`。 |
| `context_compactor.py` | `AutoCompactDispatcher`（熔断 + 自动恢复）、`ReactiveCompactEngine`、`ToolResultBudgetManager`、`ReadDedupManager`、microcompact/session-memory 引擎。 |
| `micro_compact.py` | 轻量工具结果裁剪（时间/预算双策略，超预算 trim 最旧）。 |
| `circuit_breaker.py` | 通用 `CompactionCircuitBreaker`（auto-reset）。 |
| `layered_context.py` / `working_memory.py` | 分层上下文 / 工作记忆。 |
| `timeline_memory.py` | 时间线记忆。 |
| `vector_memory.py` | 向量记忆。 |
| `prompt.py` / `prompt_pipeline.py` | 系统提示组装（静态前缀 + 动态后缀，含 malformed 输入加固）。 |

## 记忆系统

| 模块 | 职责 |
|---|---|
| `memory.py` | 三层 `MemoryManager`（user/project/local）+ BM25/TF-IDF 检索（`MemoryEntry` content 强制 str）。 |
| `memory_pipeline.py` | 记忆流水线编排。 |
| `memory_curator_agent.py` | 记忆策展 agent。 |
| `memory_injector.py` | 上下文感知记忆注入控制器。 |
| `memory_reranker.py` | 检索结果重排。 |

## 会话 / 持久化

| 模块 | 职责 |
|---|---|
| `session.py` | 会话持久化（全量 + 增量 delta + 合并）、checkpoint、rewind；`update_metadata` 容错。 |
| `history.py` | 提示历史（`~/.mini-code/history.json`，TTL 缓存，str 强制）。 |
| `hooks.py` | 钩子系统（USER_INPUT/ASSISTANT_OUTPUT 等事件）。 |
| `background_tasks.py` | 后台任务注册/列表。 |

## 权限与安全

| 模块 | 职责 |
|---|---|
| `permissions.py` | `PermissionManager`（路径/命令/编辑审批 + auto 模式 + 结构化日志）。 |
| `auto_mode.py` | `AutoModeChecker`（风险评估、`detect_prompt_injection`、`classify_output_safety`）。 |
| `file_review.py` | 文件改动审查（diff 预览、`apply_reviewed_file_change`）。 |

## MCP / 技能 / 用户

| 模块 | 职责 |
|---|---|
| `mcp.py` | MCP stdio 客户端（懒启动、npx/`.cmd` 解析、协议自动探测、安全白名单）。 |
| `skills.py` | SKILL.md 工作流发现与加载。 |
| `user_profile.py` | 用户画像（语言/风格，USER.md）。 |

## 日志

| 模块 | 职责 |
|---|---|
| `logging_config.py` | `setup_logging`（按大小轮转）、`StructuredFormatter`、`log_api_call`/`log_tool_execution`/`log_permission_check`/`log_session_event`、`--structured-logs`/`MINI_CODE_LOG_STRUCTURED`。 |

## 控制论子系统（cybernetic）

> 自适应控制回路：传感器 → PID 控制器 → 执行器，黑盒调节 agent 行为。

| 模块 | 职责 |
|---|---|
| `cybernetic_orchestrator.py` | 控制回路编排总入口。 |
| `cybernetic_supervisor.py` | 全局健康/风险聚合。 |
| `cybernetic_ablation.py` | 控制回路消融开关。 |
| `context_cybernetics.py` | 上下文压力 PID + 预测。 |
| `feedback_controller.py` | 反馈 PID（含 `SystemState`/`ControlSignal`，抗饱和）。 |
| `feedforward_controller.py` | 前馈预配置（意图→PreemptiveConfig）。 |
| `predictive_controller.py` | 指数平滑/移动平均预测。 |
| `decoupling_controller.py` | 解耦控制。 |
| `adaptive_pid_tuner.py` | 自适应 PID 整定。 |
| `state_observer.py` | 系统状态观测。 |
| `progress_controller.py` | 任务进度/停滞控制。 |
| `stability_monitor.py` | 稳定性监测。 |
| `cost_control.py` | 成本速率 PID + 预算调节。 |
| `cost_tracker.py` | 成本/用量统计（`calculate_cost`、`ModelUsage`）。 |
| `agent_metrics.py` | 工具历史指标（`ToolHistoricalStats`）。 |
| `verification_controller.py` | 风险自适应验证规划。 |
| `self_healing_engine.py` | 自愈引擎。 |
| `decision_audit.py` | 决策审计。 |
| `runtime_profiles.py` / `runtime_profile_eval.py` | 运行时画像与评估。 |
| `release_readiness.py` | 发布就绪评估。 |
| `product_surfaces.py` | 产品快照（指令/钩子/委派/扩展/就绪摘要）。 |

## 共享类型

| 模块 | 职责 |
|---|---|
| `types.py` | `ChatMessage`、`AgentStep`、`ModelAdapter`、`RuntimeEvent`、`StepDiagnostics` 等核心类型。 |

---

## 测试与配置（仓库根，非包内）

- `tests/` — pytest 套件（含 `test_integration_rounds.py` 端到端、`test_ts_ported.py` TS 对齐、各子系统单测）。
- `conftest.py` — pytest 共享夹具。
- `pyproject.toml` — 包定义（入口 `minicode-py` / `minicode-headless` / `minicode-web`，Web 为可选依赖）。
- `.env.example` — 环境变量样例（含 `MINI_CODE_COMMAND_ENCODING`）。
- `ts-src/` — TypeScript 原版（移植参考，保留）。
- `py-src/experiments/` — 研究 harness（未跟踪，`test_sealed_mini_study` 使用）。
