# MiniCode Python 源码学习指南

> 面向想深入理解"类 Claude Code"项目架构的开发者。按子系统递进，每阶段 30-60 分钟精读 + 配套测试验证。

---

## 目录

- [第 0 步：全局类型与数据结构](#第-0-步全局类型与数据结构)
- [第 1 步：Agent 主循环](#第-1-步agent-主循环)
- [第 2 步：Tool Runtime](#第-2-步tool-runtime)
- [第 3 步：Session / Replay / Checkpoint / Rewind](#第-3-步session--replay--checkpoint--rewind)
- [第 4 步：Memory 设计](#第-4-步memory-设计)
- [第 5 步：模型适配层](#第-5-步模型适配层)
- [学习路线总图](#学习路线总图)

---

## 第 0 步：全局类型与数据结构

**文件：** `minicode/types.py`

这是整个项目的"词汇表"，所有核心数据结构都在这里定义。先读懂它们，后续模块的接口才能看懂。

### 关键类型

| 类型 | 说明 |
|---|---|
| `ChatMessage` | 会话消息的统一 TypedDict（支持 `system`/`user`/`assistant`/`assistant_progress`/`assistant_tool_call`/`tool_result` 六种角色） |
| `AgentStep` | 模型每一步的返回值：可以是 `assistant` 文本（含 `kind: final/progress`），也可以是 `tool_calls`（含 `calls: list[ToolCall]`） |
| `ToolCall` | 单次工具调用的结构：`id` + `toolName` + `input` |
| `ModelAdapter` | **模型适配器的 Protocol 接口**，只要求实现 `next(messages, …) -> AgentStep` |
| `RuntimeEvent` | 运行时事件，带 `category`（phase/compaction/guard/widening/recovery/stop）和 `step`/`phase`/`stop_reason` 等上下文 |

### 为什么从这里开始

`ModelAdapter` 是 Protocol 而非 ABC——任何实现了 `next()` 的对象都是合法的适配器。这个设计决定了后续 Anthropic/OpenAI/Mock 三个适配器的协作方式。`AgentStep` 的 `type` 字段（`assistant` vs `tool_calls`）直接驱动主循环的分支逻辑。

---

## 第 1 步：Agent 主循环

> 理解 **用户输入 → 模型判断 → 工具调用 → 工具结果回填 → 继续模型推理** 的完整闭环。

### 1.1 主循环入口 — `agent_loop.py`

**精读：** `run_agent_turn()` 函数（约第 726 行开始）

这是整个 Agent 循环的入口函数。核心结构：

```
run_agent_turn()
  ├── Prelude: 初始化 TurnPreludeState、CyberneticOrchestrator、各种控制器
  ├── Context pre-checks: MicroCompact → Cybernetics → Compactor → AutoCompact
  └── Recurrent Kernel (while has_remaining_steps):
        ├── begin_step() → derive_turn_step_policy()
        ├── _model_next()          ← 调用模型
        ├── 判断 next_step.type:
        │     ├── "assistant" → decide_assistant_turn()
        │     │     ├── kind=progress → 继续循环
        │     │     ├── kind=retry    → 重试
        │     │     ├── kind=fallback → widen/stop
        │     │     └── kind=final    → 返回 messages
        │     └── "tool_calls" → 并发/串行执行工具
        │           ├── ToolScheduler.schedule_calls() 分类
        │           ├── Phase 1: 并发执行只读工具
        │           ├── Phase 2: 串行执行写入工具
        │           └── 结果回填到 messages → continue
        └── 异常处理: ConnectionError/Timeout/通用异常 → fallback/compact/ModelSwitcher
```

**关键设计决策：**

- **Widening 机制**：当模型连续多次无工具调用（"空转"）时，`turn_kernel` 自动切换到 widen 模式，扩大搜索范围
- **并发工具执行**：`ToolScheduler` 根据 `is_concurrency_safe` 将工具分为并发组和串行组，只读工具（read_file、grep_files）并发跑，写入工具串行跑
- **多层异常恢复**：API 异常先尝试 reactive compact（缩减上下文重试），再尝试 ModelSwitcher fallback（切备用模型），最后才返回错误给用户

### 1.2 单轮状态机 — `turn_kernel.py`

**精读：**

- `TurnRecurrentState` — 跟踪 step 计数、工具错误计数、widening 状态、verification 状态
- `derive_turn_step_policy()` — 根据当前状态计算每步的策略（是否严格验证、是否激进压缩）
- `decide_assistant_turn()` — 模型文本输出的决策树：是 progress（继续）还是 retry（重试）还是 final（结束）还是 fallback（需要 widen/stop）
- `decide_tool_turn()` — 工具结果的决策
- `build_widening_transition_nudge()` — 生成 widen 提示注入到对话中

**关键概念：** "Widen" 是 MiniCode 的特色机制。当模型在 narrow path 上反复空转（只输出文本不调工具），系统自动注入 nudge 消息扩大模型的行为空间，而不是让用户手动干预。

### 1.3 应用状态 — `state.py`

`Store[AppState]` — 全局状态管理。`set_busy()`/`set_idle()`/`increment_tool_calls()`/`add_cost()` 等状态转换函数，通过 store 贯穿整个循环，驱动 TUI 渲染。

### 配套测试

```bash
pytest tests/test_agent_loop.py -v
pytest tests/test_turn_kernel.py -v
```

---

## 第 2 步：Tool Runtime

> 理解工具如何注册、如何执行、如何处理权限和异常。

### 2.1 工具注册与执行 — `tooling.py`

**精读：**

| 组件 | 说明 |
|---|---|
| `ToolDefinition` | 工具的四要素：`name` + `description` + `input_schema` + `validator` + `run` |
| `ToolRegistry` | 工具注册表，用 `_tool_index: dict[str, ToolDefinition]` 做 O(1) 查找 |
| `ToolRegistry.execute()` | 5 层异常保护的核心执行方法 |
| `ToolResult` | 统一返回值：`ok: bool` + `output: str` + `awaitUser: bool` |
| `ToolContext` | 执行上下文：`cwd` + `permissions` + `session` |
| `_smart_truncate_output()` | 按工具类型智能截断大输出（read_file 保留头尾、grep 保留前 N 条、run_command 保留头尾+错误行） |

**5 层异常保护（`execute()` 方法）：**

```
Layer 1: 工具未找到      → ToolResult(ok=False, "Unknown tool: xxx")
Layer 2: 输入校验失败    → ToolResult(ok=False, "Input validation error: ...")
Layer 3: 执行中崩溃      → 捕获 Exception，返回带 traceback 的 ToolResult
Layer 4: 输出过大        → _smart_truncate_output() 智能截断
Layer 5: 未知异常        → 全局兜底，绝不传播到调用方
```

任何工具崩溃都不会让整个 session 挂掉——这是 MiniCode 的核心可靠性保障。

### 2.2 内置工具实现 — `tools/` 目录

挑 3 个典型的看：

| 工具 | 文件 | 看点 |
|---|---|---|
| `read_file` | `tools/read_file.py` | 只读工具的 validator + run 模式；支持 offset/limit 分段读取 |
| `run_command` | `tools/run_command.py` | 命令执行工具的权限检查 + 超时 + 编码处理 |
| `write_file` | `tools/write_file.py` | 写入工具如何创建 checkpoint（编辑前快照） |

### 2.3 权限管理 — `permissions.py`

`PermissionManager` — 在工具执行前检查权限：

- 路径审批：是否允许访问某路径
- 命令审批：是否允许执行某命令
- Auto 模式：`AutoModeChecker` 做风险评估、prompt injection 检测、输出安全分类

### 2.4 工具执行的完整生命周期 — `agent_loop.py`

**精读：** `_execute_single_tool()`（第 369-466 行）

```
_execute_single_tool()
  ├── Pre-tool hooks: fire_hook_sync(HookEvent.PRE_TOOL_USE)
  ├── 状态更新: store.set_state(set_busy(tool_name))
  ├── 超时保护: ThreadPoolExecutor + future.result(timeout=TOOL_TIMEOUT)
  ├── 执行: tools.execute(tool_name, input, ToolContext(...))
  ├── Post-tool 状态: increment_tool_calls() → set_idle()
  ├── Post-tool hooks: fire_hook_sync(HookEvent.POST_TOOL_USE)
  └── 全局安全网: except Exception → ToolResult(ok=False, ...)
```

### 配套测试

```bash
pytest tests/test_tooling.py -v
pytest tests/test_tools/ -v
```

---

## 第 3 步：Session / Replay / Checkpoint / Rewind

> 这部分对"类 Claude Code"项目最有价值——实现会话的持久化、回放、回滚。

### 3.1 核心数据结构 — `session.py`

**精读：** `SessionData` 类

```python
@dataclass
class SessionData:
    session_id: str
    messages: list[dict]           # 完整对话消息
    transcript_entries: list[dict] # 运行时事件时间线
    checkpoints: list[FileCheckpoint]  # 文件编辑快照
    # ... 还有 skills、hooks、mcp_servers 等产品表面数据
```

`FileCheckpoint` — 文件编辑前的快照：

```python
@dataclass
class FileCheckpoint:
    checkpoint_id: str
    file_path: str        # 被编辑的文件
    existed: bool          # 编辑前文件是否存在
    previous_content: str  # 编辑前的完整内容
    kind: str              # "edit" 或 "rewind"
    group_id: str          # 按编辑组分组
```

### 3.2 增量持久化策略

**精读：** `save_session()`（第 471-553 行）

```
保存策略:
  ├── Delta Save (默认): _save_delta()
  │     └── 只写自上次保存以来新增的 messages/transcripts/checkpoints
  ├── Full Save (每 10 次 delta 或 force_full): 序列化全部数据
  └── Consolidate: 合并所有 delta 文件并清理

加载策略 (load_session):
  ├── 1. 加载基础 session JSON
  ├── 2. 扫描 delta 目录
  ├── 3. 按序号依次应用 delta（去重处理）
  └── 4. 更新 tracking counters
```

**关键细节：**
- `AutosaveManager` 每 30 秒检查一次 `_dirty` 标志，有变更就做 delta save
- Delta 文件命名 `delta_0001.json`、`delta_0002.json`... 保证顺序
- 加载时处理重叠：如果 delta 的 offset 和当前 messages 有重叠，只追加不重叠的部分

### 3.3 Rewind 机制

**精读：** `rewind_session_data()`（第 779-828 行）

```
rewind_session_data():
  ├── 1. _select_checkpoints_to_rewind(): 选择要回滚的 checkpoint
  │     ├── 按 step 数: 从末尾倒推 N 步
  │     ├── 按 checkpoint_id: 精确定位
  │     └── 按 group_id: 同一编辑组的所有文件一起回滚
  ├── 2. 创建反向 checkpoint（rewind safety）
  │     └── 记录回滚前文件的当前状态，可 undo
  ├── 3. 执行文件恢复
  │     ├── existed=True → 写回 previous_content
  │     └── existed=False → 删除文件
  └── 4. persist: save_session(force_full=True)
```

**关键设计：** 回滚不是销毁性操作——每次回滚都会先创建反向快照（`kind="rewind"`），用户可以再次回滚来 undo 回滚。这是 production-grade 的安全设计。

### 3.4 Session 查看与回放

- `format_session_inspect()` — 详细的 session 检查视图
- `format_session_replay()` — 回放导向的历史视图（checkpoint trail + transcript timeline + prompt history）
- `format_rewind_preview()` — Dry-run 预览哪些文件会被恢复
- `format_session_list()` — 所有 session 的摘要列表

### 配套测试

```bash
pytest tests/test_session.py -v
```

---

## 第 4 步：Memory 设计

> 理解工作记忆、项目记忆、记忆注入、上下文压缩的完整链路。

### 4.1 记忆层级模型 — `memory.py` 前半部分

**三层作用域（`MemoryScope`）：**

| 层级 | 存储位置 | 生命周期 |
|---|---|---|
| `USER` | `~/.mini-code/memory/` | 跨项目持久 |
| `PROJECT` | `.mini-code-memory/` | 项目内共享，可 Git 版本化 |
| `LOCAL` | `.mini-code-memory-local/` | 项目本地，不提交 |

**四级时间层级（`MemoryTier`），仿人类记忆模型：**

| 层级 | 保留时间 | 状态 |
|---|---|---|
| `WORKING` | 当前 session | 完整细节，快速访问 |
| `SHORT_TERM` | < 7 天 | 完整细节 |
| `LONG_TERM` | < 30 天 | 已压缩整合 |
| `ARCHIVAL` | 永久 | 重度摘要 |

### 4.2 记忆搜索 — BM25 + 多信号融合

**精读：** `MemoryFile.search()` 方法

打分公式（多信号融合）：

```
final_score = BM25 * 0.7 + Domain_Jaccard * 0.3   # 内容相关性
            + log1p(usage_count) * 0.3             # 使用频次加成
            + 1/(1 + age_hours/24) * 0.5           # 新近度加成

其中 BM25 又叠加:
  + substring_score (精确匹配 +2.0, 部分匹配 +1.0)
  + tag_score (精确 tag 匹配 +5.0, 部分匹配 +1.5)
```

**领域感知搜索：** 支持 `active_domains` 参数（如 `["frontend", "testing"]`），对匹配领域的记忆做 soft boosting，而非硬过滤。

**代码术语扩展：** `_CODE_TERM_EXPANSIONS` 字典支持中英文代码术语的双向扩展（如 "函数" ↔ "function"/"func"/"method"），还有按领域（frontend/backend/database/devops/testing）的术语扩展。

### 4.3 MemoryManager — `memory.py` 中段

**精读：** `MemoryManager` 类

核心方法：
- `add_entry()` — 自动分类（`_auto_classify_content` 用关键词启发式判断类别）
- `search()` — 跨 scope 搜索 + 去重 + 最小相关性阈值
- `get_relevant_context()` — 为 system prompt 注入准备格式化文本，token 预算感知
- `handle_user_memory_input()` — 解析 `# remember ...` 和 `/memory add ...` 指令
- `compress_scope()` — Jaccard 相似度合并重复记忆
- `decay_memories()` — 时间衰减（超过 30 天未更新 → usage_count 减半）
- `promote_memories()` — 层级升降：使用次数 ≥5 → LONG_TERM；30 天未访问 → ARCHIVAL；再次访问 → 复活到 SHORT_TERM
- `link_memories()` — 内容相似的记忆自动建立关联图
- `detect_conflicts()` — 检测新记忆与已有记忆的潜在冲突

**数据完整性保障：**
- `_atomic_write()` — 先写临时文件再 `os.replace()`，防止写一半崩溃
- `_validate_memory_data()` — 加载时校验 JSON 结构和字段
- `_recover_entries()` — 损坏文件的自动恢复（创建 `.bak` 备份 + 只加载有效条目）
- 内存中 `content` 强制为 `str`（8+ 个调用点都用 `.lower()`/`.strip()`/`[:N]`）

### 4.4 工作记忆 — `working_memory.py`

`protect_context()` — 标记关键上下文在 compaction 时不应被丢弃。

例如：模型刚输出的 final answer、用户的重要指令、关键决策——这些会被 `protect_context()` 保护起来，compaction 引擎会跳过它们。

### 4.5 记忆注入 — `memory_injector.py`

`MemoryInjector` — 在每个 agent turn 开始时工作：

```
run_agent_turn() → MemoryInjector.inject_for_task(task_description)
  ├── 1. 用 task description 搜索相关记忆
  ├── 2. MemoryInjectionController 决定注入策略
  │     ├── mode: aggressive / normal / conservative / disabled
  │     ├── max_memories: 注入多少条
  │     └── min_relevance: 相关性阈值
  └── 3. 格式化为 "## Injected Memory" 追加到 system prompt
```

注入策略由 `MemoryInjectionController` 根据上下文压力动态决定——上下文越满，注入越保守。

### 4.6 上下文压缩 — `context_compactor.py` + `micro_compact.py` + `circuit_breaker.py`

**三层防御体系：**

```
Layer 1: MicroCompactor   — 最轻量，裁剪旧工具结果（按时间/预算）
Layer 2: ContextCompactor — 去重 + 摘要 + session summary 生成
Layer 3: AutoCompact      — 上下文接近上限时的激进压缩

每层由 CompactionCircuitBreaker 保护：
  - 连续失败 >= failure_threshold → 禁用该层
  - 成功后记录 → 计数归零
  - 支持自动重置
```

**`ContextCompactor` 的子组件：**
- `ToolResultBudgetManager` — 按消息限制工具输出 token 预算
- `ReadDedupManager` — 同一文件的重复读取去重

### 配套测试

```bash
pytest tests/test_memory.py -v
pytest tests/test_context_compactor.py -v
```

---

## 第 5 步：模型适配层

> 理解 OpenAI / Anthropic / Mock 的 provider adapter 抽象与工厂模式。

### 5.1 抽象接口 — `types.py`

```python
class ModelAdapter(Protocol):
    def next(
        self,
        messages: list[ChatMessage],
        on_stream_chunk: Callable[[str], None] | None = None,
        store: Any | None = None,
    ) -> AgentStep: ...
```

**关键设计：** `ModelAdapter` 是 `Protocol`（结构化子类型），不是 `ABC`。任何实现了 `next()` 方法的对象都是合法的适配器——不需要显式继承。这让 Mock 和测试用例的实现成本降到最低。

### 5.2 Provider 检测与配置 — `model_registry.py`

**精读顺序：**

| 顺序 | 组件 | 说明 |
|---|---|---|
| 1 | `Provider` enum | 五种 provider：ANTHROPIC / OPENAI / OPENROUTER / CUSTOM / MOCK |
| 2 | `detect_provider()` | 根据 model 名称 + 环境变量自动检测 provider |
| 3 | `build_provider_config()` | 构建 `ProviderConfig`（base_url + api_key + headers），统一四种 provider 的配置 |
| 4 | `create_model_adapter()` | **工厂函数**——唯一入口，根据 provider 类型创建对应的 adapter |
| 5 | `ModelSelectionController` | 控制论模型选择器，根据任务复杂度/预算/延迟推荐模型 |

**`create_model_adapter()` 工厂逻辑：**

```python
def create_model_adapter(model, tools, runtime, force_mock):
    if force_mock or MINI_CODE_MODEL_MODE == "mock":
        return MockModelAdapter()

    config = build_provider_config(model, runtime)

    if config.is_openai_compatible:  # OPENAI / OPENROUTER / CUSTOM
        return OpenAIModelAdapter(enriched_runtime, tools)

    # Default: Anthropic
    return AnthropicModelAdapter(enriched_runtime, tools)
```

**关键：** OpenAI/OpenRouter/Custom 三种 provider 共用同一个 `OpenAIModelAdapter`，通过 `ProviderConfig` 区分 endpoint。

### 5.3 Anthropic Adapter — `anthropic_adapter.py`

原生 Anthropic Messages API 适配器：

- 流式响应解析（SSE events: `message_start`/`content_block_delta`/`message_delta`/`message_stop`）
- 工具调用解析（`tool_use` content block → `AgentStep(type="tool_calls")`）
- 文本响应解析（`text` content block → `AgentStep(type="assistant")`）
- Thinking/Extended Thinking 支持
- 缓存计费（`cache_creation_input_tokens`/`cache_read_input_tokens`）
- 指数退避重试（配合 `api_retry.py`）

### 5.4 OpenAI Adapter — `openai_adapter.py`

OpenAI Chat Completions API 适配器（同时覆盖 OpenRouter 和 Custom endpoint）：

- 请求转换：内部 Anthropic-格式 messages → OpenAI-格式 messages
- 工具格式双向转换：Anthropic `tools[]` ↔ OpenAI `tools[]` + `tool_calls`
- 流式响应解析（SSE: `choices[0].delta`）
- 计费追踪（按模型定价）
- OpenRouter 特殊头（`HTTP-Referer`/`X-Title`）

### 5.5 Mock Adapter — `mock_model.py`

`MockModelAdapter` — 测试用，基于关键字的脚本化响应：

```
输入 "/ls"      → 返回 list_files 工具调用
输入 "/grep X"  → 返回 grep_files 工具调用
输入 "/read"    → 返回 read_file 工具调用
输入 tool_result → 返回包含工具结果的 assistant 文本
```

无需真实 API key，被所有测试用例和 CI 使用。

### 5.6 运行时切换 — `model_switcher.py` + `api_retry.py`

- `ModelSwitcher` — 运行时热切换模型，维护 fallback 链。当 API 调用失败时自动切换到备用模型
- `api_retry.py` — 可重试状态判定（5xx / 429 / 网络错误），指数退避（含 jitter），Retry-After 头解析

### 配套测试

```bash
pytest tests/test_model_registry.py -v
pytest tests/test_anthropic_adapter.py -v
pytest tests/test_openai_adapter.py -v
```

---

## 学习路线总图

```
                    types.py（词汇表）
                         ↓
              agent_loop.py ──→ turn_kernel.py
              （主循环）           （状态机 + widen）
                         ↓
              tooling.py ──→ tools/ ──→ permissions.py
            （工具注册执行）  （内置工具）   （权限管理）
                         ↓
                   session.py
           （持久化 + checkpoint + rewind）
                         ↓
   memory.py ──→ working_memory.py ──→ memory_injector.py ──→ context_compactor.py
  （三层四级记忆） （工作记忆保护）        （记忆注入）            （上下文压缩）
                         ↓
   model_registry.py ──→ anthropic_adapter.py ──→ openai_adapter.py ──→ mock_model.py
   （工厂+Provider解析）   （Anthropic API）       （OpenAI API）          （测试Mock）
```

### 建议学习节奏

| 阶段 | 预计时间 | 核心文件数 |
|---|---|---|
| 第 0 步：类型 | 15 分钟 | 1 |
| 第 1 步：主循环 | 60 分钟 | 3 |
| 第 2 步：工具 | 45 分钟 | 3+ |
| 第 3 步：会话 | 45 分钟 | 1 |
| 第 4 步：记忆 | 60 分钟 | 5 |
| 第 5 步：适配器 | 60 分钟 | 6 |
| **合计** | **约 5 小时** | **~20** |

### 每阶段的学习方法

1. **先读文件顶部的 docstring 和导入**，了解模块职责和依赖关系
2. **精读核心类/函数**（上面标注了行号），边读边做笔记
3. **运行配套测试**，看测试用例如何调用这些接口
4. **用 `pytest --pdb` 打断点**单步调试一个完整 turn 的执行流程
5. **回头看调用方**——例如读完 `ToolRegistry.execute()` 后去 `agent_loop.py` 看 `_execute_single_tool()` 如何调用它

---

## 架构速查

以下是在学习过程中可能反复查阅的关键关系：

| 模块 | 被谁调用 | 调用谁 |
|---|---|---|
| `agent_loop.py` | `main.py`/`headless.py`/`web/runner.py` | `tooling.py`, `turn_kernel.py`, `model_registry.py`, `memory_injector.py`, `context_compactor.py` |
| `tooling.py` | `agent_loop.py` | `tools/*.py` |
| `turn_kernel.py` | `agent_loop.py` | （纯逻辑，无外部依赖） |
| `session.py` | `agent_loop.py`（通过 autosave），`cli_commands.py` | 文件系统 |
| `memory.py` | `memory_injector.py`, `agent_loop.py` | 文件系统 |
| `model_registry.py` | `agent_loop.py`（`create_model_adapter`） | `anthropic_adapter.py`, `openai_adapter.py`, `mock_model.py` |
| `types.py` | 所有模块 | 无 |

---

> **最后更新：** 2026-06-19
> **适配代码版本：** `minicode/` 包当前 `main` 分支
