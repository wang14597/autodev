# WorkItem 控制台（前端 + 后端）设计

> 日期：2026-07-22
> 状态：设计已定（brainstorming 三项关键决策已确认），按"设计并落地"实现
> 背景：平台面向广大用户，控制台的中心实体必须是领域聚合根 **WorkItem**，贴合真实业务流程：用户创建 WorkItem → 填需求 → 关联一个项目(git 仓库) → 据需求自动收集上下文 → (后续走方案/评审/开发…)，且多 WorkItem 可并行。此前两版前端（context-preview 单页、绕开领域的 Vite SPA）方向错误，已清理；本设计从零重建前后端。

## 1. 决策（已确认）

1. **后端用真实领域 WorkItem**：web 层不再自造 Preview 模型，改用领域 `WorkItem` 聚合根 + `SqliteWorkItemRepository` + 真实 `Engine`/handler 驱动。与平台 DDD 对齐，为 F5–F8 铺路。
2. **创建后自动收集**：提交需求即在后台自动驱动 INTAKE→TRIAGE→CONTEXT，进度轮询展示。
3. **展示完整流水线**：UI 展示 INTAKE→…→DONE 全阶段路线图；当前只有到 CONTEXT 可真跑，之后阶段置灰标"待建设"。

## 2. 中心实体与词汇（统一语言）

- **WorkItem（工作项）**：一次研发需求的载体。字段来自领域：`id`、`requirement`(goal/target_repo/…)、`repo_ref`(关联项目)、`type`(分诊得出)、`state`(当前阶段)、`history`(状态转移审计)、`artifact_versions`(各阶段产物)、时间戳。
- **Project（项目）**：一个 git 仓库，来自配置 `repo_map`(name→git URL)。创建 WorkItem 时从中选一个关联。
- **阶段（WorkflowState 线性主链）**：需求录入 INTAKE → 分诊 TRIAGE → 上下文 CONTEXT → 方案 DESIGN → 评审 REVIEW → 开发 IMPL → 验收 ACCEPT → 测试 VERIFY → 提交MR SUBMIT_MR → 完成 DONE；另有 WAIT_HUMAN(人审挂起)、FAILED(失败) 为覆盖态。
- **上下文简报**：CONTEXT 阶段 `ContextArtifact.context_file` 指向的 Markdown。

## 3. 后端（FastAPI 驱动侧适配器）

新增 `src/autodev/webapp/`（全新，非复用旧 Preview 代码）：

- **组合根 `deps.py`/`config.py`**：从环境变量装配真实依赖 —— `SqliteWorkItemRepository`、`InMemoryEventBus`、`StageContext`（`GitWorkspaceAdapter`(F1) + `ClaudeContextAdapter`(F3) 为真实；DESIGN 及之后的端口用"未实现"桩适配器，被调用即抛 `StageError(FATAL,"stage not yet implemented")`，正常流程不会触达）、`TriagePolicy`/`GatePolicy`、`Engine`、线程池执行器、`repo_map`。
- **应用服务 `WorkItemConsoleService`**（可注入假件单测）：
  - `create(goal, repo) -> id`：校验非空；`WorkItem.create(...)`（Requirement + RepoRef + 默认 AutonomyDial）；`repo.save`；投递后台 `_drive(id)`；返回 id。
  - `_drive(id)`（**有界驱动**）：循环 `wi = repo.get(id)`；当 `wi.state in {INTAKE,TRIAGE,CONTEXT}` 且 `wi.is_runnable()` 时 `engine.advance(wi)`（引擎内部已做失败翻译/重试/转移/事件/落盘），否则跳出。CONTEXT 成功后转移到 DESIGN → 跳出并静止；失败则引擎收敛到 FAILED → 跳出。**绝不进入未实现阶段。**
  - `get(id)`、`list()`：读仓库；`list` 新到旧。
- **视图映射 `views.py`**：把领域 `WorkItem` 投影成前端 DTO（避免领域对象直接序列化）：`id/goal/repo/type/state/created_at/updated_at`、`stages`(每阶段 status: done|current|pending|blocked，据 history+当前 state 计算，DESIGN 及之后标 blocked="待建设")、`context`(若有：读 `context_file` 内容 → markdown + 路径)、`failure`(FAILED 时的原因，取自 history 末条 reason)。
- **路由**：
  - `GET /api/projects` → 配置的项目名列表(repo_map keys)。
  - `POST /api/workitems` `{goal, repo}` → `{id}`；空值 400。
  - `GET /api/workitems` → WorkItem 概要列表(新到旧)。
  - `GET /api/workitems/{id}` → WorkItem 详情 DTO；未知 404。
  - 托管前端构建产物(见 §5)。
- **并发**：后台线程池并行驱动多个 WorkItem；`SqliteWorkItemRepository` 每调用独立连接、开 WAL + busy_timeout，规避锁争用。

## 4. 前端（现代工程，全新重建）

`frontend/`：Vite + React + TypeScript；TanStack Query(服务端状态/轮询)；React Router(多页面)；设计令牌 + CSS Modules；字体与 Markdown 渲染库本地打包(运行时零公网 CDN)。沿用"冷色仪表盘"设计身份（令牌/字体不变），但**以 WorkItem 为中心重构信息架构与文案**。

- **页面**：
  - **工作台 `/`（WorkItem 列表 + 新建）**：左侧「新建工作项」表单（需求文本域 + 项目选择/自由输入 → 提交）；主区是 WorkItem 卡片/行列表（并行的多个工作项，每个显示需求摘要、项目、状态徽标、当前阶段、时间）。点击进入详情。
  - **工作项详情 `/workitems/:id`**：
    - 概览：需求、关联项目、类型、当前状态。
    - **生命周期流水线**：INTAKE→…→DONE 横向/纵向步骤条，每阶段按 DTO 的 status 着色（已完成/进行中/待运行/待建设-置灰）；运行中阶段用 amber 声呐信号。
    - **阶段产物**：CONTEXT 完成后在该阶段下展开「上下文简报」（Newsreader 渲染的 Markdown，经 DOMPurify 消毒）+ context 文件路径。失败则显示失败原因面板。
    - 运行中以 TanStack Query 2s 轮询详情，state 进入静止态（DESIGN/FAILED/WAIT_HUMAN/DONE）停止轮询。
- **组件**：AppHeader、NewWorkItemForm、WorkItemList/Card、StatusBadge、LifelinePipeline(阶段步骤条)、StageArtifact/BriefDocument、FailurePanel、EmptyState、Notice。
- **数据层**：`api/{types,client}` 与后端 DTO 一一对应；`hooks/`(useProjects/useWorkItems/useWorkItem(轮询)/useCreateWorkItem)。
- **安全/可达性**：Markdown 先消毒后渲染；用户/模型字符串走文本节点；键盘焦点可见；prefers-reduced-motion 尊重；响应式到移动端。

## 5. 前后端集成

- 开发：`npm run dev`(Vite :5173)，`/api` 代理到 FastAPI :8000。
- 生产：`npm run build` → `frontend/dist`，FastAPI 托管（SPA 客户端路由回退 + 目录穿越防护）；未构建回退占位页、API 仍可用。`AUTODEV_FRONTEND_DIST` 可覆盖产物目录。

## 6. 测试与门禁

- **后端**：`WorkItemConsoleService` 单测（注入 `InMemoryWorkItemRepository` + FakeWorkspace/FakeContext + 同步执行器）：create→驱动到 CONTEXT→状态/产物正确；驱动**止于 DESIGN**（不触达未实现阶段）；F1/F3 抛 StageError → 引擎收敛 FAILED、DTO 有失败原因；list/get；views 投影正确（stages 状态、blocked 标记）。端点测试（TestClient + 假 service）：路由形状/状态码/404/400、SPA 托管/回退/穿越防护。
- **前端**：Vitest + RTL：api client、hooks 轮询停止条件、NewWorkItemForm 校验、LifelinePipeline 阶段着色、BriefDocument 消毒、StatusBadge。门禁：typecheck/oxlint/vitest/build/prettier，并接入 GitHub Actions frontend job。
- **Python**：pytest / ruff / mypy / tests-docs 全绿；新增 web 可选依赖组；CHANGELOG + README 更新。

## 7. 范围边界与非目标

- 只做 WorkItem 控制台 + 驱动到 CONTEXT；DESIGN 及之后为置灰占位，随 F5–F8 逐步接入（届时扩展有界驱动的阶段集合 + 端点/DTO）。
- 不做鉴权/多租户（内网自用）；不做 WorkItem 删除/取消（后续）；不接飞书/GitLab MR。
- 复用领域与 F1/F3，不改核心域与既有适配器。

## 8. 验收标准

- 用户可在工作台创建多个并行 WorkItem、看到各自状态推进；详情页展示完整生命周期与（完成后的）上下文简报。
- 后端跑在真实 `WorkItem`/`SqliteWorkItemRepository`/`Engine`；有界驱动止于 DESIGN，绝不进入未实现阶段（有测试保证）。
- 前后端门禁全绿；`python -m autodev.webapp`（构建后）一体提供控制台；`npm run dev` 开发热更新可用。
