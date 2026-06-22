# MiniCode 根兼容门面清理与超大模块物理拆分任务书

| 项目 | 内容 |
|---|---|
| 文档日期 | 2026-06-22 |
| 任务编号 | `MC-ARCH-CLEAN-20260622` |
| 基线提交 | `5f5b607 refactor: establish Python package boundaries` |
| 任务名称 | 根目录兼容门面退场、内部导入迁移与超大模块物理职责拆分 |
| 任务性质 | 行为保持型架构治理第二阶段 |
| 优先级 | P0 |
| 建议工期 | 6–10 个工作日，按子系统独立提交与验收 |
| 影响范围 | `minicode/`、`tests/`、`docs/`、打包与入口配置 |
| 当前基础 | 第一阶段完成度 84%，Python 1180 passed，前端 28 passed |

## 1. 背景

第一阶段已经建立 `core/`、`config/`、`providers/`、`context/`、`memory/`、`persistence/`、`control/`、`runtime/` 等目标 package，并消除了已知 package 循环依赖。

但为保留旧导入和 monkeypatch 语义，`minicode/` 根目录仍保留约 73 个兼容门面。真实实现虽然已经迁入子包，IDE 目录仍表现为大量平铺 Python 文件，且仓库内部代码仍有不少旧路径导入。

同时以下超大模块主要完成了“归包”，尚未完成任务书要求的“物理职责拆分”：

| 模块 | 当前规模 | 主要问题 |
|---|---:|---|
| `memory/timeline/reasoner.py` | 约 3,513 行 | 模型、提取、评分、日期/数值/旅行/事件规则仍集中 |
| `runtime/runner.py` | 约 2,052 行 | 总编排仍直接协调过多服务 |
| `memory/manager.py` | 约 1,986 行 | 模型、校验、存储、检索、编排、格式化混合 |
| `persistence/session_storage.py` | 约 1,378 行 | 模型、I/O、delta、rewind、autosave、format 混合 |
| `context/compaction/dispatcher.py` | 约 1,150 行 | models、budget、dedup、reactive、dispatcher 混合 |
| `context/manager.py` | 约 971 行 | 状态、统计、摘要和持久化仍耦合 |
| `cli/commands.py` | 约 862 行 | 命令注册、匹配、处理、格式化混合 |
| `config/__init__.py` | 约 798 行 | package API 与所有配置实现混合 |

本任务的目标不是再次移动文件，而是让根目录真正干净，并让目标子模块承载真实实现。

## 2. 任务目标

完成后必须达到：

1. 仓库内部不再导入非稳定的根兼容门面；
2. 删除约 70 个非必要根兼容文件；
3. `minicode/` 根目录只保留稳定入口、明确兼容面和既有产品边界；
4. 不使用 import hook、动态 `sys.modules` 注册表或隐藏目录伪装根目录清理；
5. Timeline、Memory、Session、Compaction、Config、CLI 和 Runtime runner 完成真实物理拆分；
6. 旧 session、配置、三个 console scripts 和任务书明确的稳定 Python API 保持兼容；
7. package 依赖图无循环，Runtime 直接依赖和文件规模显著下降；
8. Python、Web、前端、构建、wheel 和入口冒烟全部通过；
9. 每个子系统独立提交，任何失败先在当前批次收敛。

## 3. 根目录最终白名单

最终 `minicode/` 根目录允许存在的 Python 文件：

```text
minicode/
├── __init__.py
├── main.py
├── headless.py
├── tty_app.py
├── tooling.py
├── agent_loop.py      # 稳定兼容入口，仅转发 runtime.runner
└── session.py         # 稳定兼容入口，仅转发 persistence 公共 API
```

`config` 和 `memory` 已是 package，以 package 名保持稳定 API，不需要恢复根 `config.py` 或 `memory.py`。

以下文件不得以“兼容”为由继续留在根目录：

- Provider、Context、Control、Safety、Integration、Observability、CLI 实现或门面；
- `types.py`、`state.py`、`workspace.py` 等已迁入 Core 的门面；
- `timeline_memory.py`、`context_manager.py`、`context_compactor.py` 等数据子系统门面；
- `task_*`、`agent_*`、`cybernetic_*` 等 Runtime/Control 门面。

新增 `tests/test_root_package_surface.py`，通过白名单稳定阻止根目录再次膨胀。

## 4. 必须保留的稳定兼容面

以下入口必须继续可用：

```text
minicode-py
minicode-headless
minicode-web
minicode.agent_loop.run_agent_turn
minicode.memory.MemoryManager
minicode.session.SessionData
minicode.config.load_runtime_config
```

还必须保持：

- `run_agent_turn()` 签名、callback 顺序、返回值、异常与终态语义；
- 旧 session/delta/checkpoint JSON 可加载、保存与 rewind；
- 配置环境变量、优先级、默认值与诊断含义；
- TUI、Headless、Web 行为和事件协议；
- 已安装 wheel 在非仓库 cwd 下正常导入和运行。

非上述稳定 API 的旧根路径不继续无限期兼容。删除前必须完成仓库内部调用审计，并在迁移表中记录新路径。

## 5. 重构红线

### 5.1 不允许“视觉清理”代替架构清理

- 禁止用 `MetaPathFinder`、全局 import hook 或集中 `sys.modules` 别名隐藏旧模块；
- 禁止把 70 个根门面原样搬进 `compat/` 后继续让内部代码依赖旧路径；
- 禁止通过 IDE exclude、文件名改后缀或文档解释掩盖平铺实现；
- 删除门面前必须先迁移内部导入和 monkeypatch。

### 5.2 不允许一次删除全部门面

- 每个批次只清理一个领域或一条依赖链；
- 当前批次定向测试和全局入口测试未通过前，不开始下一批；
- 不在同一批同时删除 Provider、Memory、Session、CLI 全部门面；
- 每批必须有独立 Git commit，保证可审查和可回退。

### 5.3 不允许借拆分改变行为

- 不改变 Agent、工具、权限、fallback、重试、压缩、token 或成本语义；
- 不修改 Memory 检索排序、Timeline 证据和推理答案；
- 不修改 Session ID、目录、delta、checkpoint、rewind 和格式文本核心含义；
- 不降低测试断言、不新增无理由 skip/xfail；
- 不通过扩大 `try/except`、局部 import、`Any` 或字符串转发掩盖依赖问题。

### 5.4 保护现有工作区

基线提交后仍存在未提交的用户改动和本地目录。每批开始前必须记录 `git status --short`，不得提交或回退非本任务文件。

## 6. 依赖与导入迁移规则

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

迁移必须遵守：

1. 内部代码直接导入目标 package，不经过根门面；
2. 测试 monkeypatch 应 patch 实际查找位置，而不是已删除的旧定义位置；
3. 若 patch 路径难以稳定，优先增加显式依赖参数或依赖对象；
4. 跨 package 只导入公共名称，不新增 `_private_name`；
5. `core` 只依赖标准库和 `core` 内部模块；
6. Provider 只依赖纯 token 能力，不导入 ContextManager；
7. Runtime 不导入 TUI/Web；领域包不导入 `runtime.runner`；
8. Memory/Context 通过窄接口交互，不导入彼此内部实现；
9. 文件移动后禁止保留错误的相对导入；
10. 架构测试必须同时检查文件系统白名单、AST 导入和 package 循环。

## 7. 分阶段实施计划

### 阶段 0：冻结第二阶段基线

实施内容：

1. 确认基线提交为 `5f5b607`；
2. 记录未提交用户改动；
3. 运行 Python 全量、前端测试、构建和三个入口；
4. 生成全部根门面、内部旧路径导入和 monkeypatch 清单；
5. 新增根目录最终白名单测试，先以预期失败或迁移期允许表运行。

退出条件：基线绿色，删除候选文件和引用位置全部可追踪。

建议提交：

```text
test(arch): inventory legacy root facades and define final root allowlist
```

### 阶段 1：Provider、Observability 与 Safety 门面退场

迁移范围：

- `model_registry.py`、`model_switcher.py`；
- `openai_adapter.py`、`anthropic_adapter.py`、`api_retry.py`、`mock_model.py`、`cost_tracker.py`；
- `logging_config.py`、`agent_metrics.py`、`decision_audit.py`；
- `permissions.py`、`auto_mode.py`、`file_review.py`。

实施步骤：

1. 运行代码改用 `providers.*`、`observability.*`、`safety.*`；
2. 测试 import 和 monkeypatch 改到真实查找位置；
3. 对模型工厂、权限存储路径等可变依赖增加窄依赖入口；
4. 删除上述根门面；
5. 运行 Provider/Config/Safety/Tools/Agent fallback 测试。

退出条件：对应根文件不存在，定向测试与入口测试绿色。

建议提交：

```text
refactor(providers): migrate internal imports and remove provider root facades
```

### 阶段 2：Control 与 Runtime 辅助门面退场

迁移范围：

- `cybernetic_*`、`*_controller.py`、`adaptive_pid_tuner.py`；
- `state_observer.py`、`stability_monitor.py`、`self_healing_engine.py`、`cost_control.py`；
- `agent_intelligence.py`、`agent_router.py`、`agent_reflection.py`；
- `turn_kernel.py`、`pipeline_engine.py`、`smart_router.py`、`intent_parser.py`；
- `task_object.py`、`task_graph.py`、`task_tracker.py`、`capability_registry.py`；
- `runtime_profiles.py`、`runtime_profile_eval.py`、`release_readiness.py`、`product_surfaces.py`。

必须保留 `agent_loop.py`，但内容不得超过稳定转发所需逻辑。

退出条件：Runtime/Control 内部只使用 `runtime.*`、`control.*` 目标路径；相关门面全部删除；控制与压力测试绿色。

建议拆为两个提交：

```text
refactor(control): remove legacy control module facades
refactor(runtime): remove legacy runtime helper facades
```

### 阶段 3：Context、Memory、Persistence 门面退场

迁移范围：

- `context_manager.py`、`context_compactor.py`、`micro_compact.py`、`circuit_breaker.py`；
- `layered_context.py`、`working_memory.py`、`prompt.py`、`prompt_pipeline.py`；
- `timeline_memory.py`、`memory_pipeline.py`、`memory_curator_agent.py`；
- `memory_injector.py`、`memory_reranker.py`、`vector_memory.py`、`domain_classifier.py`；
- `history.py`、`user_profile.py`。

必须保留：

- `memory/` package 的稳定 API；
- 根 `session.py` 稳定兼容面。

退出条件：数据子系统定向测试、旧 session fixture、Memory/Timeline 答案和排序测试绿色。

建议拆为三个提交：

```text
refactor(context): remove legacy context facades
refactor(memory): remove legacy memory facades
refactor(persistence): remove legacy persistence facades
```

### 阶段 4：Integration 与 CLI 门面退场

迁移范围：

- `mcp.py`、`skills.py`、`hooks.py`、`background_tasks.py`；
- `cli_commands.py`、`manage_cli.py`、`local_tool_shortcuts.py`、`install.py`。

重点风险：

- MCP 测试使用私有 helper；迁移后应改为目标模块测试，不能为测试保留根门面；
- CLI/TUI 测试广泛 monkeypatch 命令模块；应 patch `cli.commands` 的实际查找位置；
- TUI navigation 和 input handler 必须改用 `cli` package 公共 API。

退出条件：根目录只剩白名单文件；`tests/test_root_package_surface.py` 由迁移期模式切换为严格模式。

建议提交：

```text
refactor(integrations): remove extension root facades
refactor(cli): migrate command consumers and remove CLI root facades
```

### 阶段 5：Timeline Memory 物理拆分

目标结构：

```text
memory/timeline/
├── models.py
├── extractors.py
├── index.py
├── reasoner.py
└── rules/
    ├── dates.py
    ├── numeric.py
    ├── travel.py
    └── events.py
```

拆分要求：

1. dataclass 与索引模型进入 `models.py`；
2. record/semantic extraction 进入 `extractors.py`；
3. tokenize、score、context selection 进入 `index.py`；
4. StateReasoner 只编排稳定规则接口；
5. 日期、数值、旅行和事件启发式进入独立规则文件；
6. 不改变答案、证据 ID、排序、置信度和 insufficient-information 判断。

规模目标：

- `reasoner.py` 建议不超过 1,000 行；
- 单个 rules 文件建议不超过 700 行；
- 不以机械行数替代职责完整性。

退出条件：Timeline 全量样例完全一致，文件职责清晰。

### 阶段 6：Memory 与 Session 物理拆分

#### Memory

必须把真实实现拆到：

- `memory/models.py`：Scope、Tier、Entry、File、Paths；
- `memory/storage.py`：JSON 校验、恢复、原子写入、路径；
- `memory/retrieval.py`：tokenize、BM25、TF-IDF、query expansion；
- `memory/manager.py`：业务编排；
- `memory/prompt.py`：注入与格式化。

#### Session

必须把真实实现拆到：

- `persistence/session_models.py`；
- `persistence/session_storage.py`；
- `persistence/rewind.py`；
- `persistence/autosave.py`；
- `persistence/formatters.py`。

规模目标：

- `memory/manager.py` 建议不超过 750 行；
- `session_storage.py` 建议不超过 650 行；
- formatters、rewind、autosave 可独立测试。

退出条件：Memory 检索/持久化和旧 session/delta/rewind 全部通过。

### 阶段 7：Compaction、Config 与 CLI 物理拆分

#### Compaction

- models → `compaction/models.py`；
- budget → `compaction/budgets.py`；
- dedup/micro → `compaction/micro.py`；
- reactive → `compaction/reactive.py`；
- dispatcher 只保留策略选择和编排。

#### Config

`config/__init__.py` 只作为显式公共 API，真实实现进入：

- `paths.py`；
- `settings.py`；
- `providers.py`；
- `mcp.py`；
- `diagnostics.py`。

#### CLI

拆分：

- 命令定义/注册；
- 匹配与补全；
- session/config/model/mcp/extension handler；
- 展示格式化。

退出条件：配置优先级、slash command、补全和诊断行为不变；集中模块规模显著下降。

### 阶段 8：Runtime runner 收敛

目标：让 `runtime.runner.run_agent_turn()` 只承担组合和时序编排。

优先提取：

- work-chain/task prelude；
- context/memory/control 组合初始化；
- recurrent step driver；
- concurrent tool batch collection；
- coda/report/terminal-state 收口。

要求：

- 通过显式依赖对象或组合根注入服务；
- 不新增领域包→runner 反向依赖；
- callback 和事件顺序使用 characterization test 固定；
- `runner.py` 建议收敛到 1,200 行以内。

退出条件：Agent 单元、集成、压力、Headless、TUI、Web Runner 全部绿色。

### 阶段 9：最终清理与验收

1. 严格执行根目录白名单；
2. 检查不存在旧根路径内部导入；
3. 检查 package 循环、跨层私有导入和 Runtime→UI 依赖；
4. 隔离构建与安装 wheel；
5. 执行三个 console script、MockModel、TUI、Web、旧 session 冒烟；
6. 更新 `STRUCTURE.md`、开发规范、实现报告和测试报告；
7. 输出第二阶段完整迁移映射和删除清单。

## 8. 自动化架构测试要求

`tests/test_architecture.py` 与新增测试至少覆盖：

```text
test_root_python_files_match_allowlist
test_internal_modules_do_not_import_legacy_root_facades
test_layered_packages_have_no_import_cycles
test_core_depends_only_on_standard_library
test_runtime_never_imports_tui_or_web
test_cross_package_imports_do_not_use_private_names
test_required_legacy_public_imports_still_work
```

门面清理期间可以使用显式的迁移期 allowlist，但每完成一个批次必须缩小；禁止使用永不收敛的通配 allowlist。

## 9. 测试矩阵

### 每批最小检查

```bash
.venv/bin/python -m compileall -q minicode
.venv/bin/python -m pytest -q tests/test_architecture.py tests/test_root_package_surface.py
.venv/bin/python -m pytest -q tests/test_packaging.py tests/test_main.py tests/test_headless.py
git diff --check
```

### 门面清理定向测试

| 批次 | 必跑测试 |
|---|---|
| Provider | `test_config.py`、`test_model_switching.py`、两个 adapter、retry、cost |
| Safety/Observability | `test_permissions.py`、`test_tools.py`、`test_logging*.py` |
| Control/Runtime | Agent loop/flow/stress、cybernetic、turn kernel、integration |
| Context | compactor、cybernetics、robustness、micro、TS ported |
| Memory/Timeline | `test_memory_*`、domain、timeline、stress、e2e |
| Session | session、main、tools、release integration、Web runner |
| Integration/CLI | MCP、skills、hooks、background tasks、CLI、TUI |

### 最终验收

```bash
env PATH="$PWD/.venv/bin:/usr/bin:/bin" .venv/bin/python -m pytest -q

cd web
npm test -- --run
npm run build

cd ..
.venv/bin/python -m pip wheel . --no-deps --no-build-isolation -w /tmp/minicode-wheel
git diff --check
```

还必须验证：

- `minicode-py --help`；
- `minicode-headless --help`；
- `minicode-web --help`；
- 从非仓库 cwd 导入稳定 API；
- MockModel 完成一轮 Agent turn；
- TUI 创建/恢复 session；
- Web 创建 session、发送消息并收到终态；
- 旧 session、delta、checkpoint、rewind；
- 用户级/项目级配置优先级。

## 10. 提交策略

禁止把本任务做成一个巨型提交。建议最少拆为：

1. 架构 inventory 与 root allowlist；
2. Provider/Observability/Safety 门面清理；
3. Control 门面清理；
4. Runtime 辅助门面清理；
5. Context 门面清理；
6. Memory/Persistence 门面清理；
7. Integration/CLI 门面清理；
8. Timeline 物理拆分；
9. Memory 物理拆分；
10. Session 物理拆分；
11. Compaction/Config/CLI 物理拆分；
12. Runner 收敛；
13. 最终文档与验收。

每个提交信息必须记录定向测试结果；当前批次失败时不得继续叠加下一批。

## 11. 风险与控制

| 风险 | 控制措施 |
|---|---|
| 删除门面导致 import error | 全仓 AST/rg 审计，先迁移后删除，入口 smoke |
| monkeypatch 命中新旧不同对象 | patch 实际查找位置或显式注入依赖 |
| 模块级 registry/path 状态丢失 | 把状态所有权放入目标模块并增加 identity/state 测试 |
| dataclass/Enum 移动破坏持久化 | 保留模型定义位置或增加旧 fixture 兼容测试 |
| 相对 import 因移动改变解析 | 使用明确公共绝对路径，compileall + import smoke |
| 拆分改变顺序/排序/预算 | characterization tests 固定事件、答案、排序和统计 |
| 根目录表面干净但隐藏兼容层 | 禁止 import hook/sys.modules 集中别名；架构测试检查 |
| 大批改动难审查 | 一领域一提交，失败停止扩散 |
| 误提交用户工作区改动 | 每批记录 status，显式 stage 文件，不使用 `git add -A` |

## 12. 交付物

必须提交：

1. 本任务书；
2. `tests/test_root_package_surface.py`；
3. 更新后的 `tests/test_architecture.py`；
4. 根兼容门面删除清单；
5. 旧路径→新路径最终迁移表；
6. 超大模块拆分前后职责与行数对比；
7. `docs/STRUCTURE.md` 与开发规范；
8. 第二阶段实现报告；
9. 第二阶段测试报告；
10. 全部测试命令、通过数、失败数、跳过数和耗时。

建议报告路径：

```text
docs/newTask/report/MC-ARCH-CLEAN-20260622_IMPLEMENTATION_REPORT.md
docs/newTask/test/MC-ARCH-CLEAN-20260622_TEST_REPORT.md
```

## 13. 验收标准

### AC-CLEAN-01 根目录

- 根目录 Python 文件与白名单完全一致；
- 不存在业务实现或非必要兼容门面；
- IDE 展开 `minicode/` 时能直接看出子系统边界。

### AC-CLEAN-02 内部导入

- 仓库内部不导入已删除旧路径；
- monkeypatch 指向真实查找位置；
- 不存在隐藏兼容 import hook；
- 跨 package 不导入私有名称。

### AC-CLEAN-03 大模块拆分

- Timeline、Memory、Session、Compaction、Config、CLI 的目标模块包含真实实现；
- API 聚合文件不再承载大段业务实现；
- `runtime.runner` 明显收敛；
- 文档与物理文件一致。

### AC-CLEAN-04 架构

- package 依赖图无循环；
- Core、Runtime、产品面依赖方向满足规则；
- 架构测试能稳定阻止根目录和循环回归。

### AC-CLEAN-05 兼容与测试

- 任务书明确的稳定入口全部可用；
- 旧 session、配置、Memory 行为不变；
- Python、Web、前端、构建、wheel、入口全部通过；
- 无新增无理由 skip/xfail；
- 不存在 P0/P1 回归。

## 14. Definition of Done

只有同时满足以下条件才能标记完成：

- [ ] 根目录 Python 文件严格符合最终白名单；
- [ ] 约 70 个非必要兼容门面已删除；
- [ ] 仓库内部不再依赖已删除根路径；
- [ ] 未使用 import hook 或集中模块别名伪装清理；
- [ ] Timeline 已按 models/extractors/index/reasoner/rules 物理拆分；
- [ ] Memory 已按 models/storage/retrieval/manager/prompt 物理拆分；
- [ ] Session 已按 models/storage/rewind/autosave/formatters 物理拆分；
- [ ] Compaction、Config、CLI 已完成真实职责拆分；
- [ ] Runtime runner 已收敛且事件/终态无变化；
- [ ] 已知循环为零，架构测试阻止回归；
- [ ] 稳定入口、旧 session 和配置兼容；
- [ ] Python 全量测试通过；
- [ ] Web/前端测试与构建通过；
- [ ] wheel 隔离安装和三个 console script 通过；
- [ ] `git diff --check` 通过；
- [ ] 每个阶段有独立提交和测试记录；
- [ ] 实现报告、测试报告、迁移表和结构文档完整。

在以上条件全部满足前，不得以“IDE 看起来更整洁”“文件已经移动”或“主要测试通过”宣布任务完成。
