# MiniCode Web 输出可读性优化测试报告

| 项目 | 内容 |
|---|---|
| 任务编号 | `MC-WEB-READABILITY-20260621` |
| 测试日期 | 2026-06-21 |
| 被测版本 | `0.1.2-web-readability` |
| 总体结论 | 离线自动化通过；外部 API 与真实浏览器视觉验收受环境限制 |

## 1. 自动化结果

### 1.1 Python 离线全量回归

```bash
env HOME=/private/tmp/minicode-readability-tests \
  PATH="$PWD/.venv/bin:$PATH" \
  .venv/bin/python -m pytest -q -k 'not TestLiveAPI'
```

结果：`1172 passed, 2 deselected, 1 warning`。

说明：隔离 HOME 用于防止测试写入真实 `~/.mini-code`。warning 为 FastAPI TestClient 上游弃用提示，与本任务无关。

### 1.2 Web 后端定向测试

```bash
.venv/bin/python -m pytest -q \
  tests/test_web_events.py tests/test_web_runner.py tests/test_web_api.py
```

结果：`18 passed, 1 warning`。

覆盖结构化工具上限事件、snapshot 恢复、冷启动 session summary、fallback 抑制、工具事件、权限、错误、重连和 secret 脱敏。

### 1.3 前端单元/组件测试

```bash
cd web && npm test -- --run
```

结果：`7` 个测试文件，`28 passed`。

覆盖：

- GFM 全语法、raw HTML 转义、`javascript:` URL 拦截；
- 未闭合流式 fenced code；
- 长代码折叠、无语言标签降噪和精确复制；
- heading ID 去重、目录 Escape/焦点归还、transcript 容器内跳转；
- 13 个连续工具调用聚合、失败显式呈现、分组边界和运行中工具；
- 工具分组展开与 accessible summary；
- 工具上限 reducer/snapshot 恢复及继续 turn 去重；
- 智能跟随、未读计数和跳回最新。

### 1.4 构建与静态检查

```bash
cd web && npm run build
git diff --check
```

结果：均通过。Vite 构建输出约 `380.82 kB` JavaScript（gzip `116.70 kB`）和 `19.68 kB` CSS（gzip `5.08 kB`）。

## 2. 验收项映射

| 验收项 | 自动化结论 | 证据 |
|---|---|---|
| AC-READ-01 Markdown 语义与安全 | 通过 | Markdown 组件测试、TypeScript 构建 |
| AC-READ-02 工具聚合 | 通过 | 13 调用 selector 测试、失败/边界/展开测试 |
| AC-READ-03 回到最新 | 自动化通过，视觉待补 | scroll hook 测试、独立 grid dock 结构 |
| AC-READ-04 长回答目录 | 通过 | ID 去重、焦点、Escape、容器内跳转测试 |
| AC-READ-05 代码块 | 通过 | 30 行折叠、精确复制、overflow 样式 |
| AC-READ-06 工具上限 | 通过 | runner 结构化终态、持久化、store 恢复与继续测试 |
| AC-READ-07 视觉与无障碍 | 语义自动化通过，视觉待补 | heading/details/dialog/accessible-name 测试；真实视口未完成 |

## 3. 环境限制

### 3.1 外部 API 用例

不排除 `TestLiveAPI` 时结果为 `1172 passed, 2 failed`。两个失败均由外部 Anthropic 端点 DNS 不可达导致：

- `TestLiveAPI.test_simple_question`；
- `TestLiveAPI.test_tool_use_via_api`。

这两项会使用环境中的模型凭据向外部服务发送请求。本轮未申请放开凭据传输，故在最终离线回归中明确 deselect。

### 3.2 真实浏览器验收

- 临时 Web 服务已成功启动，HTTP 回环探测收到服务响应；
- Codex 内置浏览器控制通道在导航 `127.0.0.1`/`localhost` 时持续无返回，无法获得 DOM snapshot；
- 因此未伪造 1280×720、768×1024、390×844、200% zoom、控制台和视觉重叠结果。

建议环境恢复后补跑任务书第 8 节的 6 组浏览器用例，并将截图/控制台结果追加到本报告。

## 4. 风险结论

本次变更的协议、状态恢复、渲染安全、工具聚合和交互逻辑已有自动化覆盖，离线回归无已知代码失败。剩余风险集中在真实浏览器的像素级布局和外部模型联调，不影响本地静态构建与离线功能正确性。
