# MC-WEB-20260619 测试报告

| 项目 | 内容 |
|---|---|
| 测试日期 | 2026-06-19 |
| 被测版本 | `0.1.0-web-mvp` |
| 结论 | 通过 |
| Python | 3.12（项目 `.venv`） |
| Node.js | 24.16.0 |
| 浏览器视口 | 1280×720、390×844 |

## 1. 自动化测试结果

### 完整 Python 回归

为避免测试读写真实 `~/.mini-code`，使用隔离 HOME；为保证离线可复现，主动移除外部 Provider API Key：

```bash
env -u ANTHROPIC_API_KEY \
  HOME=/tmp/minicode-full-test-home \
  PATH=/Users/xiatian/python/projects/MiniCode-Python/.venv/bin:/usr/local/bin:/usr/bin:/bin \
  .venv/bin/python -m pytest -q
```

结果：

```text
1168 passed, 2 skipped, 1 warning in 5.69s
```

- 跳过 2 项：需要真实 Anthropic 网络请求的可选 Live API 测试。
- 1 条 warning：FastAPI/Starlette `TestClient` 对当前 httpx 适配的弃用提示，不影响行为。

### Web 后端专项

覆盖事件序号、等待、重放、游标续接、Session API、WebSocket 快照、Runner callback、显式异常、权限批准/超时/重复响应、Secret 脱敏、Diff 与路径边界。

```bash
HOME=/tmp/minicode-web-tests \
  .venv/bin/python -m pytest -q \
  tests/test_web_api.py tests/test_web_events.py tests/test_web_runner.py
```

结果：`14 passed`。

### TUI / Headless 兼容性

TUI 与 Headless 已包含在完整回归中；另执行 Web + TUI + Headless 聚焦回归，结果通过。未修改用户已有的 `minicode/tui/input_handler.py` 与 `tests/test_tty_app.py` 工作区改动。

### 前端状态与构建

```bash
cd web
npm run test
npm run build
```

结果：

```text
Test Files  2 passed
Tests       6 passed
TypeScript strict build passed
Vite production build passed
```

前端覆盖：delta 合并、工具 started/completed、失败终态、重连去重、权限防重复提交、刷新后工具状态恢复。

## 2. 浏览器验收

浏览器验收使用生产构建与本地 FastAPI 静态服务。会话目录使用临时 HOME；完整 Agent 流程使用 `MINI_CODE_MODEL_MODE=mock`，没有发送外部网络请求或真实 Secret。

### 桌面 1280×720

- 三栏计算宽度为 `248px / 692px / 340px`；
- Session、Conversation、Changes/Activity 均可见；
- 无横向溢出；
- 创建会话和页签切换成功；
- WebSocket 显示 `connected`；
- 浏览器控制台错误数为 0。

### 窄屏 390×844

- 主对话保持单列且无横向溢出；
- Sessions 与 Workspace context 由有可访问名称的按钮打开；
- 抽屉覆盖显示，背景遮罩可关闭；
- 抽屉完成动画后 transform 为 0，右侧抽屉宽约 335px；
- 浏览器控制台错误数为 0。

### Mock 完整流程

浏览器发送 `/ls minicode/web`：

- 显示 1 条用户消息；
- 显示 1 条 Assistant 最终回答；
- 显示 `list_files` 工具卡片、成功状态与耗时；
- turn 状态为 `Completed`；
- 输入框重新启用；
- Changes 展示当前工作区文件与增删统计；
- 刷新后恢复 2 条对话消息、completed 终态和 1 张成功工具卡片；
- 浏览器控制台错误数为 0。

### 服务退出

关闭浏览器连接后发送一次 `Ctrl+C`，Uvicorn 正常完成 application shutdown，无残留监听进程。

## 3. 验收条件映射

| 用例 | 结果 | 证据 |
|---|---|---|
| AC-01 正常问答 | 通过 | Mock 浏览器完整流程；最终状态 completed。 |
| AC-02 工具执行 | 通过 | `list_files` 卡片、成功状态、耗时；Runner 单测覆盖失败。 |
| AC-03 显式异常 | 通过 | 注入 `NameError`，收到 `turn.failed`、errorType、traceId，状态保持 failed。 |
| AC-04 权限确认 | 通过 | 批准、超时拒绝、重复响应冲突；前端按钮防连击。 |
| AC-05 页面恢复 | 通过 | seq 去重/重放测试；浏览器刷新恢复消息、终态和工具卡片。 |
| AC-06 Diff | 通过 | tracked/untracked 自动化测试；浏览器 Changes 展示。 |
| AC-07 兼容性 | 通过 | 完整 Python 回归 1168 passed；TUI/Headless 用例通过；Web 依赖可选。 |

## 4. 风险与说明

- 本轮未调用真实外部模型 Provider；Live API 测试明确跳过，功能链使用可重复的本地 Mock Runtime 验证。
- FastAPI `TestClient` 有 1 条上游弃用 warning；后续依赖升级时跟进 httpx2/Starlette 适配即可。
- 取消是协作式；底层不可中断调用仍受现有工具/Provider timeout 约束。
