# MC-WEB-UX-20260621 完成报告

| 项目 | 内容 |
|---|---|
| 任务编号 | `MC-WEB-UX-20260619` |
| 任务名称 | Web 三栏滚动隔离与长会话体验优化 |
| 目标版本 | `0.1.1-web-ux` |
| 实施日期 | 2026-06-21 |
| 实施状态 | 已完成 |
| 任务依据 | `docs/newTask/plan/WEB_UI_SCROLL_AND_LONG_CONTENT_UX_TASK_BRIEF_2026-06-19.md` |

## 1. 交付结论

本轮完成了 Web 工作台滚动模型、智能跟随、Diff 按需加载、统一时间线、长内容展示、重连反馈、权限/错误/取消状态和移动端无障碍优化。桌面页面不再由 document 承担业务滚动；长会话、Changes 和会话列表拥有独立滚动边界。版本已从 `0.1.0-web-mvp` 升级到 `0.1.1-web-ux`。

本地服务地址：`http://127.0.0.1:8765`。

## 2. 已完成内容

| 编号 | 状态 | 实现摘要 |
|---|---|---|
| UX-001 | 完成 | `100dvh` 固定工作台；Grid 子项 `min-height: 0`；三处独立滚动和滚动链隔离。 |
| UX-002 | 完成 | 新增 `useTranscriptScroll`；80px 阈值、用户上滚停止、未读计数、回到最新和 reduced-motion。 |
| UX-003 | 完成 | Diff 初始 API 仅返回摘要；按文件加载 patch；revision 缓存、1MB/5MB 截断层级和 100 项分段渲染。 |
| UX-004 | 完成 | 消息、工具、权限和错误按事件序列进入判别联合时间线；工具保留 turn、状态和耗时。 |
| UX-005 | 完成 | 安全文本/链接/代码围栏渲染；代码语言、复制、横向滚动和长代码折叠；HTML 不执行。 |
| UX-006 | 完成 | Snapshot 恢复消息、工具、待审批、错误和最近 100 条 runtime Activity。 |
| UX-007 | 完成 | WebSocket 指数退避和 jitter，最大 30 秒；状态、同步时间、重试上限、手动重连和 seq 去重。 |
| UX-008 | 完成 | 权限 choices、提交锁；错误 trace 复制/重试/关闭；取消中状态；运行时可编辑草稿但禁止发送。 |
| UX-009 | 完成 | 移动抽屉 `inert`/`aria-hidden`、焦点锁定、Escape、焦点归还、背景锁滚和 ARIA 关联。 |
| UX-010 | 完成 | Python/前端/构建/浏览器验收和本报告、测试报告。 |

## 3. 协议变化

### Diff

`GET /api/sessions/{session_id}/diff` 不再返回 patch 正文，文件摘要新增：

```text
path, status, additions, deletions, isBinary, revision
```

新增端点：

```text
GET /api/sessions/{session_id}/diff/files/{encoded_path}?limit={bytes}
```

该端点对解码后的路径执行 workspace 边界校验，拒绝绝对路径、`..` 和越界 symlink；文本 patch 默认限制 1MB，用户显式加载更多时上限 5MB。

### Snapshot

`SessionSnapshot` 新增 `activities`，从当前进程的事件历史恢复最近 100 条 runtime phase，并保留 `turnId` 和时间戳。

## 4. 关键实现说明

- 滚动：`html/body/#root` 与三栏容器固定视口，header、composer、品牌区和页签不随内容移动。
- 跟随：仅操作 transcript 自身的 `scrollTo`；`content-visibility` 延迟高度通过有限帧收敛处理，真实向上滚动会立即中止。
- 长内容：Timeline item 使用 `content-visibility: auto`；折叠 Diff 不持有 patch DOM；105 文件组件用例验证分批展示。
- 恢复：Reducer 按 `seq` 丢弃重复事件，快照不会覆盖序号更新的本地状态。
- 安全：Markdown 不使用 `dangerouslySetInnerHTML`；外链仅允许 `http`、`https`、`mailto` 并设置安全 `rel`。
- 注释：对 Grid/Flex 滚动约束、智能跟随阈值、重连上限和 Diff 路径安全不变量补充了原因说明。

## 5. 实测数据

| 指标 | 结果 |
|---|---:|
| 1280x720 document 高度 | 720px |
| 长会话 transcript 高度 / scrollHeight | 549px / 6119px |
| 中栏上滚后 window.scrollY | 0 |
| 上滚后左右栏/header top | 0 / 0 / 0 |
| 回到最新后的底部距离 | 0px |
| Diff 初始 patch DOM 数 | 0 |
| 展开单文件后的 patch DOM 数 | 1 |
| 390x844 document 高度 | 844px |
| 移动端抽屉关闭状态 | `inert=true`, `aria-hidden=true` |
| 浏览器 console warning/error | 0 |
| 生产 JS | 218.07KB，gzip 68.31KB |

## 6. 接下来可优化

1. 使用成熟的 Markdown/GFM 解析器补齐标题、列表、表格、引用和行内代码，同时保持严格白名单净化。
2. 将 Activity 持久化到 SessionData，使服务进程重启后也能恢复，而不只覆盖浏览器刷新/重连。
3. Diff 更新事件携带受影响路径，实现文件级缓存失效；单文件 Git patch 改为流式限长读取，进一步降低超大 patch 峰值内存。
4. 会话达到数千个 timeline item 后引入真正的窗口虚拟化；当前 `content-visibility` 已覆盖一般长会话，但不是完整虚拟列表。
5. 增加 App 级重连时钟、移动焦点循环和 20 连续 delta 的自动化浏览器用例，减少手工浏览器验收占比。
6. 后续建议项可继续补充会话搜索/重命名/删除、草稿按 session 保存、主题手动切换和 Diff 过滤。

测试明细见 `docs/newTask/test/MC-WEB-UX-20260621_TEST_REPORT.md`。
