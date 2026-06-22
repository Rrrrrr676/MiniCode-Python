# MC-ARCH-CLEAN-20260622 测试报告

| 项目 | 内容 |
|---|---|
| 日期 | 2026-06-22 |
| Python | 3.12 |
| 平台 | macOS / Asia/Shanghai |
| 最终结论 | **通过：0 个产品失败，0 个新增 skip/xfail** |

## 1. 基线

重构前基线：

| 检查 | 结果 |
|---|---|
| Python 全量 | 1180 passed，1 warning，13.12s |
| 前端 | 7 files / 28 tests passed |
| 三个入口帮助 | 全部退出码 0 |

## 2. 分阶段定向回归

| 批次 | 结果 |
|---|---:|
| Provider/Observability/Safety | 114 passed |
| Control/Cybernetics/Stress | 265 passed |
| Runtime 辅助门面与解环 | 162 passed，2 个 live API 用例按定向命令排除 |
| Context/Compaction 门面 | 235 passed |
| Memory 门面 | 285 passed |
| Persistence 门面 | 116 passed |
| Integration/CLI/Core 门面 | 184 passed |
| Timeline 物理拆分 | 279 passed |
| Memory 物理拆分 | 200 passed |
| Session 物理拆分 | 179 passed |
| Compaction 物理拆分 | 237 passed |
| Config 物理拆分 | 74 passed |
| CLI 物理拆分 | 133 passed |
| Runner 收敛 | 126 passed，2 个 live API 用例按定向命令排除 |

每批失败均在该批收敛后才继续，主要修复项包括：显性依赖环、实际 monkeypatch 查找位置、拆分后私有 helper 导入和 coda 依赖注入。

## 3. 最终 Python 验收

```bash
env PATH=/Users/xiatian/python/projects/MiniCode-Python/.venv/bin:/usr/bin:/bin \
  .venv/bin/python -m pytest -q
```

结果：

- 1183 passed；
- 0 failed / 0 errors；
- 0 skipped / 0 xfailed；
- 1 warning；
- 13.92s。

唯一 warning 为 FastAPI TestClient 暴露的 Starlette/httpx 弃用提示，与本次重构无关。

编译与文本质量：

```bash
.venv/bin/python -m compileall -q minicode
git diff --check
```

两项均通过。

## 4. 前端与构建

```bash
cd web
npm test -- --run
npm run build
```

结果：

- Vitest：7 files / 28 tests passed，817ms；
- TypeScript/Vite：通过，275 modules transformed，82ms；
- 产物：CSS 19.68 kB，JS 380.82 kB。

## 5. Wheel 与非仓库 cwd

```bash
.venv/bin/python -m pip wheel . --no-deps --no-build-isolation \
  -w /tmp/minicode-wheel-20260622-final
.venv/bin/python -m venv /tmp/minicode-wheel-venv-20260622-final
/tmp/minicode-wheel-venv-20260622-final/bin/python -m pip install --no-deps \
  /tmp/minicode-wheel-20260622-final/minicode_py-0.1.0-py3-none-any.whl
```

结果：

- wheel：`minicode_py-0.1.0-py3-none-any.whl`；
- 大小：3,020,841 bytes；
- SHA-256：`41ad1a6357831e55d848c6a93b13b09ac94825c6600facdf2b73bedf07daebc6`；
- 从 `/tmp` 安装成功，不依赖仓库 cwd。

## 6. 入口与稳定 API 冒烟

隔离 venv、工作目录 `/tmp`：

| 检查 | 结果 |
|---|---|
| `minicode-py --help` | 通过 |
| `minicode-headless --help` | 通过 |
| `minicode-web --help` | 通过 |
| `minicode.agent_loop.run_agent_turn` | 导入通过 |
| `minicode.memory.MemoryManager` | 导入通过 |
| `minicode.session.SessionData` | 导入通过 |
| `minicode.config.load_runtime_config` | 导入通过 |
| MockModel 单轮 Agent turn | 通过 |

首次隔离 MockModel 命令在受限沙箱中尝试写真实 `~/.mini-code/cybernetic_supervisor.json`，被文件系统策略拒绝。使用隔离 `HOME=/tmp/minicode-wheel-home` 后通过；这属于沙箱路径限制，不是产品断言失败。

## 7. 数据与产品面验证

以下均包含在最终 1183 项全量测试中：

- 旧 session JSON、delta、checkpoint、rewind；
- session list/resume/inspect/replay/preview；
- Memory 检索、排序、持久化、Timeline 答案/证据/日期/数值/旅行规则；
- 配置环境变量与用户/项目级优先级、Provider fallback 和诊断；
- Agent callback、fallback、终态、压力与并发；
- TUI 创建/恢复 session 和命令 monkeypatch 实际查找位置；
- Web session 创建、消息、权限、事件 replay 与终态；
- 根白名单、旧导入禁止、package 无环、Core/Runtime 边界。

## 8. 最终判定

代码、行为、架构、前端、构建、wheel 和入口验收全部绿色，未发现 P0/P1 回归。全部子系统与最终文档均按独立批次完成提交。
