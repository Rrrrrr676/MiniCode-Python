# MC-WEB-UX-20260621 测试报告

| 项目 | 内容 |
|---|---|
| 测试日期 | 2026-06-21 |
| 被测版本 | `0.1.1-web-ux` |
| 结论 | 通过 |
| Python | 3.12，项目 `.venv` |
| 前端 | React + TypeScript + Vite + Vitest |
| 浏览器视口 | 1280x720、390x844 |

## 1. 自动化结果

### 完整 Python 回归

```bash
env PATH=/Users/xiatian/python/projects/MiniCode-Python/.venv/bin:/usr/bin:/bin \
  .venv/bin/python -m pytest -q
```

结果：

```text
1173 passed, 1 warning in 11.83s
```

warning 为 FastAPI/Starlette `TestClient` 对当前 httpx 适配的既有弃用提示，不影响本任务行为。

### Web 后端专项

```bash
.venv/bin/python -m pytest -q \
  tests/test_web_api.py tests/test_web_events.py tests/test_web_runner.py
```

结果：`17 passed`。覆盖 Diff 摘要/patch、绝对路径/`..`/越界 symlink、二进制和大 patch 截断、WebSocket 重放、Secret 脱敏、权限、终态以及工具/Activity 快照恢复。

### 前端单元与组件测试

```bash
cd web
npm test -- --run
```

结果：

```text
Test Files  5 passed
Tests       18 passed
```

覆盖 80px 跟随阈值、上滚停止、即时落底、未读/回到最新、时间线顺序和去重、快照恢复、权限 choices、防重复提交、Diff 懒加载/缓存/105 文件分批、安全链接与 HTML 注入。

### 生产构建

```bash
cd web
npm run build
```

结果：TypeScript 与 Vite 构建通过；JS 218.07KB（gzip 68.31KB），CSS 12.81KB（gzip 3.66KB）。

## 2. 浏览器验收

浏览器使用生产构建与本地 FastAPI 服务，控制台 warning/error 为 0。

### AC-UX-01 / 02 三栏独立滚动

- 1280x720 下 document、app-shell、左右栏和 conversation 高度均为 720px；
- transcript 为独立滚动容器，`clientHeight=549`、`scrollHeight=6119`；
- 中栏向上滚动 320px 后 `window.scrollY=0`；
- session rail、context rail、header top 均保持 0，composer bottom 保持 720；
- context-content 为独立 `overflow-y:auto`，实测 `clientHeight=648`、`scrollHeight=1113`。

### AC-UX-03 智能跟随

- 长快照初始恢复后底部距离为 0，未错误显示“Back to latest”；
- 用户上滚后底部距离为 367px，按钮出现；
- 点击后底部距离恢复 0，按钮消失，document 不滚动；
- 单测覆盖后续 contentVersion/delta 到达时不抢回用户位置。

### AC-UX-04 Diff 懒加载

- 当前 31 文件工作区初始 `.diff-patch` DOM 数为 0；
- 展开 `minicode/web/api.py` 后 patch DOM 数为 1，内容长度 2247 字符；
- 组件测试验证 105 个文件初始只展示前 100 个，并验证 revision 变化清除缓存。

### AC-UX-05 / 06 时间线与恢复

- 现有长会话按用户消息、9 张工具卡和 Assistant 回答恢复顺序；
- reducer 测试覆盖消息/工具顺序、stream item 完成归并和重复 seq 丢弃；
- Runner/Reducer 覆盖工具、Activity、待审批和错误快照恢复；
- 浏览器实测停止服务后状态变为 `reconnecting`，时间线保持 11 项；服务恢复后回到 `connected`，仍为 11 项，没有重复消息；
- 重连使用最后 seq，连接状态不会覆盖既有 turn 终态。

### AC-UX-07 移动端抽屉

- 390x844 下 app/document 高度均为 844px；
- 关闭抽屉同时具有 `inert` 和 `aria-hidden=true`；
- 打开后移除隐藏属性，焦点进入“New session”，body 锁滚；
- Escape 关闭后恢复 `inert`/`aria-hidden`，焦点返回触发按钮，`aria-expanded=false`。

### AC-UX-08 长内容性能

- 6119px transcript 保持 document 固定高度；
- 大消息使用 `content-visibility`，代码块可横向滚动且未遮挡 composer；
- Diff 初始 DOM 不包含 patch；
- 浏览器无 React key warning、console warning 或 console error。

## 3. 说明

- 全量测试首次在受限沙箱内运行时，因无法访问 `~/.mini-code` 产生 PermissionError；改在获准环境并补齐 `.venv/bin` PATH 后全部 1173 项通过。
- 本轮没有调用外部模型服务；浏览器使用已有本地会话验证长内容和工具恢复。
- 20 连续实时 delta、WebSocket 断网时钟和 100 文件真实 Git 仓库主要由单元/组件验证覆盖，后续可加入专用 E2E fixture 做完全自动化压测。
