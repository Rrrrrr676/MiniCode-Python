# MiniCode Python 包结构

> 规范实现位于 `minicode/`。本文按 2026-06-22 第二阶段架构治理结果维护。

## 稳定入口

根目录 Python 文件严格限定为：

```text
minicode/
├── __init__.py
├── main.py
├── headless.py
├── tty_app.py
├── tooling.py
├── agent_loop.py
└── session.py
```

稳定入口与 API：

- `minicode-py`、`minicode-headless`、`minicode-web`；
- `minicode.agent_loop.run_agent_turn`；
- `minicode.memory.MemoryManager`；
- `minicode.session.SessionData`；
- `minicode.config.load_runtime_config`。

除 `agent_loop.py` 和 `session.py` 两个明确兼容入口外，旧根路径已退场。仓库内部必须直接导入目标 package。

## 当前包树

```text
minicode/
├── core/                 # 基础类型、状态、意图、token、Provider 纯原语
├── config/               # paths/settings/providers/mcp/diagnostics
├── providers/            # 注册、适配器、重试、切换、成本、Mock
├── context/
│   ├── manager.py, prompt.py, prompt_pipeline.py, layered.py, working.py
│   └── compaction/
│       ├── models.py, budgets.py, micro.py, reactive.py
│       ├── session_memory.py, dispatcher.py, service.py
│       └── micro_legacy.py, circuit_breaker.py
├── memory/
│   ├── models.py, storage.py, retrieval.py, retrieval_manager.py
│   ├── manager.py, prompt.py, pipeline.py, curator.py, injector.py
│   └── timeline/
│       ├── models.py, extractors.py, index.py, reasoner.py
│       ├── numeric_reasoning.py, event_reasoning.py
│       └── rules/{dates.py,numeric.py,travel.py,events.py}
├── persistence/
│   ├── session_models.py, session_storage.py, rewind.py
│   ├── autosave.py, formatters.py, history.py, user_profile.py
├── safety/               # permissions/auto_mode/file_review
├── integrations/         # MCP/skills/hooks/background tasks/product surfaces
├── observability/        # logging/metrics/decision audit
├── control/              # 控制、稳定性、验证、恢复、调度智能
├── runtime/
│   ├── runner.py, composition.py, prelude.py, coda.py
│   ├── control_runtime.py, lifecycle.py, model_execution.py
│   ├── tool_execution.py, policy.py, kernel.py
│   ├── routing.py, smart_routing.py, intent.py, pipeline.py
│   └── tasks/{object.py,graph.py,tracker.py}
├── cli/
│   ├── commands.py, registry.py, matching.py, handlers.py, formatters.py
│   ├── management.py, shortcuts.py, install.py
├── tools/                # 内置工具
├── tui/                  # 终端产品面
└── web/                  # Web API、Runner、事件桥接
```

## 依赖方向

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

共享的纯 Provider 识别、Intent 模型和 token 估算位于 `core`。控制层需要的调度智能位于 `control.intelligence`，反思实现位于 `memory.reflection`，避免低层反向依赖 Runtime。

## 架构护栏

`tests/test_root_package_surface.py` 和 `tests/test_architecture.py` 自动检查：

- 根目录 Python 文件严格匹配白名单；
- 内部模块不导入已删除的 71 个旧根路径；
- 分层 package 无循环；
- `core` 只依赖标准库和 core；
- Runtime 不导入 TUI/Web；
- 跨 package 不导入私有名称；
- 必须保留的稳定 API 仍可导入。

## 大模块拆分结果

| 原模块 | 拆分前 | 当前集中模块 | 主要职责 |
|---|---:|---:|---|
| `memory/timeline/reasoner.py` | 3,513 | 183 | 规则组合与公开 Reasoner |
| `memory/manager.py` | 1,986 | 521 | 记忆业务编排与维护 |
| `persistence/session_storage.py` | 1,378 | 420 | session/delta I/O |
| `context/compaction/dispatcher.py` | 1,150 | 288 | Auto Compact 策略分发 |
| `config/__init__.py` | 798 | 16 | 显式公共 API |
| `cli/commands.py` | 862 | 12 | CLI 公共 API 聚合 |
| `runtime/runner.py` | 2,052 | 1,125 | 单轮时序与 recurrent loop |

## 数据兼容

- `minicode.session` 继续同步 `MINI_CODE_DIR`/`SESSIONS_DIR`，旧 session、delta、checkpoint 和 rewind 格式不变；
- `minicode.memory` 继续导出稳定 Memory API；
- `minicode.config` 只聚合显式 API，环境变量、设置优先级和诊断语义保持；
- wheel 可在非仓库 cwd 下导入稳定 API 并运行三个 console scripts。

## 测试与构建

- `tests/`：pytest 单元、集成、压力、架构与 Web backend 测试；
- `web/`：React/Vite 前端，REST/WebSocket 协议保持；
- `pyproject.toml`：Python 包、可选依赖与三个 console scripts；
- `ts-src/`：TypeScript 参考实现，不属于 Python Runtime 依赖。
