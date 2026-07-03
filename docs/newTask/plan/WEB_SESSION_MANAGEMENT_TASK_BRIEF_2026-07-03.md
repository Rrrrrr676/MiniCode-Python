# MiniCode Web 会话管理任务书

| 项目 | 内容 |
|---|---|
| 文档日期 | 2026-07-03 |
| 任务编号 | `MC-WEB-SESSION-MGMT-20260703` |
| 任务名称 | Web 会话重命名、归档、删除与列表整理 |
| 依赖版本 | `0.1.2-web-readability` |
| 建议目标版本 | `0.1.3-web-session-management` |
| 优先级 | P0 / P1 |
| 预计工期 | 2-3 个工作日 |
| 依据 | 用户 Web 截图、当前 `minicode/web` API、`minicode/persistence/session_storage.py` 现状 |

## 1. 背景

当前 MiniCode 本地 Web 控制台已经支持创建、恢复和展示会话，但会话列表只提供“新建”和“选择”两个动作。随着真实使用次数增加，左侧列表会快速堆积大量重复标题，例如“帮我分析一下这个项目的结构”“New session”等。用户无法在 Web 页面中删除空会话、隐藏旧会话、重命名重要会话，也无法区分哪些会话值得保留。

现有代码状态：

- 后端 Web API 暂只暴露 `GET /api/sessions`、`POST /api/sessions`、`GET /api/sessions/{session_id}`、发消息、取消、Diff 和事件流；
- 前端左侧 session item 只是普通按钮，没有会话菜单和批量整理入口；
- 底层 persistence 已有 `delete_session(session_id)`，可以删除 session JSON、delta 文件并更新 `sessions_index.json`；
- `SessionSummary.title` 目前由 `first_message` 或 `last_message` 推导，缺少稳定的用户自定义标题；
- 会话文件保存在 `~/.mini-code/sessions/`，索引保存在 `~/.mini-code/sessions_index.json`，Web 侧按 workspace 过滤展示。

本任务目标是在不改变 Agent 核心执行链路的前提下，为 Web 控制台补齐基础会话管理能力，并保持 local-first、安全可恢复、不会误删工作区文件的产品语义。

## 2. 核心问题

### 2.1 用户体验问题

1. 会话越来越多，用户难以找到刚才或重要的会话；
2. 多个会话标题来自同一句首条问题，列表辨识度低；
3. 空会话和测试会话无法清理；
4. 用户可能误以为删除会话会回滚右侧 Changes 中的文件改动；
5. 重要会话和临时会话没有区分方式；
6. 会话失败、未完成、已取消等状态虽然存在，但没有整理和筛选入口；
7. 当前选中会话被删除后的页面状态没有定义。

### 2.2 技术问题

1. `SessionMetadata` 没有 `title`、`archived_at`、`deleted_at` 等管理字段；
2. `list_sessions()` 无法按 archived / active 过滤；
3. `delete_session()` 是硬删除能力，直接暴露给 UI 风险较高；
4. Web runner 的 `_states`、pending permission 和 active turn 内存状态需要和删除/归档操作保持一致；
5. 前端 `api` client 没有 patch/delete/bulk 方法；
6. 前端会话列表状态与 WebSocket snapshot 状态需要在管理操作后同步刷新；
7. 旧 session JSON 与旧 `sessions_index.json` 必须向后兼容。

## 3. 产品目标

任务完成后，用户应能够：

1. 在每个会话项右侧打开 `...` 菜单；
2. 对会话执行 `Rename`、`Archive`、`Delete...` 操作；
3. 默认从主列表隐藏 archived 会话，并可切换到 Archived 视图找回；
4. 对 archived 会话执行 `Restore` 或 `Delete permanently`；
5. 批量清理当前 workspace 的空会话；
6. 为会话设置稳定标题，不再完全依赖 first/last message；
7. 删除会话前看到明确确认文案：删除只删除会话记录，不会回滚工作区文件改动；
8. 删除当前会话后自动切到下一个合适会话，没有可用会话时自动创建新会话；
9. 在运行中的会话上禁止危险管理操作，提示用户先 Cancel 当前 turn；
10. 保持刷新、重连、事件去重和现有 Diff/Activity 行为稳定。

## 4. 非目标

本任务不做：

- 云端同步、登录、团队共享；
- Git commit、branch、PR 或文件回滚；
- 删除工作区文件、清空右侧 Changes；
- 会话全文搜索；
- 会话标签系统；
- 多工作区全局会话中心；
- 加密存储和跨设备备份；
- 完整审计日志 UI；
- TUI 会话管理命令扩展，除非实现中需要同步底层能力测试。

## 5. 产品设计

### 5.1 左侧会话项

每个 session item 的结构建议：

```text
┌────────────────────────────────────┐
│ 会话标题                      ...  │
│ 2 messages · Completed · 20:05     │
└────────────────────────────────────┘
```

要求：

- 整个会话项仍可点击选择会话；
- `...` 是独立按钮，点击不触发选择；
- hover/focus 时显示菜单按钮，键盘 Tab 可访问；
- selected 状态、menu open 状态和 focus 状态视觉上可区分；
- 标题单行省略，tooltip 或 title 属性显示完整标题；
- 状态文案沿用当前 `STATUS_LABELS`；
- 空会话显示 `Empty · Ready` 或 `0 messages · Ready`；
- archived 视图中显示 `Archived` 标记。

### 5.2 会话菜单

主列表 active 会话菜单：

```text
Rename
Archive
Delete...
```

Archived 视图菜单：

```text
Rename
Restore
Delete permanently...
```

运行中或等待权限的会话菜单：

```text
Rename
Archive              disabled
Delete...            disabled
```

禁用原因：

```text
Cancel the running turn before archiving or deleting this session.
```

### 5.3 重命名

交互要求：

- 点击 `Rename` 后进入轻量编辑态；
- 可用 inline input，也可用 modal/dialog；
- 默认填入当前展示标题；
- Enter 保存，Escape 取消；
- 空字符串表示清除自定义标题，恢复自动标题；
- 最大长度 120，与 `CreateSessionRequest.title` 保持一致；
- 保存失败时不丢失输入；
- 保存成功后当前列表和 header 标题立即更新。

标题展示优先级：

```text
custom title > first user message > last message > New session
```

注意：`custom title` 是用户显式设置的稳定字段，不应被后续 message 覆盖。

### 5.4 归档

归档语义：

- 归档只隐藏会话，不删除任何 JSON、delta、checkpoint、transcript；
- Archived 视图可以找回；
- 归档当前选中会话后，自动选择下一个 active 会话；
- 如果没有 active 会话，自动创建一个新会话；
- 已归档会话不可直接发送新消息，除非先 Restore；
- 归档操作不影响右侧 Changes，因为 Changes 来自当前 Git workspace。

列表过滤：

```text
All active | Archived
```

首轮可以只做两个 segmented controls：

```text
Active | Archived
```

后续可扩展为：

```text
All | Active | Failed | Incomplete | Archived
```

### 5.5 删除

删除分两层：

1. 主列表中的 `Delete...`：允许删除 active 会话，但必须弹确认框；
2. Archived 视图中的 `Delete permanently...`：文案更强，强调不可恢复。

确认文案必须包含：

```text
Delete this session record permanently?

This only deletes the saved conversation, transcript, checkpoints, and replay data.
It will not revert or delete files in the workspace. Current Changes are Git working tree changes.
```

中文界面可以使用：

```text
确定永久删除这个会话记录吗？

这只会删除保存的对话、transcript、checkpoint 和 replay 数据。
它不会回滚或删除工作区文件。右侧 Changes 是当前 Git 工作区改动，不属于单个会话。
```

按钮：

```text
Cancel
Delete session
```

Archived 视图按钮：

```text
Cancel
Delete permanently
```

删除保护：

- 运行中或等待权限的会话不能删除；
- 当前 workspace 之外的 session 不能通过 Web API 删除；
- session 不存在时返回稳定 `SESSION_NOT_FOUND`；
- 删除当前选中会话后，前端不得停留在不存在的 `selectedSessionId`；
- 删除操作成功后，WebSocket 应关闭或自然断开，不应无限重连不存在会话。

### 5.6 批量清理空会话

主列表底部或列表 header 增加轻量入口：

```text
Clean empty sessions
```

定义：

- 当前 workspace；
- 未归档或全部 active 视图中的空会话；
- `messageCount == 0`；
- 非当前运行中；
- 非当前 selected session，或允许删除后自动切换。

确认文案：

```text
Delete 6 empty sessions?

Only sessions with 0 messages in this workspace will be deleted.
Workspace files will not be changed.
```

后端建议返回：

```json
{
  "deleted": 6,
  "skipped": 1,
  "sessionIds": ["abc123", "def456"]
}
```

若首轮时间紧张，批量清理可作为 P1，但 API 和测试应预留清晰路径。

## 6. 数据模型方案

### 6.1 SessionMetadata 新字段

建议给 `SessionMetadata` 增加以下字段：

```python
title: str = ""
archived_at: float = 0.0
deleted_at: float = 0.0
```

字段语义：

- `title`：用户自定义标题，空字符串表示使用自动标题；
- `archived_at`：0 表示未归档，非 0 表示归档时间；
- `deleted_at`：首轮可暂不使用，保留给未来软删除/回收站；若不做回收站，可不加。

最小实现建议：

```python
title: str = ""
archived_at: float = 0.0
```

不建议首轮做 `deleted_at` 软删除，原因是已有 `delete_session()` 硬删除能力且需要避免存储膨胀。但任务文档应保留未来演进空间。

### 6.2 SessionData 序列化

`save_session()` 的 full save 需要写入 metadata 新字段：

```json
"metadata": {
  "session_id": "...",
  "title": "...",
  "archived_at": 0.0
}
```

`_save_session_index()` 也要写入同样字段。列表读取主要依赖 index，所以 index 必须保持完整。

### 6.3 向后兼容

旧 JSON 不含 `title` 和 `archived_at` 时：

- dataclass 默认值应自动填充；
- `list_sessions()` 不应因为旧字段缺失失败；
- `load_session()` 不应因为 metadata 新字段缺失失败；
- `_load_session_index()` 对损坏或旧格式 index 仍应尽量容错。

建议测试旧索引：

```json
{
  "abc123": {
    "session_id": "abc123",
    "created_at": 1,
    "updated_at": 2,
    "first_message": "hello",
    "workspace": "/tmp/demo"
  }
}
```

期望：

- `title == ""`；
- `archived_at == 0.0`；
- 仍能正常显示为 `hello`。

### 6.4 标题计算

建议集中实现一个 helper，避免前后端重复猜：

```python
def display_title(metadata: SessionMetadata) -> str:
    return metadata.title or metadata.first_message or metadata.last_message or "New session"
```

Web `SessionSummary.title` 使用该结果。

若后续需要同时返回自动标题和自定义标题，可扩展：

```json
{
  "title": "Frontend bug triage",
  "customTitle": "Frontend bug triage",
  "fallbackTitle": "帮我分析一下这个项目的结构"
}
```

首轮不强制。

## 7. 后端 API 设计

### 7.1 Schema

新增请求模型：

```python
class UpdateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    archived: bool | None = None
```

新增批量请求：

```python
class DeleteEmptySessionsRequest(BaseModel):
    archived: bool = False
```

可选响应：

```python
class SessionMutationResponse(BaseModel):
    session: SessionSummary | None = None
    sessions: list[SessionSummary] = Field(default_factory=list)
```

建议让 mutation 后返回最新 `SessionSummary` 或最新列表，减少前端二次请求。不过为了保持现有 API 简洁，也可以 mutation 后前端调用 `listSessions()`。

`SessionSummary` 建议新增：

```python
customTitle: str = ""
archived: bool = False
archivedAt: float = 0.0
```

如果不想扩大响应，可至少增加：

```python
archived: bool = False
```

### 7.2 列表 API

现有：

```text
GET /api/sessions
```

建议扩展 query：

```text
GET /api/sessions?archived=false
GET /api/sessions?archived=true
GET /api/sessions?archived=all
```

默认：

```text
archived=false
```

这样主列表不会显示 archived 会话，符合“归档就是隐藏”的直觉。

### 7.3 更新会话

新增：

```text
PATCH /api/sessions/{session_id}
```

请求：

```json
{
  "title": "Frontend session cleanup",
  "archived": true
}
```

行为：

- `title` 为字符串时更新自定义标题；
- `title` 为 `""` 时清除自定义标题；
- `archived: true` 设置 `archived_at = now`；
- `archived: false` 设置 `archived_at = 0.0`；
- 未提供字段保持不变；
- 成功后 force full save，确保 metadata 和 index 一致。

错误：

| 场景 | HTTP | code |
|---|---:|---|
| session 不存在 | 404 | `SESSION_NOT_FOUND` |
| workspace 不匹配 | 404 | `SESSION_NOT_FOUND` |
| running / waiting_permission 时归档 | 409 | `SESSION_BUSY` |
| title 过长 | 422 | `VALIDATION_ERROR` |

注意：

- 运行中允许 Rename，但不允许 Archive；
- 是否允许 archived session Rename：允许；
- 是否允许 archived session 发消息：不允许，或自动 restore 后再发送。首轮建议不允许并返回 `SESSION_ARCHIVED`。

### 7.4 删除会话

新增：

```text
DELETE /api/sessions/{session_id}
```

建议 query：

```text
DELETE /api/sessions/{session_id}?permanent=true
```

首轮可以不要求 query，但 API 内部语义必须是永久删除。

行为：

1. 验证 session 存在且 workspace 匹配；
2. 验证没有 active turn；
3. 清理 pending permission；
4. 从 runner `_states` 移除；
5. 调用底层 `delete_session(session_id)`；
6. 发布可选 `session.deleted` 事件，或让 WebSocket 断开后前端刷新列表；
7. 返回 `204 No Content` 或 `{ "deleted": true }`。

建议返回 JSON，方便前端显示 notice：

```json
{
  "deleted": true,
  "sessionId": "abc123"
}
```

错误：

| 场景 | HTTP | code |
|---|---:|---|
| session 不存在 | 404 | `SESSION_NOT_FOUND` |
| workspace 不匹配 | 404 | `SESSION_NOT_FOUND` |
| running / waiting_permission | 409 | `SESSION_BUSY` |
| persistence 删除失败 | 500 | `SESSION_DELETE_FAILED` |

### 7.5 批量删除空会话

新增：

```text
POST /api/sessions/delete-empty
```

请求：

```json
{
  "archived": false
}
```

行为：

- 只处理当前 workspace；
- 只删除 `messageCount == 0` 的会话；
- 跳过 running / waiting_permission；
- 可选择只删 active，或只删 archived；
- 返回删除数量、跳过数量和删除 ID。

响应：

```json
{
  "deleted": 6,
  "skipped": 1,
  "sessionIds": ["abc123", "def456"]
}
```

### 7.6 Runner 方法

`WebSessionRunner` 建议新增：

```python
def list_session_summaries(self, *, archived: bool | None = False) -> list[SessionSummary]:
    ...

def update_session(self, session_id: str, *, title: str | None = None, archived: bool | None = None) -> SessionSummary:
    ...

def delete_session_record(self, session_id: str) -> bool:
    ...

def delete_empty_sessions(self, *, archived: bool = False) -> dict[str, object]:
    ...
```

实现注意：

- 所有 mutation 使用同一个 lock；
- 删除前读取 persisted session，避免 `_states` 中没有加载时误判；
- workspace 比较继续使用 `Path(...).resolve()`；
- active turn 检查要同时看 `state.status` 和 `state.future.done()`；
- 删除当前 `_active_session_id` 对应 session 时必须拒绝；
- 删除时 pending permission 要 resolve 为 deny 或直接移除，避免 worker 等待；
- 删除成功后 broker 中旧事件可以保留在内存，或新增 broker 清理方法；首轮建议清理，防止内存长期增长。

可选新增：

```python
EventBroker.drop_session(session_id)
```

用于删除会话后释放 `_events` 和 `_sequences`。

## 8. 前端设计

### 8.1 API client

`web/src/api/client.ts` 新增：

```ts
listSessions: (archived?: boolean | "all") => ...
updateSession: (sessionId: string, patch: { title?: string; archived?: boolean }) => ...
deleteSession: (sessionId: string) => ...
deleteEmptySessions: (archived?: boolean) => ...
```

`web/src/api/types.ts` 扩展：

```ts
export interface SessionSummary {
  sessionId: string;
  createdAt: number;
  updatedAt: number;
  title: string;
  customTitle?: string;
  messageCount: number;
  status: TurnStatus;
  archived?: boolean;
  archivedAt?: number;
}
```

### 8.2 App 状态

新增状态：

```ts
const [sessionView, setSessionView] = useState<"active" | "archived">("active");
const [menuSessionId, setMenuSessionId] = useState("");
const [renamingSessionId, setRenamingSessionId] = useState("");
const [deleteTarget, setDeleteTarget] = useState<SessionSummary | null>(null);
const [isManagingSession, setIsManagingSession] = useState(false);
```

建议拆分组件，避免 `App.tsx` 继续膨胀：

```text
web/src/features/sessions/
  SessionRail.tsx
  SessionItem.tsx
  SessionActionsMenu.tsx
  RenameSessionDialog.tsx
  DeleteSessionDialog.tsx
  sessionSelection.ts
```

首轮如果不拆，也要把纯逻辑 helper 放出：

```ts
selectNextSessionAfterRemoval(sessions, removedId, currentId)
```

### 8.3 会话选择策略

删除或归档当前 selected session 后：

1. 获取最新 active sessions；
2. 优先选择被删除项后面的会话；
3. 若没有后面的，选择前一个；
4. 若列表为空，创建新会话；
5. 设置 `selectedSessionId`；
6. 重置 transcript state；
7. 关闭 mobile drawer/menu/dialog。

伪代码：

```ts
async function moveAfterSessionRemoved(removedId: string) {
  const items = await api.listSessions(false);
  setSessions(items);
  const next = chooseNextSession(items, removedId, selectedSessionId);
  if (next) {
    setSelectedSessionId(next.sessionId);
    return;
  }
  const created = await api.createSession();
  setSelectedSessionId(created.sessionId);
  setSessions(await api.listSessions(false));
}
```

### 8.4 菜单交互

要求：

- 菜单按钮有 `aria-label="Session actions for {title}"`；
- 菜单打开后 Escape 关闭；
- 点击外部关闭；
- 选择菜单项后关闭；
- 删除确认 dialog 打开后焦点进入 dialog；
- dialog 关闭后焦点回到原菜单按钮或 session item；
- 移动端 drawer 内菜单不能把焦点漏到背景；
- 菜单不得被左侧 rail 边界裁剪，必要时使用 absolute/fixed 层。

如果不引入新 UI 库，建议使用原生 button + 简单 popover 状态。不要引入重量级组件库。

### 8.5 删除确认 Dialog

Dialog 内容：

```text
Delete session?

"帮我分析一下这个项目的结构"

This only deletes the saved conversation, transcript, checkpoints, and replay data.
It will not revert or delete files in the workspace. Current Changes are Git working tree changes.
```

Checkbox 可选：

```text
I understand workspace files will not be changed.
```

首轮不强制 checkbox，确认文案和危险按钮足够即可。

按钮：

```text
Cancel
Delete session
```

危险按钮颜色要明显，但不使用过饱和大面积红色；保持当前设计系统克制。

### 8.6 归档视图

左侧顶部建议：

```text
+ New session

[Active] [Archived]
```

Archived 为空：

```text
No archived sessions.
```

Active 为空：

```text
No active sessions.
```

但启动时如果 active 为空，仍自动创建一个新会话，避免主对话区无 selected session。

### 8.7 Clean empty sessions

位置建议：

- session list header 或底部 footer 上方；
- 只有存在空会话时显示；
- 文案：`Clean empty sessions`；
- 点击后显示确认 dialog；
- 清理后显示 notice：`Deleted 6 empty sessions.`

首轮可只清理 active 空会话。Archived 空会话在 Archived 视图中清理。

## 9. 样式要求

保持现有 Web 控制台风格：

- 卡片 radius 不超过 8px；
- session item 不做嵌套卡片；
- 菜单紧凑、可扫描；
- 菜单和 dialog 不能遮挡或挤压主对话；
- 左侧 rail 宽度不因菜单出现而变化；
- hover/focus 状态清晰；
- 390px 移动端下菜单与 dialog 不溢出；
- 不使用大面积装饰渐变；
- 不引入新的主题色体系。

建议 CSS class：

```css
.session-item-row
.session-item-main
.session-actions-button
.session-actions-menu
.session-filter
.session-dialog
.danger-button
```

## 10. 安全与隐私

### 10.1 删除边界

删除会话只允许删除：

```text
~/.mini-code/sessions/{session_id}.json
~/.mini-code/sessions/deltas/{session_id}/
~/.mini-code/sessions_index.json 中对应索引
```

不得删除：

- workspace 文件；
- Git tracked/untracked 文件；
- `.mini-code-memory/`；
- settings、MCP、skills 配置；
- 其他 workspace 的 session。

### 10.2 workspace 校验

所有 Web session mutation 都必须复用现有 workspace 校验：

```python
Path(session.workspace).resolve() == Path(self.workspace).resolve()
```

不匹配时返回 404，避免泄露其他 workspace session 是否存在。

### 10.3 Secret 脱敏

Rename 标题和 API 响应仍要经过 Web sanitize 边界，避免用户手动把 token 放进 title 后被不受控传播。列表展示可以显示用户输入标题，但如果现有 `sanitize_for_web` 能覆盖字符串，应在返回前使用。

### 10.4 并发

删除和归档必须和 turn 执行互斥：

- active turn 期间禁止 archive/delete；
- rename 可以允许，但需要 lock；
- pending permission 期间禁止 archive/delete；
- close runner 时仍按现有逻辑 deny pending permission。

## 11. 任务分解

| 编号 | 优先级 | 任务 | 交付物 | 完成标准 |
|---|---|---|---|---|
| SM-001 | P0 | Session metadata 扩展 | `SessionMetadata` 字段、序列化、索引兼容 | 旧 session 可读，新字段可保存 |
| SM-002 | P0 | 标题计算与重命名底层能力 | helper、storage/runner 更新方法 | custom title 优先且不会被 message 覆盖 |
| SM-003 | P0 | 归档底层能力 | `archived_at` 保存、列表过滤 | active 默认隐藏 archived |
| SM-004 | P0 | 删除 Web runner 能力 | runner delete 方法、busy 保护、workspace 校验 | 删除只影响当前 workspace session 记录 |
| SM-005 | P0 | Web API 路由 | `PATCH /api/sessions/{id}`、`DELETE /api/sessions/{id}` | 错误 envelope 稳定，状态码正确 |
| SM-006 | P0 | 前端 API types/client | TS 类型和 client 方法 | 前端可调用 rename/archive/delete |
| SM-007 | P0 | Session item 菜单 | `...` 菜单、Rename/Archive/Delete | 鼠标和键盘均可操作 |
| SM-008 | P0 | 删除确认 dialog | 确认文案、危险按钮、成功刷新 | 用户明确知道不会回滚文件 |
| SM-009 | P0 | 选中会话删除后的迁移 | selection helper 和 App 流程 | 不停留在已删除 session |
| SM-010 | P1 | Archived 视图与 Restore | filter UI、restore action | archived 可找回 |
| SM-011 | P1 | Clean empty sessions | 批量 API、确认 dialog、notice | 可清理 0 message 会话 |
| SM-012 | P1 | 可访问性和移动端 | focus、Escape、drawer 内菜单 | 390px 和键盘路径可用 |
| SM-013 | P0 | 自动化测试 | Python、TS、组件测试 | 关键路径全部覆盖 |
| SM-014 | P0 | 文档与完成报告 | usage 更新、report/test report | 启动和使用说明同步 |

## 12. 实施顺序

建议按下面顺序开发，降低返工：

1. 扩展 metadata 和 serialization；
2. 增加 runner 层 update/delete/list filtering；
3. 增加 API 和后端测试；
4. 扩展前端 client/types；
5. 实现 session item 菜单和 rename；
6. 实现 archive/restore 和 active/archived filter；
7. 实现 delete confirm 和 selected session 切换；
8. 实现 clean empty sessions；
9. 做移动端和键盘可访问性收尾；
10. 更新 docs 和报告。

如果时间不足，P0 MVP 可以只交付：

- Rename；
- Archive/Restore；
- Delete with confirmation；
- selected session 删除后自动切换；
- 后端和前端关键测试。

`Clean empty sessions` 可以作为 P1 延后，但建议同轮完成，因为它直接解决截图中的空会话堆积问题。

## 13. 验收用例

### AC-SM-01 重命名会话

前置：存在一个已完成会话，标题来自 first message。

步骤：

1. 打开会话菜单；
2. 点击 Rename；
3. 输入 `Project structure analysis`；
4. 保存；
5. 刷新页面；
6. 发送一条新消息。

期望：

- 左侧列表和 header 显示 `Project structure analysis`；
- 刷新后仍显示自定义标题；
- 新消息不会覆盖自定义标题；
- 清空 title 后恢复 first/last message 自动标题。

### AC-SM-02 归档当前会话

前置：active 列表有 3 个会话，当前选中第 2 个。

步骤：

1. 对当前会话点击 Archive；
2. 查看 active 列表；
3. 切换到 Archived；
4. 点击 Restore。

期望：

- 被归档会话从 active 列表消失；
- 主对话自动切到下一个 active 会话；
- Archived 视图能看到该会话；
- Restore 后回到 active 列表；
- transcript、messages、checkpoints 没有丢失。

### AC-SM-03 删除非当前会话

前置：active 列表有多个 completed 会话。

步骤：

1. 打开非当前会话菜单；
2. 点击 Delete；
3. 在确认 dialog 点击 Cancel；
4. 再次点击 Delete 并确认。

期望：

- Cancel 不改变列表；
- 确认文案包含“不回滚工作区文件”的说明；
- 确认后会话从列表消失；
- `GET /api/sessions/{id}` 返回 404；
- 当前 selected session 不变化；
- 右侧 Changes 不被清空或回滚。

### AC-SM-04 删除当前会话

前置：active 列表有 2 个会话，当前选中第 1 个。

步骤：

1. 删除当前会话；
2. 等待列表刷新。

期望：

- 页面自动选择剩余会话；
- WebSocket 不对旧 session 无限重连；
- transcript state 重置为新 selected session；
- header title 和 composer 状态正确。

### AC-SM-05 删除最后一个 active 会话

前置：active 列表只有 1 个 idle/completed 会话。

步骤：

1. 删除该会话；
2. 等待操作完成。

期望：

- 后端删除旧会话；
- 前端自动创建新会话；
- 列表显示新会话；
- composer 可用；
- 不出现空白死状态。

### AC-SM-06 运行中会话保护

前置：一个会话处于 `running` 或 `waiting_permission`。

步骤：

1. 打开该会话菜单；
2. 尝试 Archive 或 Delete；
3. 直接调用 API 删除该 session。

期望：

- UI 上 Archive/Delete disabled；
- disabled 原因可见或可通过 tooltip/aria 描述；
- API 返回 409 `SESSION_BUSY`；
- Agent turn 不受影响。

### AC-SM-07 Archived 会话不能直接发消息

前置：存在 archived 会话。

步骤：

1. 切到 Archived；
2. 选择 archived 会话；
3. 尝试发送消息。

期望：

- Composer disabled 或显示需要 Restore；
- API 若被直接调用，返回稳定错误；
- Restore 后可以正常发送。

### AC-SM-08 清理空会话

前置：当前 workspace 有 6 个 0 message 会话、2 个非空会话、1 个 running 空会话。

步骤：

1. 点击 Clean empty sessions；
2. 确认删除。

期望：

- 确认文案显示将删除 6 个或说明会跳过 running；
- 非空会话保留；
- running 会话跳过；
- 返回 notice 显示 deleted/skipped；
- workspace 文件不变化。

### AC-SM-09 旧会话兼容

前置：`sessions_index.json` 中存在不含 `title` 和 `archived_at` 的旧 metadata。

步骤：

1. 启动 Web；
2. 打开会话列表；
3. 重命名该旧会话；
4. 刷新。

期望：

- 旧会话正常显示；
- 重命名后 index 和 session JSON 写入新字段；
- 不触发 JSON decode 或 dataclass 初始化错误。

### AC-SM-10 跨 workspace 保护

前置：`~/.mini-code/sessions_index.json` 中存在其他 workspace 的 session。

步骤：

1. 在当前 Web workspace 调用 PATCH/DELETE 其他 workspace session ID。

期望：

- 返回 404 `SESSION_NOT_FOUND`；
- 其他 workspace session 文件不变；
- 不泄露目标 workspace path。

## 14. 测试要求

### 14.1 Python 单元/集成测试

新增或扩展：

```text
tests/test_session.py
tests/test_web_api.py
tests/test_web_runner.py
```

覆盖：

- metadata 新字段保存/加载；
- 旧 metadata 兼容；
- custom title 优先级；
- archive/restore 保存到 index；
- list active 默认排除 archived；
- delete session 清理 delta 和 index；
- Web DELETE 拒绝 running session；
- Web PATCH 拒绝跨 workspace session；
- 删除当前 loaded state 后 runner 内存清理；
- delete-empty 只删除当前 workspace 0 message sessions；
- error envelope code/status 稳定。

### 14.2 前端测试

新增或扩展：

```text
web/src/features/sessions/*.test.tsx
web/src/App.test.tsx 或现有 store/component tests
```

覆盖：

- session item 菜单打开/关闭；
- Rename 保存和取消；
- Archive 后切换列表；
- Restore 后出现在 active；
- Delete dialog 文案；
- Delete cancel 不调用 API；
- Delete confirm 调用 API 并刷新；
- 删除当前 session 后选择下一个；
- 删除最后 session 后创建新 session；
- disabled busy actions；
- keyboard Escape / Tab 基础路径。

### 14.3 浏览器手测

视口：

```text
1280x720
768x1024
390x844
```

场景：

- 会话超过 20 个时菜单不被裁剪；
- 左侧 rail 独立滚动时菜单定位正确；
- mobile drawer 中菜单和 dialog 可用；
- 删除确认 dialog 不溢出；
- 200% zoom 下按钮可见；
- 删除/归档后 header、transcript、composer 无错位；
- 浏览器 console 无 React key warning 和 runtime error。

### 14.4 命令

目标验证命令：

```bash
env PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest -q tests/test_session.py tests/test_web_api.py tests/test_web_runner.py
cd web && npm run test
cd web && npm run build
git diff --check
```

如果改动影响共享 session persistence，建议再跑：

```bash
env PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest -q
```

## 15. 文档更新要求

完成实现后更新：

```text
README.md
README.zh-CN.md
docs/USAGE_GUIDE.md
docs/newTask/report/MC-WEB-SESSION-MGMT-20260703_IMPLEMENTATION_REPORT.md
docs/newTask/test/MC-WEB-SESSION-MGMT-20260703_TEST_REPORT.md
```

使用说明至少包括：

- 如何重命名会话；
- 如何归档和恢复；
- 删除会话不会回滚工作区文件；
- 如何清理空会话；
- 会话文件仍保存在 `~/.mini-code/sessions/`。

## 16. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 用户误以为删除会回滚文件 | 数据误解、信任下降 | 删除确认明确说明只删除记录，不改 workspace |
| 删除 running session 导致 worker 状态异常 | 后端异常、权限等待泄漏 | API 和 UI 双重禁止，runner lock 检查 |
| 新 metadata 字段破坏旧 session | 历史记录不可读 | dataclass 默认值和旧 JSON 测试 |
| Archived 过滤导致启动无会话 | 空白页面 | active 为空时自动创建新 session |
| 前端 selectedSessionId 指向已删除 ID | 无限重连或 404 notice | 删除/归档后统一 selection helper |
| 菜单在滚动侧栏中被裁剪 | 操作不可见 | fixed/portal 或 rail 内定位测试 |
| 批量删除误删非空 session | 数据丢失 | 后端以 persisted metadata/message count 为准，测试覆盖 |
| 跨 workspace 删除 | 隐私和数据损坏 | resolve workspace 校验，不匹配返回 404 |

## 17. 后续演进

本任务完成后可继续考虑：

- 会话全文搜索；
- pin/star 重要会话；
- 标签和项目阶段；
- 导出 session 为 Markdown/JSON；
- 会话导入；
- 回收站和保留期；
- 按 workspace 的存储用量统计；
- session compaction 和摘要索引；
- 按模型、状态、日期筛选；
- TUI 中补 `/session-rename`、`/session-archive`、`/session-delete`。

## 18. 最小可交付定义

若只交付 MVP，必须满足：

1. `SessionMetadata.title` 持久化；
2. `SessionMetadata.archived_at` 持久化；
3. Web 支持 rename/archive/restore/delete；
4. 删除有确认 dialog，文案说明不会回滚工作区文件；
5. 删除当前会话后自动选择或创建可用会话；
6. running/waiting_permission 会话不能 archive/delete；
7. 旧 session 兼容；
8. Python 和前端关键测试通过。

`Clean empty sessions` 可以作为 P1，但建议随同交付。
