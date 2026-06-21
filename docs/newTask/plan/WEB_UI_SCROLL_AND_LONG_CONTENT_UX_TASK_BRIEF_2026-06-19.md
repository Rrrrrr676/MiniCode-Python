# MiniCode Web 前端滚动与长内容体验优化任务书

| 项目 | 内容 |
|---|---|
| 文档日期 | 2026-06-19 |
| 任务编号 | MC-WEB-UX-20260619 |
| 任务名称 | Web 三栏滚动隔离与长会话体验优化 |
| 依赖版本 | `0.1.0-web-mvp` |
| 建议目标版本 | `0.1.1-web-ux` |
| 优先级 | P0 / P1 |
| 预计工期 | 1–2 个工作日 |
| 依据 | `docs/DEVELOPMENT_GUIDELINES.md`、`MC-WEB-20260619_IMPLEMENTATION_REPORT.md`、浏览器实测 |

## 1. 背景与实测结论

当前 Web MVP 已完成会话、实时事件、工具、权限、错误、Diff 和刷新恢复，但长回答场景下的页面滚动模型仍不正确。用户在中间对话区滚动 Agent 返回内容时，左右栏和顶部栏会随整个页面一起移动，破坏三栏工作台的稳定感。

2026-06-19 在 1280×720 视口实测：

| 指标 | 当前值 | 说明 |
|---|---:|---|
| `document.scrollHeight` | 6664px | 整页被对话内容撑高 |
| `.app-shell` 高度 | 6664px | 使用 `min-height`，没有锁定视口 |
| `.conversation` 高度 | 6664px | 中栏没有形成固定高度网格 |
| `.transcript` 高度 | 6475px | `overflow-y: auto` 实际没有产生独立滚动 |
| 中栏滚动后的 `window.scrollY` | 5944px | 滚动发生在 window |
| 左右栏 top | -5944px | 两侧跟随页面移出视口 |
| 当前 Changes 文件数 | 48 | 初始页面一次性渲染全部文件 |
| Changes 文本量 | 227,634 字符 | 折叠前已经进入 DOM |
| 当前 transcript 文本量 | 41,786 字符 | 长回答渲染压力明显 |

此外，`App.tsx` 在消息、流式文本或权限状态变化时无条件调用 `scrollIntoView({ behavior: "smooth" })`。流式输出期间，这会持续争夺滚动位置；用户向上阅读历史内容时仍可能被拉回底部。

## 2. 优化目标

本任务完成后应达到：

1. 页面本身不滚动，左、中、右三栏拥有明确且互不干扰的滚动边界；
2. 用户停留在底部时，流式回答自动跟随；用户向上阅读后，自动跟随立即停止；
3. 长 Diff 不在初始加载时进入 DOM，按文件展开后再获取与渲染；
4. 消息、工具、权限、错误和 runtime phase 按真实时间顺序呈现；
5. 长回答、长会话和大量文件变化下保持可用性能；
6. 重连、移动端抽屉、键盘导航和错误恢复具有明确反馈。

## 3. 必须完成范围

### 3.1 三栏独立滚动

- `html`、`body`、`#root` 锁定为视口高度并禁止 document 滚动；
- `.app-shell` 使用 `height: 100dvh`、`min-height: 0` 和 `overflow: hidden`；
- `.conversation` 使用 `minmax(0, 1fr)` 约束 transcript 行；
- `.transcript`、`.session-list`、`.context-content` 分别成为独立滚动容器；
- 三个滚动容器增加 `overscroll-behavior: contain`，防止滚动链传递；
- 左侧品牌、新建按钮、工作区状态固定；右侧 Changes/Activity 页签固定；
- 桌面端页面滚动时 header 和 composer 不离开视口；
- 移动端使用 `100dvh`，兼容移动浏览器动态地址栏。

推荐布局约束：

```css
html,
body,
#root {
  height: 100%;
  overflow: hidden;
}

.app-shell {
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
}

.conversation,
.session-rail,
.context-rail {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.transcript,
.session-list,
.context-content {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}
```

### 3.2 智能自动跟随

- 禁止使用会改变 document 滚动位置的全局 `scrollIntoView()`；
- 为 transcript 建立显式 ref，通过容器 `scrollTop`/`scrollTo` 控制；
- 用户距离底部不超过 80px 时视为 `isFollowing=true`；
- 用户主动向上滚动后停止自动跟随，不得在下一个 delta 到达时抢回位置；
- 停止跟随后显示“回到最新”按钮，并提示未读增量；
- 点击“回到最新”恢复跟随并滚到底部；
- 用户提交新消息时可以主动恢复跟随；
- `prefers-reduced-motion` 下禁用 smooth scroll。

### 3.3 Diff 摘要与按需加载

- 初始 Diff API 只返回文件路径、状态、增删行数和是否为二进制文件；
- 新增按文件读取 patch 的端点，路径必须继续经过工作区边界校验；
- 用户首次展开文件时再请求 patch；
- 同一文件 patch 在 revision 未变化时复用缓存；
- Diff 更新后只失效受影响文件或当前 revision 的缓存；
- 单文件大 patch 显示截断说明，并允许用户显式加载更多；
- 折叠文件不得持有大段不可见 DOM；
- Changes 文件列表超过 100 项时使用虚拟列表或分段渲染。

建议协议：

```text
GET /api/sessions/{session_id}/diff
GET /api/sessions/{session_id}/diff/files/{encoded_path}
```

### 3.4 统一会话时间线

- Store 不再把工具卡片统一堆在全部消息之后；
- 用户消息、Assistant 增量/最终消息、工具、权限、错误按事件顺序形成判别联合 TimelineItem；
- 每个工具卡片归属正确 turn，并显示运行中、成功、失败和耗时；
- runtime phase 默认折叠到对应 turn 的 Activity 区；
- 刷新后从 snapshot 恢复最近工具与 Activity，不丢失归属关系；
- 多轮会话不得把上一轮工具显示到当前回答下面。

### 3.5 长回答展示

- Assistant 内容使用安全 Markdown 渲染；
- 代码块支持语言标识、横向滚动、复制和长代码折叠；
- 外部链接必须使用安全 `rel`；
- HTML 默认不执行，继续防止脚本注入；
- 大消息考虑 `content-visibility: auto` 或列表虚拟化；
- 流式 Markdown 不得因不完整代码围栏导致整个页面反复重排。

### 3.6 重连与恢复反馈

- WebSocket 重连改为指数退避，例如 1s、2s、4s、8s，最大 30s，并增加 jitter；
- 显示 `connecting / connected / reconnecting / offline` 和最后同步时间；
- 达到重试上限后提供“立即重连”；
- reconnect 继续使用最后 `seq`，重复事件不得产生重复消息；
- 断线期间不得把 turn 推断为完成；
- 重连快照不得覆盖更新的本地事件状态。

### 3.7 权限、错误与取消反馈

- 权限卡根据后端 choices 显示允许一次、当前 turn、始终允许等合法 scope；
- 保持按钮防重复提交，提交中显示明确状态；
- 错误卡支持复制 trace ID、重试上一问题和关闭展示；
- 关闭错误只影响 UI，不篡改后端已记录终态；
- 点击取消后显示 `Cancelling…`，直到收到 `turn.cancelled` 或失败；
- Composer 在 turn 运行时允许编辑草稿，但禁止直接提交，或明确支持排队提交。

### 3.8 移动端与可访问性

- 关闭的移动端抽屉使用 `inert`/`aria-hidden`，内部控件不得被 Tab 聚焦；
- 抽屉打开后锁定焦点，支持 Escape 关闭，并在关闭后把焦点还给触发按钮；
- 打开抽屉时阻止背景区域滚动；
- 抽屉按钮提供 `aria-expanded` 与 `aria-controls`；
- tab 与 tabpanel 建立明确关联；
- 不在整个 transcript 上使用会重复朗读全部内容的宽泛 live region；
- 新增独立、简短的屏幕阅读器状态播报区域。

## 4. 建议完成范围

- 会话搜索、重命名与删除；
- 手动深色/浅色主题切换并持久化；
- 工具结果复制；
- Diff 文件过滤和只看失败工具；
- Composer 自动增高、草稿按 session 保存；
- “跳到上一条用户消息”和“跳到最新错误”快捷操作。

## 5. 明确不在本任务范围

- 多工作区并行和多 Agent 并行；
- 在线代码编辑、Diff 行级评论；
- Git 分支、提交与 PR 工作流；
- 云端部署、登录和团队协作；
- 替换现有 Runtime 事件协议的核心语义。

## 6. 任务分解

| 编号 | 优先级 | 任务 | 交付物 | 完成标准 |
|---|---|---|---|---|
| UX-001 | P0 | 视口与三栏滚动隔离 | CSS/layout 测试 | 中栏滚动时左右栏 top 保持 0 |
| UX-002 | P0 | 智能跟随与回到最新 | `useTranscriptScroll` + 测试 | 用户向上滚动后 delta 不抢位置 |
| UX-003 | P0 | Diff 摘要/按需 patch | API、Store、ChangesPanel | 初始 DOM 不包含 patch 正文 |
| UX-004 | P1 | 统一 Timeline | 类型、reducer、组件 | 工具与对应回答按序排列 |
| UX-005 | P1 | Markdown/代码体验 | 安全 renderer | 代码块可复制且不执行 HTML |
| UX-006 | P1 | 快照 Activity 恢复 | snapshot schema/reducer | 刷新后工具与阶段归属不丢失 |
| UX-007 | P1 | 重连状态机 | WebSocket service/hook | 指数退避、手动重连、seq 去重 |
| UX-008 | P1 | 权限/错误/取消 UX | 卡片与交互测试 | Scope、trace、retry、cancelling 清晰 |
| UX-009 | P1 | 移动端无障碍 | drawer focus 管理 | 关闭抽屉不可聚焦，Esc 可关闭 |
| UX-010 | P0 | 性能与回归验收 | 测试报告 | 自动化和浏览器场景全部通过 |

## 7. 验收用例

### AC-UX-01 中栏独立滚动

在 1280×720 下加载高度超过 5000px 的回答，从中栏顶部滚到底部：

- `window.scrollY` 始终为 0；
- `.transcript.scrollTop` 发生变化；
- `.session-rail`、`.context-rail`、header、composer 的 top 不变化。

### AC-UX-02 侧栏独立滚动

分别滚动会话列表和 Changes：只有鼠标所在容器变化，滚动到边界后不把滚轮传递给其他栏或 document。

### AC-UX-03 用户阅读不被打断

流式输出时用户向上滚动 300px，连续接收至少 20 个 delta：当前位置变化不超过 2px，并显示“回到最新”。点击按钮后恢复到底部跟随。

### AC-UX-04 Diff 懒加载

工作区包含 100 个修改文件和至少 1MB patch：初始页面不包含 patch 正文；展开单个文件后只请求并渲染该文件内容；折叠后大 patch DOM 被释放或受控缓存。

### AC-UX-05 时间线归属

执行两轮各包含两个工具的任务，消息、工具、权限和错误按 seq 排列，每张工具卡只出现在所属 turn 中。

### AC-UX-06 刷新与重连

运行中刷新并模拟 WebSocket 断开：消息不重复，工具状态不丢失，页面显示 reconnecting 而不是 completed。

### AC-UX-07 移动端键盘与抽屉

390×844 下关闭抽屉时 Tab 不进入隐藏控件；打开后焦点停留在抽屉内；Escape 关闭并恢复触发按钮焦点。

### AC-UX-08 长内容性能

在 2 条各 40,000 字符消息、100 个 Diff 文件和 100 条 Activity 下：

- 页面首屏可交互；
- 滚动无明显长时间冻结；
- Changes 初始 DOM 文本不包含所有 patch；
- 浏览器控制台无错误和 React key warning。

## 8. 测试要求

### 前端单元/组件测试

- transcript 底部阈值与 `isFollowing` 状态；
- delta 到达时跟随/不跟随两条路径；
- “回到最新”按钮与 unread 计数；
- Timeline 按 seq 归并与重复事件去重；
- Diff 展开时只发起一次 patch 请求；
- 重连退避、恢复和手动重连；
- drawer inert、Escape 和焦点恢复；
- Markdown 脚本注入回归。

### 后端测试

- Diff summary 与单文件 patch schema；
- encoded path、`..`、绝对路径和 symlink 越界；
- 大 patch 截断与二进制文件；
- snapshot 最近 Activity 与工具归属；
- API/事件继续执行 Secret 脱敏。

### 浏览器测试

- 1280×720 三栏滚动隔离；
- 390×844 抽屉与键盘；
- 长回答期间手动上滚；
- 100 文件 Diff 懒加载；
- WebSocket 断开/恢复；
- 刷新恢复时间线。

目标命令：

```bash
python -m pytest -q
cd web && npm run test
cd web && npm run build
```

## 9. 代码注释与变更记录要求

- 对 `min-height: 0`、`minmax(0, 1fr)`、`overscroll-behavior` 等非直观滚动约束添加简短注释，说明其防止 Grid/Flex 子项撑高和滚动链传递的原因；
- 对智能跟随阈值、用户主动滚动判定、重连退避上限添加常量名和设计注释，禁止散落 magic number；
- 对 Diff path 解码与 workspace 边界检查注明安全不变量；
- 注释解释“为什么”，不重复代码表面行为；
- 实现报告必须记录协议变化、性能数据、浏览器实测结果和未完成项；
- Git commit message 使用 `fix:` / `perf:` / `feat:` / `test:` / `docs:`，提交正文列出验证命令与结果。

## 10. Definition of Done

- AC-UX-01 至 AC-UX-08 全部通过；
- 页面 document 不再承担桌面端业务区域滚动；
- 用户阅读历史时不被流式 delta 强制拉回；
- 初始 Diff DOM 不包含全部 patch；
- 统一时间线和刷新恢复保持事件幂等；
- 移动端抽屉满足基础键盘与焦点要求；
- 完整 Python、前端测试和生产构建通过；
- `git diff --check` 通过；
- 实现报告和测试报告同步写入 `docs/newTask/`。
