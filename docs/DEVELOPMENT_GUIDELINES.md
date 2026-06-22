# MiniCode Python 开发规范

> 生效日期：2026-06-22
> 适用范围：仓库根目录下的 Python Runtime、TUI、Headless、Web、测试与文档。

本文使用以下约束词：

- **必须**：合并前不可违反；
- **应该**：默认遵守，偏离时需要说明理由；
- **可以**：根据任务选择。

## 1. 总体原则

### 1.1 Local-first

- 所有产品面默认围绕本地工作区运行；
- 新增网络监听必须默认绑定 `127.0.0.1`；
- 不能为了 Web 功能破坏离线 TUI 或 Headless 能力。

### 1.2 Runtime-first

- Agent 的真实状态必须可观察：开始、工具调用、审批、失败、完成都有明确事件；
- 不允许将异常吞掉后伪装成 `Ready`、`idle` 或成功；
- 运行时状态是后端事实，前端不能自行推断成功。

### 1.3 Recovery-first

- 文件写入继续使用 checkpoint/rewind 机制；
- 破坏性操作必须经过现有权限系统；
- 新功能必须考虑重试、断线恢复和中途失败。

### 1.4 向后兼容

- `minicode-py` 和 `minicode-headless` 是稳定入口；
- Web 是新增产品面，不得把核心逻辑搬进前端；
- 公共数据结构变化必须考虑已保存 session 的兼容读取。

## 2. 目录与模块边界

### 2.1 Python Runtime

```text
minicode/
  core/               # 标准库基础类型、状态、事件、错误、工作区边界
  config/             # 路径、设置、Provider/MCP 配置和诊断
  providers/          # Provider 纯定义、注册、适配、重试、切换
  context/            # token、上下文、prompt 与 compaction
  memory/             # 记忆模型、存储、检索、注入与 timeline
  persistence/        # session、rewind、history、user profile
  safety/             # 权限、auto mode、文件审查
  integrations/       # MCP、skills、hooks、background tasks
  observability/      # 日志、指标、决策审计
  control/            # 控制回路、稳定性、验证与恢复
  runtime/            # Agent 单轮编排、生命周期、模型/工具执行、policy
  cli/                # 命令、管理、快捷方式、安装器
  agent_loop.py       # 稳定 Runtime 转发入口
  session.py          # 稳定 Persistence 兼容入口
  tooling.py          # 稳定工具协议与执行
  tui/                # 终端产品面
  web/                # Web API、事件桥接和静态资源服务
  tools/              # 内置工具
```

### 2.2 浏览器前端

```text
web/
  src/api/            # HTTP/WebSocket 客户端与协议类型
  src/components/     # 无业务状态的通用组件
  src/features/       # chat/session/tool/permission/changes 功能模块
  src/store/          # 事件归并和页面状态
  src/styles/         # 全局变量、主题和布局
```

### 2.3 边界规则

- `core` 只能依赖 Python 标准库或 `core` 内部模块；
- `runtime` 不得导入 `minicode.tui` 或 `minicode.web`；
- 领域包不得反向导入 `runtime.runner`；
- 跨包调用使用目标包公共入口，不新增跨包 `_private_name` 导入；
- `config` 和 Provider 共同依赖 `core.provider_spec`，不得互相形成回边；
- Provider token 估算只依赖 `core.tokens`，不得依赖 Context package；
- TUI 和 Web 只消费核心 callback/事件，不复制 Agent 决策；
- `minicode/web/` 可以依赖核心 Runtime，但核心 Runtime 不反向依赖 Web；
- `web/` 不直接读取文件系统、配置文件或 API Key；
- TypeScript CLI 参考实现继续放在 `ts-src/`，浏览器前端不得混入该目录。

### 2.4 兼容门面规则

- 根目录 Python 文件必须严格匹配 `tests/test_root_package_surface.py` 白名单；
- 仅 `agent_loop.py` 与 `session.py` 是明确稳定兼容入口，不得恢复已删除旧门面；
- 测试 monkeypatch 必须指向实际查找位置，不得为了测试恢复旧定义位置；
- dataclass、Enum、TypedDict 移动前必须验证旧 JSON/session/pickle 风险；
- 删除兼容层前必须完成全仓导入与 monkeypatch 审计；
- 禁止 import hook、集中 `sys.modules` 别名或隐藏目录伪装根目录清理；
- 新实现只放在目标 package，稳定入口不得增长领域业务逻辑。

### 2.5 大模块职责规则

- Timeline 规则按 dates/numeric/travel/events 分离，Reasoner 只做组合；
- Memory 的模型、存储、检索、prompt 与 manager 分离；
- Session 的 models、storage、rewind、autosave、formatters 分离；
- Compaction dispatcher 只选择策略，budget/micro/reactive/service 独立；
- `config.__init__`、`cli.commands` 只能聚合公共 API；
- `runtime.runner` 负责单轮时序，组合初始化、prelude、control apply 和 coda 放入独立模块。

## 3. Python 代码规范

### 3.1 语言与类型

- 最低支持 Python 3.11；
- 新模块必须使用 `from __future__ import annotations`；
- 公共函数、类属性和跨模块数据必须写类型标注；
- 优先使用 `dataclass`、`TypedDict`、`Literal` 表达稳定结构；
- 不使用无边界的 `dict[str, Any]` 代替已明确的数据协议；
- `Any` 只能用于外部输入边界或兼容层，并应尽快校验和收窄。

### 3.2 命名

- 文件、函数、变量使用 `snake_case`；
- 类使用 `PascalCase`；
- 常量使用 `UPPER_SNAKE_CASE`；
- 布尔值使用 `is_`、`has_`、`can_`、`should_` 前缀；
- callback 使用 `on_<event>`，事件发布函数使用 `emit_<event>`；
- 私有实现使用单下划线，不用名称改写隐藏设计问题。

### 3.3 函数与依赖

- 函数应该保持单一职责；复杂分支应拆成可测试的小函数；
- 优先显式传入依赖，避免在函数内部创建不可替换的全局对象；
- import 默认放在模块顶部；仅为解决可选依赖或循环依赖时允许局部 import；
- 局部 import 不得与闭包变量同名，避免产生未绑定 cell；
- 不在核心模块引入仅供 UI 使用的依赖。

### 3.4 异常与日志

- 禁止空的 `except Exception: pass`，清理逻辑除外且必须有注释；
- 边界层可以捕获宽泛异常，但必须记录完整堆栈并转换成明确失败结果；
- 用户可见错误包含简短说明、错误类型和 trace ID；
- 完整堆栈进入日志，不直接倾倒到普通用户界面；
- 日志不得包含 API Key、Token、完整 Authorization Header 或未经处理的 `.env`；
- 后台线程异常必须传播到 session 状态，不能只保存在局部变量。

## 4. 并发与事件规范

### 4.1 线程规则

- `run_agent_turn()` 可以在线程池中执行；
- Worker 线程不得直接修改浏览器状态；
- 跨线程通信通过线程安全 Queue/Broker；
- 从线程向 asyncio event loop 传递数据时使用线程安全调度接口；
- 共享 map/list 必须由锁保护，或只允许单一所有者修改；
- 取消操作必须是协作式取消，不能依赖强杀线程。

### 4.2 事件规则

统一事件至少包含：

```text
seq, session_id, turn_id, type, timestamp, payload
```

- 同一 session 的 `seq` 必须单调递增；
- 事件 type 使用点分小写形式，如 `tool.started`；
- started/completed/failed 事件必须配对，异常情况以 failed 收口；
- 前端事件处理必须幂等；
- 事件协议新增字段应保持向后兼容；
- 删除或改名事件字段视为破坏性变更，必须同步迁移与测试。

### 4.3 Turn 状态机

稳定状态限定为：

```text
idle -> running -> waiting_permission -> running -> completed
                                      \-> failed
                                      \-> cancelled
```

- `failed`、`completed`、`cancelled` 是终态；
- 终态不能被 finally 块无条件覆盖为 `idle`；
- 每个 `turn.started` 最终必须对应一个 completed/failed/cancelled；
- UI 的 `Ready` 只能表示没有活跃 turn，不能代替 Provider readiness。

## 5. API 规范

### 5.1 路径与方法

- REST 路径使用复数资源名：`/api/sessions`；
- GET 只读，POST 创建或执行动作，DELETE 删除资源；
- 动作型端点使用明确后缀，如 `/cancel`、`/resolve`；
- WebSocket 仅承载实时事件，初始快照也必须有稳定 schema。

### 5.2 响应与错误

成功响应使用明确对象，不返回含义不明的裸字符串。错误响应统一为：

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session does not exist.",
    "traceId": "trace-123",
    "retryable": false
  }
}
```

- 错误 code 稳定、全大写下划线；
- message 面向用户且不泄露内部路径或 Secret；
- 对可重试错误明确标记 `retryable`；
- 输入必须在 API 边界校验，不能把未验证 JSON 直接传给工具。

### 5.3 兼容性

- OpenAPI schema 是前后端协议来源；
- 前端类型应该由 schema 生成或保持自动一致性检查；
- 新增响应字段属于兼容变更；删除、改名或改变语义必须升级协议版本。

## 6. 前端开发规范

### 6.1 TypeScript

- 开启 strict mode；
- 禁止无理由使用 `any`；
- API payload 使用判别联合或生成类型；
- 组件 props、store state 和 reducer action 必须有显式类型；
- 不在 React 组件中拼装后端协议或处理原始 WebSocket 字符串。

### 6.2 组件设计

- 通用展示组件无业务副作用；
- 网络请求和事件订阅放入 feature service/hook；
- 长输出、工具结果和 runtime 细节默认折叠；
- 用户问题、最终回答、错误和权限请求具有最高视觉优先级；
- 不以颜色作为唯一状态信号，必须同时提供文字或图标；
- 交互元素必须支持键盘焦点和可访问名称。

### 6.3 状态管理

- 后端 session/turn 状态是事实来源；
- 前端 Store 按 `seq` 归并事件并丢弃重复事件；
- 不使用“收到最后一个文本片段”推断 turn 完成；
- WebSocket 断开显示重连状态，不伪装成任务完成；
- 乐观更新只用于可安全回滚的 UI 操作。

### 6.4 样式

- 通过 CSS variables 定义颜色、间距、圆角和字体；
- 保持高信息密度，但内部诊断默认收起；
- 支持 1280px 桌面布局和窄屏抽屉布局；
- 借鉴 Claude Code 的信息架构，不复制其商标、图标或受保护视觉资产。

## 7. 安全规范

- Web 服务默认仅监听 loopback；
- 不默认开启 `Access-Control-Allow-Origin: *`；
- API Key 和 Token 只存在于后端配置层；
- API、事件、日志和前端错误不得包含 Secret；
- 文件访问必须经过 `workspace.resolve_tool_path` 或等价边界检查；
- 写文件、运行命令和工作区外访问必须经过 `PermissionManager`；
- 前端不能通过自定义 API 参数绕过工具 schema；
- WebSocket 消息必须限制大小、频率和允许的消息类型；
- HTML/Markdown 输出必须防止脚本注入；
- 所有外部 URL 打开行为应使用安全的 rel 属性。

## 8. 会话与持久化规范

- 继续复用 `SessionData` 作为会话持久化主体；
- 新字段必须提供默认值，旧 session 文件必须可读；
- 保存操作应使用原子写入或现有 session 保存机制；
- transcript 与 runtime event 的职责要清晰：前者面向会话回放，后者面向实时状态；
- 会话快照必须能恢复消息、工具状态、turn 终态和最后事件序号；
- 测试不得写入真实 `~/.mini-code`，必须 monkeypatch 到 `tmp_path`。

## 9. 测试规范

### 9.1 Python

- 使用 pytest；
- 测试文件命名为 `tests/test_<module>.py`；
- Bug 修复必须先或同时增加可复现该问题的回归测试；
- 单元测试不得调用真实模型 API、真实网络或修改用户配置；
- 时间、随机值、HOME、网络和外部进程应注入或 monkeypatch；
- 测试结束后不得残留后台线程、子进程或监听端口。

常用命令：

```bash
python -m pytest -q
python -m pytest -q tests/test_architecture.py
python -m pytest -q tests/test_tty_app.py
python -m pytest -q tests/test_web_api.py tests/test_web_events.py
```

### 9.2 前端

- reducer、事件去重、重连和状态机使用单元测试；
- 关键用户路径使用浏览器端到端测试；
- API 使用 mock server，不依赖真实模型；
- 至少覆盖正常回答、工具失败、权限等待、断线重连和 Diff 展示。

### 9.3 测试质量

- 测试行为，不锁死无关实现细节；
- 断言失败信息要能指出状态和事件；
- 不使用固定 sleep 等待并发结果，使用 Event、Queue 或条件轮询；
- 对并发和重连测试明确设置超时，防止测试永久挂起。

## 10. 依赖与配置规范

- 核心 `[project.dependencies]` 保持最小；
- Web 服务依赖放入 `[project.optional-dependencies].web`；
- 测试和格式化工具放入 dev 可选依赖；
- 新依赖必须说明用途、维护状态、License 和不可替代性；
- 禁止把密钥写入仓库、测试 fixture、截图或示例输出；
- `.env.example` 只提供占位值；
- 配置优先级和兼容行为由 `minicode.config` package 统一管理。

## 11. Git 与变更管理

- 一个提交只解决一个清晰问题；
- 不在功能提交中混入无关格式化或大规模重命名；
- 提交信息推荐使用：`feat:`、`fix:`、`test:`、`docs:`、`refactor:`；
- 修改前检查工作区，保留用户已有未提交改动；
- 不使用破坏性 reset/checkout 清理他人改动；
- 协议、配置和持久化格式变更必须在 PR 描述中单独列出。

## 12. 文档规范

- 用户可见功能同步更新 `README.md` 与 `README.zh-CN.md`；
- 模块增加或职责变化同步更新 `docs/STRUCTURE.md`；
- 启动、配置、权限变化同步更新 `docs/USAGE_GUIDE.md`；
- 架构决策说明动机、替代方案、风险和迁移路径；
- 文档中的命令必须在仓库根目录可执行；
- 日期使用 `YYYY-MM-DD`，路径使用仓库相对路径。

## 13. Review 检查表

提交评审前逐项确认：

- [ ] 核心逻辑没有依赖具体 UI；
- [ ] 所有 turn 都有明确终态；
- [ ] 后台异常对用户可见且日志可追踪；
- [ ] 权限系统没有被绕过；
- [ ] API/事件不包含 Secret；
- [ ] 线程、任务和子进程可以正常收尾；
- [ ] Bug 修复包含回归测试；
- [ ] 测试不读写真实用户目录；
- [ ] 原 TUI 与 Headless 行为保持兼容；
- [ ] 文档和启动说明已更新；
- [ ] `git diff --check` 通过；
- [ ] 相关测试和完整测试结果已记录。

## 14. Definition of Done

一项开发任务只有同时满足以下条件才算完成：

1. 功能符合验收条件；
2. 失败路径和权限路径有明确行为；
3. 自动化测试通过并覆盖回归风险；
4. 无 Secret 泄露、路径越界或默认公网暴露；
5. TUI、Headless、Web 的共享逻辑没有重复实现；
6. 文档与真实代码一致；
7. 没有未说明的占位按钮、吞错或永久后台任务。
