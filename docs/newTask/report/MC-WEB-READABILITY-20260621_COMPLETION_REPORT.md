# MiniCode Web 输出可读性优化完成报告

| 项目 | 内容 |
|---|---|
| 任务编号 | `MC-WEB-READABILITY-20260621` |
| 完成日期 | 2026-06-21 |
| 目标版本 | `0.1.2-web-readability` |
| 依据任务书 | `WEB_UI_OUTPUT_READABILITY_TASK_BRIEF_2026-06-21.md` |
| 交付状态 | 开发与离线自动化验证完成；真实浏览器人工验收待浏览器控制通道恢复后补验 |

## 1. 交付摘要

本次完成了 Web 回答阅读层的系统性升级：使用安全 Markdown AST 渲染替代原始文本展示；连续同类工具调用在呈现层聚合；“回到最新”移动到不遮挡正文的独立停靠区；长回答增加 AST 目录和容器内跳转；长代码默认折叠并提供无尺寸抖动的复制反馈；工具步数耗尽改为可恢复的结构化未完成终态。

Store 中的原始事件和工具顺序未被改写，聚合仅发生在 selector/组件层。旧 session 不含新增终态字段时继续按原逻辑恢复。

## 2. 完成项

### READ-001 / READ-002：安全 Markdown 与排版系统

- 引入 `react-markdown`、`remark-gfm`、`unified`、`remark-parse` 和 `unist-util-visit`；
- 支持 H1/H2/H3、段落、粗体、斜体、删除线、列表、任务列表、引用、分隔线、表格、链接、行内代码和 fenced code；
- 不使用 `dangerouslySetInnerHTML`，raw HTML 仅作为转义文本呈现；
- URL 仅允许 `http`、`https`、`mailto` 和页内锚点，外链使用新窗口及安全 `rel`；
- Markdown 渲染错误时回退为安全纯文本；
- 建立回答宽度、中文行高、标题间距、列表、引用、表格和行内代码层级；表格独立横向滚动。

### READ-003：连续工具调用聚合

- 新增纯呈现层 `groupTimelineTools`；
- 同一 turn 内连续、同名、已完成工具调用聚合为一个原生 `details` 组件；
- 摘要显示调用数、成功/失败/运行数及累计耗时；
- 展开后保留原 seq 顺序、输入摘要、输出摘要、状态和耗时；
- 消息、权限、错误、不同 turn、不同工具及运行中工具均会中断分组。

### READ-004：回到最新

- 按钮移出 transcript 正文流，停靠在 composer 上方的独立 grid 行；
- 不覆盖正文、代码、表格、滚动条或发送按钮；
- 保留 80px 自动隐藏阈值、未读更新计数和 reduced-motion 兼容；
- 移动端限制最大宽度并使用省略保护。

### READ-005：长回答目录

- 目录和 heading ID 直接从 Markdown AST 生成；
- 4 个及以上标题或正文超过 3,000 字符时显示目录入口；
- H2/H3 保持层级，重复标题生成稳定唯一 ID；
- 跳转只修改 transcript 容器滚动位置；
- 当前章节按容器滚动位置高亮；
- 目录支持焦点锁定、Escape 关闭和焦点归还。

### READ-006：代码块体验

- 无语言代码块不显示高权重 `text` 标签；
- 复制按钮使用紧凑图标、tooltip、accessible label 和独立 live status；
- 超过 24 行或 4,000 字符默认折叠并显示行数；
- 代码块自身横向滚动，不扩张 document。

### READ-007：工具步数上限终态

- 新增结构化 `turn.incomplete` 事件、`incomplete` 状态和 snapshot `terminal` 字段；
- 根据 Agent 的 `RuntimeEvent(category="stop", stop_reason="max_steps")` 判定，不匹配 UI 文本；
- 兼容性 fallback 不再作为普通 Assistant 回答显示或持久化；
- 专用状态卡显示已用/上限步数和未完成说明；
- 提供“Continue from existing results”动作，并遵守发送中/运行中约束；
- 终态写入 session transcript metadata，服务重启和刷新后可恢复；新 turn 开始时清除旧终态，避免重复卡片。

### READ-008 / READ-009：无障碍、响应式与回归

- 标题使用原生语义元素，工具分组和长代码使用原生 `details/summary`；
- 目录、复制、继续和回到最新均有 accessible name；
- 使用独立简短 live region，避免重读整篇回答；
- 390px 断点下缩减正文边距、目录改为底部轻量弹层；
- 增加 reduced-motion 全局保护；
- Web 包版本更新为 `0.1.2-web-readability`。

## 3. 关键实现说明

1. Markdown AST 会分别用于内容分析和渲染插件，heading slug 算法一致，避免从 DOM 反向抓取目录。
2. 工具聚合输入为 `timeline + tools`，输出仅用于 render，reducer 和 snapshot 的原始数据结构保持不变。
3. 工具上限由 runtime stop event 驱动；`max_tool_steps` 终态在 executor 返回后统一落盘并发布，避免与 `completed` 混淆。
4. “回到最新”使用独立布局行而非悬浮覆盖，从结构上保证重叠面积为零。

## 4. 交付文件

- 前端：`web/src/App.tsx`、`web/src/features/chat/*`、`web/src/features/tools/*`、`web/src/store/*`、`web/src/styles/app.css`；
- 协议/后端：`minicode/web/events.py`、`minicode/web/schemas.py`、`minicode/web/runner.py`；
- 依赖与版本：`web/package.json`、`web/package-lock.json`；
- 测试：`tests/test_web_runner.py` 及 Web 组件、selector、reducer 测试；
- 文档：任务书、本完成报告和配套测试报告。

## 5. 验证结论

- Python 离线全量：`1172 passed, 2 deselected`；
- Web 前端：`7` 个测试文件、`28 passed`；
- Web 生产构建：通过；
- `git diff --check`：通过；
- 2 个 deselected 用例为真实 Anthropic API 联调用例，因外网和凭据传输限制未执行；
- 本地服务可通过 HTTP 回环访问，但 Codex 内置浏览器本轮无法完成 localhost 导航，因此 1280×720、768×1024、390×844 的真实截图/视觉验收未宣称通过，详见测试报告。
