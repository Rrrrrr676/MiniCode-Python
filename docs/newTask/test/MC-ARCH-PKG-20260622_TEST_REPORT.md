# MC-ARCH-PKG-20260622 测试报告

| 项目 | 内容 |
|---|---|
| 日期 | 2026-06-22 |
| Python | 3.12.13 |
| 平台 | macOS / Asia/Shanghai |
| 最终结论 | 已实施范围全部通过；任务书仍有结构拆分未完成项 |

## 1. 基线

测试子进程会直接调用 `python`，因此有效基线命令显式把项目 `.venv/bin` 放入 PATH。未加 PATH 或未授权用户级测试目录时产生的失败属于环境限制，不计入产品基线。

| 命令 | 结果 | 耗时 |
|---|---|---:|
| `.venv/bin/python -m compileall -q minicode` | 通过 | <1s |
| `env PATH=.../.venv/bin:/usr/bin:/bin .venv/bin/python -m pytest -q` | 1174 passed，0 failed，0 skipped，1 warning | 12.30s |
| `cd web && npm test -- --run` | 7 files / 28 tests passed | 0.864s |
| `cd web && npm run build` | 通过，275 modules transformed | 0.089s |

## 2. 分阶段回归

| 阶段 | 测试结果 |
|---|---|
| Provider/Config/Context cycle | 205 passed |
| Core 迁移/打包 | 31 passed |
| Runtime 初始迁移 | 141 passed |
| Runtime 真拆分 | 141 passed |
| Context/Compaction | 256 passed |
| Memory/Timeline | 252 passed |
| Session/Persistence | 101 passed |
| Memory 辅助模块归包 | 127 passed |

所有批次均在失败时停止扩散：先修复导入、相对路径、私有兼容或 monkeypatch 语义，再进入下一批。

## 3. 最终 Python 验收

```bash
env PATH=/Users/xiatian/python/projects/MiniCode-Python/.venv/bin:/usr/bin:/bin \
  .venv/bin/python -m compileall -q minicode
env PATH=/Users/xiatian/python/projects/MiniCode-Python/.venv/bin:/usr/bin:/bin \
  .venv/bin/python -m pytest -q
```

结果：

- 1180 passed
- 0 failed
- 0 errors
- 0 skipped
- 1 warning
- 14.23s

唯一 warning 为 FastAPI TestClient 暴露的 Starlette/httpx 弃用提示，与本次重构无关。

## 4. 前端与构建

```bash
cd web
npm test -- --run
npm run build
```

结果：

- Vitest：7 files、28 tests passed，1.07s
- TypeScript/Vite build：通过，275 modules transformed，97ms
- 产物：`index.html`、CSS 19.68 kB、JS 380.82 kB

## 5. Wheel 与入口冒烟

```bash
.venv/bin/python -m pip wheel . --no-deps --no-build-isolation -w /tmp/minicode-wheel-20260622-2
.venv/bin/python -m venv /tmp/minicode-install-20260622-2
/tmp/minicode-install-20260622-2/bin/python -m pip install --no-deps \
  /tmp/minicode-wheel-20260622-2/minicode_py-0.1.0-py3-none-any.whl
cd /tmp
/tmp/minicode-install-20260622-2/bin/minicode-py --help
/tmp/minicode-install-20260622-2/bin/minicode-headless --help
/tmp/minicode-install-20260622-2/bin/minicode-web --help
```

结果：

- wheel 构建成功：1,952,219 bytes
- SHA-256：`76b4f50f4d4374101209dc8c4095e583d3796fa4c1ed4d8b41fe046c9d066512`
- 从 `/tmp` 隔离安装成功，不依赖仓库 cwd
- 三个 console script 帮助命令均退出码 0

## 6. 其他质量门

| 检查 | 结果 |
|---|---|
| `tests/test_architecture.py` | 包含在全量 1180 项中，通过 |
| 旧 core 导入身份 | 通过 |
| 旧 session/delta/checkpoint/rewind | 通过 |
| MockModel Agent turn | Agent/Integration 测试通过 |
| TUI session create/resume | TUI/Session 测试通过 |
| Web session/message/终态 | Web API/Events/Runner 测试通过 |
| 配置优先级与 Provider fallback | Config/Model switching 测试通过 |
| `git diff --check` | 通过 |

## 7. 已知残余风险

1. 多个超大实现仍集中在单文件；虽回归绿色，但尚未满足任务书物理拆分 DoD。
2. 73 个兼容门面增加了暂时维护成本，删除前必须继续做调用审计。
3. `runtime.runner` 原始模块扇出仍高，目标 package 图无循环不代表组合根已完全收敛。
4. warning 中的 Starlette/httpx 兼容问题应在依赖升级任务中单独处理。

因此测试报告确认“已实现范围无回归”，不确认整个任务书已经 100% 完成。
