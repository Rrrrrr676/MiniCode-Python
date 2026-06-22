# MiniCode Python 包结构治理与安全拆分任务书

| 项目 | 内容 |
|---|---|
| 文档日期 | 2026-06-22 |
| 任务编号 | `MC-ARCH-PKG-20260622` |
| 任务名称 | Python Runtime 包分类、依赖治理与大模块安全拆分 |
| 任务性质 | 行为保持型架构重构 |
| 优先级 | P0 |
| 建议工期 | 8-12 个工作日，按阶段独立验收 |
| 影响范围 | `minicode/`、`tests/`、架构文档与打包配置 |
| 核心要求 | 认真拆分、保持兼容、不得引入功能回归、最终完成全量测试 |

## 1. 背景与现状

当前 `minicode/` 根目录已经出现明显的结构膨胀：

- 根目录包含约 80 个 Python 模块、38,004 行代码；
- `tools/`、`tui/`、`web/` 已经形成目录边界，但 Agent、模型、上下文、记忆、会话、控制、安全和集成模块仍大量平铺在包根目录；
- `agent_loop.py` 约 2,403 行，其中 `run_agent_turn()` 承担过多生命周期与跨子系统协调职责，并直接依赖约 37 个根模块；
- `timeline_memory.py` 约 3,513 行、`memory.py` 约 1,986 行、`session.py` 约 1,378 行，已经超过适合单模块维护和评审的规模；
- 当前存在可确认的根模块循环依赖：

```text
config
  -> model_registry
  -> openai_adapter
  -> context_manager
  -> config
```

- 测试和运行代码广泛直接导入 `minicode.agent_loop`、`minicode.memory`、`minicode.session`、`minicode.config` 等路径，粗暴移动文件会造成导入、monkeypatch、持久化和入口兼容问题。

本任务不是简单地把文件移动到若干文件夹中，而是要在保持现有行为的前提下，完成职责分类、依赖方向治理、大模块拆分、兼容迁移和系统性验证。

## 2. 任务目标

完成后必须达到以下结果：

1. `minicode/` 根目录只保留稳定入口、兼容门面和少量包级文件；
2. Runtime、Provider、Context、Memory、Control、Persistence、Safety、Integrations、CLI 等子系统具有清晰目录边界；
3. 消除已知循环依赖，并通过自动化架构测试阻止循环依赖重新出现；
4. 将 `agent_loop.py`、`timeline_memory.py`、`memory.py`、`session.py`、`context_compactor.py`、`context_manager.py` 等超大模块按真实职责拆分；
5. 保持 CLI、Headless、TUI、Web、工具、权限、会话、配置、模型适配和记忆行为不变；
6. 保持旧 session、旧配置和稳定 Python 导入路径可用；
7. 每一阶段均有定向测试，最终通过 Python 全量测试、Web 测试、前端测试、构建和打包检查；
8. 更新结构文档、开发规范、实现报告和测试报告，使新结构可持续维护。

## 3. 重构红线

以下要求是不可降低的硬性约束：

### 3.1 不允许一次性大搬迁

- 禁止在一个变更批次中同时移动全部根模块；
- 每个批次只处理一个明确子系统或一条依赖链；
- 当前批次未通过定向测试和回归测试前，不得开始下一批次；
- 文件移动、职责拆分和行为修改不得混在同一批次中，除非行为修改是修复重构过程中发现且已有回归测试覆盖的真实缺陷。

### 3.2 不允许借重构改变产品行为

- 不修改 Agent 决策语义、工具执行顺序、权限策略、重试策略和终态语义；
- 不修改 token 估算、压缩触发、成本计算、模型 fallback 和 session 保存格式的既有语义；
- 不改变 TUI、Headless、Web 的用户可见行为和稳定入口；
- 不顺手删除看似未使用但尚未完成调用链和兼容性审计的代码；
- 不以“测试需要更新”为理由降低断言强度或删除原有测试覆盖。

### 3.3 不允许破坏兼容性

以下入口和导入路径在任务完成时必须继续可用：

```text
minicode-py
minicode-headless
minicode-web
minicode.agent_loop.run_agent_turn
minicode.memory.MemoryManager
minicode.session.SessionData
minicode.config.load_runtime_config
```

- 旧模块优先转换为薄兼容门面，通过显式重新导出保持 API；
- 公共名称必须使用 `__all__` 明确声明；
- 移动 dataclass、Enum、TypedDict 时必须验证 pickle/JSON/session 等持久化兼容风险；
- 必须审计测试和运行代码中的 monkeypatch 路径。简单重新导出不一定能保持 monkeypatch 生效，必要时应通过显式依赖注入或转发函数保持旧语义；
- 在所有内部调用和测试迁移完成前，不得删除旧导入路径。

### 3.4 失败立即停止扩散

- 任一阶段出现测试失败、循环依赖增加、入口不可运行或 session 不兼容时，立即停止后续搬迁；
- 先将当前批次修复到绿色状态，再继续下一阶段；
- 不允许在多个失败阶段上继续叠加修改；
- 禁止通过扩大 `try/except`、吞异常、改为 `Any` 或延迟导入来掩盖架构问题。

## 4. 目标包结构

目标结构如下。最终文件归属允许依据依赖审计做小幅调整，但调整必须在实现报告中说明理由，不能只为目录外观强行归类。

```text
minicode/
├── __init__.py
├── main.py                     # 稳定 CLI 入口与组合根
├── headless.py                 # 稳定 Headless 入口
├── agent_loop.py               # 兼容门面，转发 runtime.runner
├── core/
│   ├── types.py                # 跨子系统稳定类型与协议
│   ├── state.py                # 通用运行状态
│   ├── events.py               # 核心事件定义
│   ├── errors.py               # 稳定异常类型
│   └── workspace.py            # 工作区边界
├── config/
│   ├── __init__.py             # 兼容原 minicode.config API
│   ├── paths.py
│   ├── settings.py
│   ├── providers.py
│   ├── mcp.py
│   └── diagnostics.py
├── runtime/
│   ├── runner.py               # 单轮总编排
│   ├── lifecycle.py            # prelude/coda/终态收口
│   ├── model_execution.py      # 模型调用、fallback、诊断
│   ├── tool_execution.py       # 工具调度和结果回收
│   ├── policy.py               # turn policy/step policy
│   ├── intelligence.py
│   ├── routing.py
│   └── tasks/
├── providers/
│   ├── spec.py                 # Provider、detect_provider 等纯定义
│   ├── registry.py
│   ├── openai.py
│   ├── anthropic.py
│   ├── retry.py
│   ├── switching.py
│   └── mock.py
├── context/
│   ├── tokens.py               # 无配置反向依赖的 token 估算
│   ├── manager.py
│   ├── prompt.py
│   ├── layered.py
│   ├── working.py
│   └── compaction/
│       ├── models.py
│       ├── dispatcher.py
│       ├── budgets.py
│       ├── reactive.py
│       ├── micro.py
│       └── circuit_breaker.py
├── memory/
│   ├── __init__.py             # 兼容原 minicode.memory API
│   ├── models.py
│   ├── storage.py
│   ├── retrieval.py
│   ├── manager.py
│   ├── pipeline.py
│   ├── curator.py
│   ├── injector.py
│   └── timeline/
│       ├── models.py
│       ├── extractors.py
│       ├── index.py
│       ├── reasoner.py
│       └── rules/
├── control/
│   ├── orchestrator.py
│   ├── supervisor.py
│   ├── feedback.py
│   ├── feedforward.py
│   ├── predictive.py
│   ├── context.py
│   ├── cost.py
│   ├── stability.py
│   ├── verification.py
│   └── recovery.py
├── persistence/
│   ├── session_models.py
│   ├── session_storage.py
│   ├── rewind.py
│   ├── formatters.py
│   ├── history.py
│   └── user_profile.py
├── safety/
│   ├── permissions.py
│   ├── auto_mode.py
│   └── file_review.py
├── integrations/
│   ├── mcp.py
│   ├── skills.py
│   ├── hooks.py
│   └── background_tasks.py
├── observability/
│   ├── logging.py
│   ├── metrics.py
│   └── decision_audit.py
├── cli/
│   ├── commands.py
│   ├── management.py
│   ├── shortcuts.py
│   └── install.py
├── tools/                       # 保持现有边界
├── tui/                         # 保持现有边界
└── web/                         # 保持现有边界
```

本任务不包含迁移到 `src/minicode/`。`src` 布局属于打包隔离优化，不能替代内部职责治理，应在本任务稳定完成后单独评估。

## 5. 依赖方向规则

目标依赖方向：

```text
core
  ↓
config / providers / context / memory / persistence / safety / integrations / observability
  ↓
control
  ↓
runtime
  ↓
main / headless / cli / tui / web
```

必须遵守以下规则：

1. `core` 只依赖 Python 标准库，不导入 Runtime、产品面或具体 Provider；
2. `runtime` 可以编排其他领域服务，但其他领域服务不得反向导入 `runtime.runner`；
3. `tui`、`web`、`headless` 只调用 Runtime 公共接口，不复制 Agent 决策；
4. Runtime 和领域包不得导入 `tui` 或 `web`；
5. Provider 协议、Provider 识别和 Provider 实现分离，配置层不得反向导入完整模型注册表；
6. token 估算属于纯上下文能力，不应通过 `context_manager` 间接依赖用户配置；
7. Control 通过稳定 DTO、Protocol 或显式输入输出工作，不直接读取 UI 状态；
8. Memory 与 Context 的交互通过窄接口完成，禁止彼此导入内部实现模块；
9. 跨包使用公共入口，禁止导入其他包的 `_private_name`；
10. 新增 `tests/test_architecture.py`，自动检测禁止依赖和包级循环依赖。

## 6. 模块归类基线

| 目标包 | 当前模块示例 | 归类原则 |
|---|---|---|
| `core` | `types.py`、`state.py`、`workspace.py` | 稳定协议、基础状态、工作区边界 |
| `config` | `config.py` | 路径、设置、Provider 配置、MCP 配置、诊断分离 |
| `runtime` | `agent_loop.py`、`turn_kernel.py`、`agent_intelligence.py`、`agent_router.py`、`agent_reflection.py`、`task_*`、`pipeline_engine.py` | 单轮生命周期、任务与运行策略 |
| `providers` | `model_registry.py`、`model_switcher.py`、`openai_adapter.py`、`anthropic_adapter.py`、`api_retry.py`、`mock_model.py` | 模型协议、选择、适配和重试 |
| `context` | `context_manager.py`、`context_compactor.py`、`micro_compact.py`、`layered_context.py`、`working_memory.py`、`prompt*.py` | token、上下文、提示和压缩 |
| `memory` | `memory.py`、`memory_pipeline.py`、`memory_*`、`timeline_memory.py`、`vector_memory.py` | 记忆模型、存储、检索、推理和注入 |
| `control` | `cybernetic_*`、`*_controller.py`、`adaptive_pid_tuner.py`、`state_observer.py`、`stability_monitor.py`、`self_healing_engine.py`、`cost_control.py` | 控制回路、观测、稳定性与恢复 |
| `persistence` | `session.py`、`history.py`、`user_profile.py` | 持久化、恢复和展示格式化 |
| `safety` | `permissions.py`、`auto_mode.py`、`file_review.py` | 授权、风险和变更审查 |
| `integrations` | `mcp.py`、`skills.py`、`hooks.py`、`background_tasks.py` | 外部协议和扩展机制 |
| `observability` | `logging_config.py`、`agent_metrics.py`、`decision_audit.py` | 日志、指标和决策审计 |
| `cli` | `cli_commands.py`、`manage_cli.py`、`local_tool_shortcuts.py`、`install.py` | 命令解析、管理和启动器安装 |

`runtime_profiles.py`、`runtime_profile_eval.py`、`release_readiness.py`、`product_surfaces.py` 等模块在实施前必须根据调用方向完成归属审计。无法明确归属时不得随意搬迁，应记录为待决项并先保持原位。

## 7. 重点大模块拆分要求

### 7.1 `agent_loop.py`

目标是让 `run_agent_turn()` 回归“编排”职责，而不是继续包含全部实现。

建议拆分边界：

- `runtime.lifecycle`：初始化、稳定任务状态、prelude、coda、成功/失败/取消收口；
- `runtime.model_execution`：模型调用、空响应、停止原因、Provider fallback、错误摘要；
- `runtime.tool_execution`：单工具执行、并发调度、权限、ToolResult 处理；
- `runtime.policy`：step policy、widening、verification、继续/停止决策；
- `runtime.runner`：串联以上组件并发布稳定 RuntimeEvent；
- Runtime 依赖由组合根或显式依赖对象传入，避免在函数内部继续创建大量全局服务。

拆分后仍需保留：

```python
from minicode.agent_loop import run_agent_turn
```

并且函数参数、回调顺序、返回值、异常传播和终态必须保持一致。

### 7.2 `memory.py`

必须至少拆分为：

- 数据模型与枚举；
- JSON 校验、恢复和持久化；
- BM25/TF-IDF/tokenize 等检索算法；
- MemoryManager 业务编排；
- prompt 注入与格式化。

`minicode.memory` 最终改为 package，并由 `memory/__init__.py` 兼容导出原公共 API。不得在拆分过程中改变检索排序、scope/tier 语义、损坏恢复或文件路径。

### 7.3 `timeline_memory.py`

必须至少拆分为：

- 时间线和状态数据模型；
- record 提取器；
- 语义索引和评分；
- StateReasoner；
- 日期、数值、旅行、事件等专用规则。

专用启发式规则应放入 `memory/timeline/rules/`，避免继续堆积在单个文件。拆分前后必须使用相同测试样例验证答案、证据、排序和不足信息判断完全一致。

### 7.4 `session.py`

必须至少拆分为：

- SessionMetadata、SessionData、FileCheckpoint；
- session/delta/index 文件读写；
- checkpoint 与 rewind；
- autosave；
- list/resume/inspect/replay/checkpoint 格式化。

旧 session 文件必须继续可读；新增字段必须有默认值；session ID、目录位置、delta 合并和 rewind 行为不得改变。

### 7.5 `context_manager.py` 与 `context_compactor.py`

- token 估算、模型窗口、上下文统计与状态持久化分离；
- compaction 的数据模型、budget、dedup、dispatcher、reactive、session-memory 分离；
- 不得改变压缩阈值、消息保留顺序、tool result budget 和 circuit breaker 状态语义；
- Provider adapter 只能依赖纯 token 能力，不得依赖完整 ContextManager。

### 7.6 `config.py` 与 `cli_commands.py`

- 配置拆分为 paths、settings、Provider、MCP、diagnostics；
- CLI 拆分为命令注册、匹配补全、命令处理器和状态格式化；
- 环境变量名、配置优先级、默认值、诊断文本核心含义和 slash command 行为保持不变。

## 8. 分阶段实施计划

### 阶段 0：冻结基线

实施内容：

1. 记录当前 Git 状态和非本任务改动；
2. 运行并记录 Python 全量测试、Web 后端测试、前端测试和构建结果；
3. 记录当前公开导入路径、console scripts、模块行数和依赖图；
4. 为已知薄弱行为补充 characterization tests，测试现状而不是理想行为；
5. 建立实现报告和测试报告骨架。

退出条件：所有基线测试通过，或已有失败被明确记录且得到任务负责人确认。不得在未知基线下开始重构。

### 阶段 1：建立架构护栏并打断循环依赖

实施内容：

1. 新增 `tests/test_architecture.py`；
2. 提取纯 `Provider` 定义和 `detect_provider()`；
3. 提取纯 token 估算能力；
4. 消除 `config -> model_registry -> openai_adapter -> context_manager -> config` 循环；
5. 验证配置、Provider 选择和 token 估算行为不变。

退出条件：已知循环消失，架构测试、配置测试、Provider 测试和上下文测试全部通过。

### 阶段 2：建立目标 package 与兼容门面

实施内容：

1. 按目标结构创建 package；
2. 先移动低风险、低耦合的纯类型和纯函数；
3. 为旧路径保留显式重新导出；
4. 逐项验证 `__module__`、序列化、导入和 monkeypatch 兼容；
5. 每次只迁移一个 package。

退出条件：稳定旧导入路径全部通过 import smoke test，TUI/Headless/Web 均能启动到帮助或状态页面。

### 阶段 3：拆分 Agent Runtime

实施内容：

1. 先提取 model execution；
2. 再提取 tool execution；
3. 再提取 lifecycle 和 policy；
4. 最后收敛 `runtime.runner`；
5. 保留 `minicode.agent_loop.run_agent_turn` 门面；
6. 每次提取只移动已有逻辑，不同步重写算法。

退出条件：Agent 单元、集成、压力、控制论、Web runner、Headless 和 TUI 相关测试全部通过；事件顺序和终态无变化。

### 阶段 4：拆分 Context、Memory 与 Persistence

实施顺序：

1. Context token 与统计；
2. Compaction；
3. Memory models/storage/retrieval/manager；
4. Timeline memory；
5. Session models/storage/rewind/formatters。

每个子步骤都必须独立测试和提交，禁止把 Timeline、Memory、Session 同时拆完后再统一排错。

退出条件：上下文、记忆、时间线、session、rewind、压缩、压力和端到端测试全部通过，旧数据兼容测试通过。

### 阶段 5：归类 Control、Safety、Integrations、Observability 与 CLI

实施内容：

1. 按依赖方向逐包迁移；
2. 清除跨包私有导入；
3. 将通用 DTO 下沉到 `core`，但不得把业务实现下沉；
4. 更新所有内部导入；
5. 保留必要的旧路径兼容门面。

退出条件：包级依赖无循环，控制、安全、MCP、技能、CLI、日志与发布就绪测试通过。

### 阶段 6：清理与文档同步

实施内容：

1. 仅在全仓调用审计确认后删除无用兼容门面；
2. 修复乱码注释、过期模块说明和错误文档链接；
3. 更新 `docs/STRUCTURE.md` 和 `docs/DEVELOPMENT_GUIDELINES.md`；
4. 测试目录按子系统归类可作为后续步骤，但不得通过移动测试掩盖测试删除；
5. 输出迁移映射表和公共 API 表。

退出条件：文档与真实目录一致，不存在未解释的根目录业务模块，不存在失效导入。

### 阶段 7：全量验收

实施内容：

1. 在干净环境重新安装项目；
2. 运行所有自动化测试；
3. 执行 CLI、Headless、TUI、Web 冒烟测试；
4. 验证旧 session 和旧配置加载；
5. 检查 import cycle、打包内容、未跟踪生成物和 diff；
6. 完成实现报告和测试报告。

退出条件：满足本任务全部 Definition of Done 后方可宣布重构完成。

## 9. 任务分解

| 编号 | 优先级 | 任务 | 主要交付物 | 完成标准 |
|---|---|---|---|---|
| ARCH-001 | P0 | 建立测试与依赖基线 | 基线报告 | 全量测试结果和依赖图已记录 |
| ARCH-002 | P0 | 新增架构约束测试 | `tests/test_architecture.py` | 可检测禁止依赖和包级循环 |
| ARCH-003 | P0 | 打断已知循环依赖 | Provider spec、token 模块 | 已知四模块循环消失 |
| ARCH-004 | P0 | 创建目标 package | 目录、`__init__.py`、公共 API | package 可导入且边界清楚 |
| ARCH-005 | P0 | 拆分 Agent Runtime | `runtime/`、兼容 `agent_loop.py` | Agent 行为和事件顺序不变 |
| ARCH-006 | P0 | 拆分 Context/Compaction | `context/` | 阈值、预算和消息顺序不变 |
| ARCH-007 | P0 | 拆分 Memory/Timeline | `memory/` | 检索、推理和持久化结果不变 |
| ARCH-008 | P0 | 拆分 Session | `persistence/`、兼容 `session.py` | 旧 session、delta、rewind 通过 |
| ARCH-009 | P1 | 归类 Control 等子系统 | 对应 package | 无跨层反向依赖 |
| ARCH-010 | P1 | 拆分 Config 与 CLI | `config/`、`cli/` | 配置优先级和命令行为不变 |
| ARCH-011 | P0 | 稳定入口与打包验证 | console script/packaging 测试 | 三个入口均可安装运行 |
| ARCH-012 | P0 | 全量回归与报告 | 测试报告、实现报告 | 全部验收项通过 |

## 10. 测试策略

### 10.1 测试原则

- 重构开始前先跑测试，重构过程中持续跑测试，重构完成后再次全量测试；
- 每个拆分批次至少包含 import smoke、对应模块单测和相关集成测试；
- 移动代码时原测试断言不得减弱；
- 新目录不等于新行为，测试应证明拆分前后输入输出一致；
- 真实网络、真实模型 API 和真实用户配置不得参与自动化测试；
- 测试不得写入真实 `~/.mini-code`；
- 不允许新增无理由 skip、xfail 或 flaky 重试来制造绿色结果；
- 最终通过标准是全量通过，不是“主要测试通过”。

### 10.2 每批次最小验证

```bash
.venv/bin/python -m compileall -q minicode
.venv/bin/python -m pytest -q <本批次定向测试>
.venv/bin/python -m pytest -q tests/test_packaging.py tests/test_main.py tests/test_headless.py
git diff --check
```

### 10.3 子系统测试矩阵

| 子系统 | 必跑测试 |
|---|---|
| Provider/Config | `test_config.py`、`test_model_switching.py`、`test_openai_adapter.py`、`test_anthropic_adapter.py`、`test_mock_model.py`、`test_cost_tracker.py` |
| Agent Runtime | `test_agent_loop.py`、`test_agent_flow.py`、`test_agent_stress.py`、`test_cluster_stress.py`、`test_turn_kernel.py`、`test_integration.py`、`test_integration_rounds.py` |
| Context | `test_context_compactor.py`、`test_context_cybernetics.py`、`test_compaction_robustness.py`、`test_micro_compact.py`、`test_ts_ported.py` |
| Memory | `test_memory_*.py`、`test_domain_memory.py`、`test_timeline_memory.py`、`test_memory_stress.py`、`test_memory_e2e.py` |
| Session/Persistence | `test_session.py`、`test_main.py`、`test_tools.py`、`test_release_integration.py` |
| Control | `test_cybernetic_*.py`、`test_advanced_cybernetics.py`、`test_feedback_controller.py`、`test_feedforward_controller.py`、`test_verification_controller.py` |
| Safety/Tools | `test_permissions.py`、`test_tools.py`、`test_run_command_encoding.py`、`test_file_review.py`（如新增） |
| 产品面 | `test_tui.py`、`test_tty_app.py`、`test_headless.py`、`test_web_api.py`、`test_web_events.py`、`test_web_runner.py` |
| 架构/打包 | `test_architecture.py`、`test_packaging.py`、`test_engineering_inventory.py`、`test_functional_completeness.py`、`test_release_readiness.py` |

### 10.4 最终全量验证

```bash
.venv/bin/python -m compileall -q minicode
.venv/bin/python -m pytest -q

cd web
npm test -- --run
npm run build

git diff --check
```

还必须执行以下人工或脚本化冒烟验证：

1. `minicode-py --help` 正常；
2. `minicode-headless --help` 正常；
3. `minicode-web --help` 或本地启动正常；
4. MockModel 下正常完成一轮 Agent turn；
5. TUI 可以创建或恢复 session；
6. Web 可以创建 session、发送消息并收到终态；
7. 旧格式 session 可以加载、保存、rewind；
8. 用户级、项目级配置优先级与重构前一致；
9. Python 包安装后不依赖仓库当前目录碰巧可导入。

最终测试报告必须记录：命令、环境、通过数、失败数、跳过数、耗时，以及任何已知残余风险。不得只写“测试通过”。

## 11. 验收标准

### AC-ARCH-01 包分类

- 根目录业务模块显著减少；
- 所有迁移模块都有明确子系统归属；
- `tools/`、`tui/`、`web/` 原有边界保持清晰；
- 文档目录树与实际文件一致。

### AC-ARCH-02 依赖方向

- 已知循环依赖被消除；
- package 级依赖图不存在新的强连通循环；
- Core 不依赖 Runtime 或产品面；
- Runtime 不依赖 TUI/Web；
- 架构测试可以在违规时稳定失败。

### AC-ARCH-03 Agent 行为保持

- `run_agent_turn()` 稳定导入和签名保持；
- 模型调用、工具调用、权限、fallback、压缩和控制信号顺序保持；
- completed/failed/cancelled 终态与重构前一致；
- Agent 单元、集成和压力测试全部通过。

### AC-ARCH-04 数据兼容

- 旧 session、delta、checkpoint、memory 和 settings 文件可读取；
- rewind、autosave 和 session list 结果正确；
- 不因类移动导致序列化或类型识别失败；
- 配置路径、环境变量和优先级不变。

### AC-ARCH-05 产品面兼容

- CLI、Headless、TUI、Web 均可运行；
- Web 事件协议、权限交互和 session API 无意外变化；
- 不需要前端通过临时兼容逻辑猜测后端变化。

### AC-ARCH-06 测试完成

- Python 全量测试通过；
- 前端测试和生产构建通过；
- compileall、架构测试、打包测试和 `git diff --check` 通过；
- 不新增无理由 skip/xfail；
- 实现报告和测试报告完整列出结果。

## 12. 风险与控制措施

| 风险 | 典型表现 | 控制措施 |
|---|---|---|
| 重新导出未保持 monkeypatch | 测试 patch 旧路径但实现仍调用新模块原对象 | 审计 patch 路径，使用显式依赖注入或转发函数 |
| dataclass/Enum 移动破坏兼容 | 旧 session 无法加载或类型比较失败 | 保留稳定导出，增加旧数据 fixture 测试 |
| 循环依赖被延迟导入掩盖 | 启动时偶发 ImportError 或未绑定变量 | 架构测试 + 顶层导入 smoke，不以局部 import 作为默认修复 |
| 拆分改变执行顺序 | 工具、hook、事件或终态顺序变化 | characterization tests，记录事件序列并对比 |
| 大批量移动难以回滚 | 一个提交涉及几十个职责 | 一子系统一批次，每批独立测试和提交 |
| 合并用户现有改动时误覆盖 | 非本任务文件或同文件改动丢失 | 开始前记录 dirty worktree，逐文件合并，不回退未知改动 |
| 测试绿色但安装失败 | 仅因仓库根目录在 `pythonpath` 中可导入 | 增加 wheel/editable install 与 console script 冒烟 |

## 13. 文档与交付物

必须提交：

1. 本任务书；
2. 更新后的 `docs/STRUCTURE.md`；
3. 更新后的 `docs/DEVELOPMENT_GUIDELINES.md`，加入可执行的依赖规则；
4. `docs/newTask/report/MC-ARCH-PKG-20260622_IMPLEMENTATION_REPORT.md`；
5. `docs/newTask/test/MC-ARCH-PKG-20260622_TEST_REPORT.md`；
6. 旧路径到新路径的完整迁移映射表；
7. 重构前后模块数量、最大文件行数、依赖扇出和循环依赖对比；
8. 所有测试命令与实际结果。

## 14. Definition of Done

只有同时满足以下条件，任务才可标记完成：

- [ ] 目标 package 已按职责建立，目录命名清晰且文档一致；
- [ ] 已知循环依赖消失，架构测试能够阻止回归；
- [ ] `agent_loop.py`、Memory、Timeline、Session、Context 等重点模块已按职责认真拆分；
- [ ] 根目录不再承担多个子系统的平铺实现；
- [ ] 稳定入口、公共导入、配置和旧 session 保持兼容；
- [ ] 没有通过吞异常、滥用局部 import、`Any`、skip 或弱化断言掩盖问题；
- [ ] 每个迁移阶段均有测试记录；
- [ ] Python 全量测试通过；
- [ ] Web 后端、前端测试和生产构建通过；
- [ ] compileall、架构约束、打包和 diff 检查通过；
- [ ] CLI、Headless、TUI、Web 冒烟验证通过；
- [ ] 实现报告、测试报告、结构文档和迁移映射全部完成；
- [ ] 未发现 P0/P1 回归，所有残余风险均已明确记录并得到负责人确认。

在以上条件全部满足前，不得以“目录已经移动完成”或“主要功能可运行”宣布任务完成。包结构治理的完成标准是：分类清楚、依赖稳定、兼容可靠、测试完整、行为无回归。
