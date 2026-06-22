# MiniCode Python 包结构

> 规范实现位于仓库根目录 `minicode/`。本文按 2026-06-22 的包治理结果维护。

## 稳定入口与兼容层

`main.py`、`headless.py`、`tty_app.py`、`tooling.py`、`tools/`、`tui/`、`web/` 保持稳定产品入口或既有边界。根目录其余同名模块主要是旧 Python 导入路径的兼容门面；兼容门面通过模块身份别名保持 monkeypatch 和模块级可变状态语义。

稳定入口：

- `minicode-py` → `minicode.main:main`
- `minicode-headless` → `minicode.headless:main`
- `minicode-web` → `minicode.web.cli:main`
- `minicode.agent_loop.run_agent_turn`
- `minicode.memory.MemoryManager`
- `minicode.session.SessionData`
- `minicode.config.load_runtime_config`

## 当前包树

```text
minicode/
├── main.py, headless.py, tty_app.py, agent_loop.py
├── tooling.py, tools/, tui/, web/
├── core/
│   ├── types.py, state.py, events.py, errors.py, workspace.py
├── config/
│   ├── __init__.py, paths.py, settings.py, providers.py, mcp.py, diagnostics.py
├── providers/
│   ├── spec.py, registry.py, openai.py, anthropic.py, retry.py
│   ├── switching.py, fallbacks.py, cost.py, mock.py
├── context/
│   ├── tokens.py, manager.py, prompt.py, prompt_pipeline.py
│   ├── layered.py, working.py
│   └── compaction/
│       ├── dispatcher.py, models.py, budgets.py, reactive.py
│       ├── micro.py, micro_legacy.py, circuit_breaker.py
├── memory/
│   ├── manager.py, models.py, storage.py, retrieval.py, prompt.py
│   ├── pipeline.py, curator.py, injector.py, reranker.py, vector.py, domain.py
│   └── timeline/
│       ├── reasoner.py, models.py, extractors.py, index.py, rules/
├── persistence/
│   ├── session_storage.py, session_models.py, rewind.py, formatters.py
│   ├── history.py, user_profile.py
├── safety/
│   ├── permissions.py, auto_mode.py, file_review.py
├── integrations/
│   ├── mcp.py, skills.py, hooks.py, background_tasks.py
├── observability/
│   ├── logging.py, metrics.py, decision_audit.py
├── control/
│   ├── orchestrator.py, supervisor.py, feedback.py, feedforward.py
│   ├── predictive.py, context.py, cost.py, stability.py, verification.py
│   ├── recovery.py, adaptive_pid.py, state_observer.py, decoupling.py
│   ├── progress.py, ablation.py
├── runtime/
│   ├── runner.py, lifecycle.py, model_execution.py, tool_execution.py, policy.py
│   ├── kernel.py, intelligence.py, routing.py, reflection.py, pipeline.py
│   ├── smart_routing.py, intent.py, capabilities.py, profiles.py
│   ├── profile_eval.py, release_readiness.py, product_surfaces.py
│   └── tasks/{object.py,graph.py,tracker.py}
└── cli/
    ├── commands.py, management.py, shortcuts.py, install.py
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

`tests/test_architecture.py` 自动检查：

- 分层 package 不形成循环；
- `core` 不导入非 core 的 MiniCode 模块；
- `runtime` 不导入 `tui` 或 `web`；
- 配置、Provider、OpenAI adapter、Context 的已知循环边不会恢复；
- 旧 core 导入和新 core 对象保持身份一致。

## Runtime 拆分

`agent_loop.py` 是 9 行稳定门面。`runtime.runner.run_agent_turn()` 只负责总编排，以下职责已独立：

- `runtime.lifecycle`：稳定任务状态消息；
- `runtime.model_execution`：Provider 调用兼容、失败摘要、fallback 分类；
- `runtime.tool_execution`：单工具超时、状态、callback 和错误收口；
- `runtime.policy`：上下文阻塞阈值与熔断压缩；
- `runtime.kernel`：turn policy、widen、verification 和终态决策。

## 数据与兼容性

- `minicode.memory` 已转换为 package，并显式导出原 Memory API；历史上被测试和向量检索使用的私有 helper 在兼容窗口内保留。
- `minicode.session` 保留路径同步门面，支持旧测试/集成 monkeypatch `MINI_CODE_DIR`、`SESSIONS_DIR`；数据模型仍由 JSON 默认值保证旧文件兼容。
- `minicode.context_manager` 保留 token、状态持久化和 `MINI_CODE_DIR` monkeypatch 转发。
- 根兼容门面与目标实现共享模块对象，旧路径 monkeypatch 不会失效。

## 已知结构债务

本轮已完成包归类、循环治理和 Runtime 真拆分；以下超大实现仍需后续批次做物理职责拆分，当前仅建立了目标子模块 API 边界：

- `memory/timeline/reasoner.py`
- `memory/manager.py`
- `persistence/session_storage.py`
- `context/compaction/dispatcher.py`
- `config/__init__.py`
- `cli/commands.py`

这些项目在 `MC-ARCH-PKG-20260622_IMPLEMENTATION_REPORT.md` 中标为未完成，不能据此宣布任务书 Definition of Done 已全部满足。

## 测试与配置

- `tests/`：pytest 全量与子系统测试；`tests/test_architecture.py` 是依赖护栏。
- `web/`：React/Vite 浏览器端，保持 REST/WebSocket 协议边界。
- `pyproject.toml`：包、可选依赖与三个 console scripts。
- `ts-src/`：TypeScript 参考实现，不属于 Python Runtime 依赖。
