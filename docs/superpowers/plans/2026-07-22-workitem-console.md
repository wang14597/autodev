# WorkItem 控制台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 以领域聚合根 WorkItem 为中心，重建控制台前后端：用户创建工作项(需求+项目)→后台自动驱动 INTAKE→TRIAGE→CONTEXT→展示完整生命周期与上下文简报；多工作项并行。

**Architecture:** 后端 FastAPI 驱动侧适配器，用真实 `WorkItem`/`SqliteWorkItemRepository`/`Engine`+真实 handler；有界驱动只跑到 CONTEXT，止于 DESIGN。前端 Vite+React+TS，TanStack Query 轮询，以 WorkItem 为中心。FastAPI 生产托管前端构建产物。

**Tech Stack:** Python/FastAPI/uvicorn/pytest；Vite/React/TypeScript/TanStack Query/React Router/Vitest/oxlint/prettier。

设计见 docs/superpowers/specs/2026-07-22-workitem-console-design.md。分支 workitem-console。

## Global Constraints

- 铁律：不改 `src/autodev/domain` 与既有适配器(workspace_git/context_claude/claude_runner/sqlite_repository)；web 是驱动侧适配器，新包 `src/autodev/webapp/`。
- mypy `files=["src"]`：webapp 全量类型标注。
- 有界驱动**绝不进入未实现阶段**(DESIGN 及之后)；DESIGN+ 端口用抛错桩。
- 运行时前端零公网 CDN(字体/marked/DOMPurify 本地打包)。
- Conventional Commits；每任务结束跑门禁。前端门禁：typecheck/oxlint/vitest/build/prettier。Python 门禁：pytest/ruff/mypy/tests-docs。

## 关键接口契约

**领域 API(已存在，直接用)：**
- `WorkItem.create(id: WorkItemId, repo_ref: RepoRef, requirement: Requirement, autonomy_dial: AutonomyDial, now: datetime) -> WorkItem`
- `AutonomyDial.all_human()`；`WorkItem.is_runnable()`(排除 DONE/FAILED/WAIT_HUMAN)；`wi.state`/`wi.history`(list[StateTransition{from_state,to_state,reason,at}])/`wi.artifacts`(dict, key→最新版本)/`wi.type`/`wi.created_at`/`wi.updated_at`。
- `Engine(repo, publisher, ctx: StageContext, clock).advance(wi)`(跑一阶段并落盘)。
- `StageContext(workspace, gatherer, designer, reviewer, executor, verifier, delivery, triage_policy, gate_policy)`。
- `SqliteWorkItemRepository(db_path).save/get/claim_runnable`；`InMemoryWorkItemRepository`(测试)。
- `GitWorkspaceAdapter(GitWorkspaceConfig(repo_map, mirror_dir, workspaces_dir))`(F1)；`ClaudeContextAdapter(runner=lambda p,c: ClaudeCodeRunner().run(p,c), autodev_home)`(F3)。

**前端 DTO 契约(后端 views.py 产出，前端 api/types.ts 对应)：**
```
WorkItemSummary = { id, goal, repo, type: string|null, state: string, created_at, updated_at }
StageView       = { key: string, label: string, status: 'done'|'current'|'pending'|'blocked' }
WorkItemDetail  = WorkItemSummary & {
  stages: StageView[],                      // INTAKE..DONE 线性链, DESIGN+ 为 blocked
  context: { markdown: string, context_file: string } | null,
  failure: { reason: string } | null,       // state==FAILED 时
}
```
state 取值：INTAKE|TRIAGE|CONTEXT|DESIGN|REVIEW|IMPL|ACCEPT|VERIFY|SUBMIT_MR|DONE|WAIT_HUMAN|FAILED。

---

## Task 1: 后端应用服务 + 有界驱动 + 视图投影

**Files:**
- Create: `src/autodev/webapp/__init__.py`
- Create: `src/autodev/webapp/stubs.py` (DESIGN+ 未实现端口桩)
- Create: `src/autodev/webapp/service.py` (WorkItemConsoleService + Executor 协议 + 有界驱动)
- Create: `src/autodev/webapp/views.py` (WorkItem→DTO 投影)
- Test: `tests/webapp/__init__.py`, `tests/webapp/test_service.py`, `tests/webapp/test_views.py`

**Interfaces produced:**
- `class UnavailableStage`：实现 DesignPort/ReviewPort/ExecutionPort/VerificationPort/DeliveryPort 的方法，任一被调 → `raise StageError(FailureKind.FATAL, "stage not yet implemented")`。
- Executor(Protocol): `submit(fn: Callable[[], None]) -> None`；SyncExecutor(测试, 直接调用)。
- `WorkItemConsoleService(repo, engine, executor, clock=..., id_gen=lambda: WorkItemId.new())`：
  - `create(goal: str, repo: str) -> str`(空值 ValueError)
  - `get(id: str) -> WorkItem | None`；`list() -> list[WorkItem]`
  - 私有 `_drive(id)`：`RUN = {S.INTAKE, S.TRIAGE, S.CONTEXT}`；`while (wi:=repo.get(id)) and wi.is_runnable() and wi.state in RUN: engine.advance(wi)`。
- `views.py`: `stage_views(wi) -> list[StageView]`；`view_summary(wi) -> dict`；`view_detail(wi, read_text: Callable[[str], str]) -> dict`(读 context_file 内容；文件缺失 markdown="")。

**Behavior 细节：**
- `create`：`Requirement(goal, repo, (), goal)`；`WorkItem.create(id_gen(), RepoRef(repo), requirement, AutonomyDial.all_human(), clock())`；`repo.save(wi)`；`executor.submit(lambda: self._drive(id))`。
- `stage_views`：线性链 `[INTAKE,TRIAGE,CONTEXT,DESIGN,REVIEW,IMPL,ACCEPT,VERIFY,SUBMIT_MR,DONE]`；已跑过(在 history 的 to_state 或 < 当前序)=done；等于当前 state=current；CONTEXT 之后且平台未实现(DESIGN..SUBMIT_MR,DONE)=blocked；INTAKE..CONTEXT 中未到=pending。label 用中文(需求录入/分诊/上下文/方案/评审/开发/验收/测试/提交MR/完成)。
- `view_detail.context`：若 `"context" in wi.artifacts` → 读 `ContextArtifact.context_file` 内容。`failure`：`state==FAILED` → 取 `wi.history[-1].reason`。

- [ ] **Step 1: 写失败测试 test_service.py**
  - `test_create_drives_to_context_and_rests_at_design`：用 `InMemoryWorkItemRepository` + `Engine(ctx=StageContext(FakeWorkspace(), FakeContext(), *UnavailableStage×5, TriagePolicy(), GatePolicy()))` + SyncExecutor；`svc.create("加限流","demo")`→ `wi=svc.get(id)`；断言 `wi.state == S.DESIGN` 且 `"context" in wi.artifacts`。
  - `test_driver_never_calls_unimplemented_stages`：UnavailableStage 的 designer 被调会抛错→若驱动越界测试会失败；断言最终 state==DESIGN(未 FAILED)。
  - `test_stage_error_converges_to_failed`：注入 gather 抛 `StageError(TRANSIENT,...)` 的假 context（重试耗尽后）→ 断言 state==FAILED。(利用引擎 RetryPolicy；用一个始终抛 TRANSIENT 的假 gatherer，引擎重试上限后 FAILED。)
  - `test_create_rejects_empty`：空 goal/repo → ValueError。
  - `test_list_get`。
- [ ] **Step 2: 跑测试确认失败** `./venv/bin/python -m pytest tests/webapp/test_service.py -q`（ImportError）。
- [ ] **Step 3: 实现 stubs.py + service.py**（按上文接口/行为）。
- [ ] **Step 4: 写 test_views.py**：构造不同 state 的 WorkItem，断言 `stage_views` 的 status 序列（如 state=CONTEXT 时 INTAKE/TRIAGE=done、CONTEXT=current、DESIGN+=blocked）；`view_detail` 在有 context 产物时返回 markdown（注入 read_text 假件）；FAILED 时 failure.reason。
- [ ] **Step 5: 实现 views.py，跑通全部** `./venv/bin/python -m pytest tests/webapp -q`。
- [ ] **Step 6: 门禁 + 提交** ruff/mypy 绿；`feat(webapp): WorkItem 控制台应用服务+有界驱动(止于DESIGN)+视图投影`。

---

## Task 2: 后端 FastAPI 应用 + 组合根 + 前端托管

**Files:**
- Create: `src/autodev/webapp/app.py` (create_app(service, projects) + DTO + SPA 托管 + 占位页)
- Create: `src/autodev/webapp/config.py` (build_app_from_env 组合根)
- Create: `src/autodev/webapp/__main__.py` (uvicorn 入口)
- Create: `src/autodev/webapp/static/index.html` (占位页)
- Modify: `pyproject.toml` (加 `[project.optional-dependencies] web = ["fastapi","uvicorn","httpx"]`)
- Test: `tests/webapp/test_app.py`

**Interfaces:**
- Consumes: Task 1 的 WorkItemConsoleService、`view_summary`/`view_detail`。
- `create_app(service, projects: list[str]) -> FastAPI`：
  - `GET /api/projects` → `projects`
  - `POST /api/workitems` `{goal,repo}` → `{id}`(ValueError→400)
  - `GET /api/workitems` → `[view_summary(wi) for wi in service.list()]`
  - `GET /api/workitems/{id}` → `view_detail(wi, read_text)`；None→404
  - SPA 托管：存在 `frontend/dist/index.html`(或 `AUTODEV_FRONTEND_DIST`)→ `/api` 之后注册 catch-all `GET /{full_path:path}`：dist 内真实文件回文件(防穿越 `dist.resolve() in candidate.parents`)，否则回 index.html；无 dist→ `GET /` 返回 static/index.html 占位。
- `build_app_from_env()`：读 `AUTODEV_HOME`(默认 ~/.autodev)/`AUTODEV_REPO_MAP`(JSON,坏值报 ValueError)/`AUTODEV_MIRROR_DIR`/`AUTODEV_WORKSPACES_DIR`；装配 `SqliteWorkItemRepository(home/"console.sqlite3")`、`InMemoryEventBus`、`StageContext`(GitWorkspaceAdapter+ClaudeContextAdapter+UnavailableStage×5+TriagePolicy+GatePolicy)、`Engine`、ThreadPoolExecutorAdapter、`projects=list(repo_map)`。
- `__main__`：`AUTODEV_WEB_HOST`/`AUTODEV_WEB_PORT`(默认 127.0.0.1:8000)。

- [ ] **Step 1: 写失败 test_app.py**（TestClient + 假 service）：`GET /api/projects`；`POST /api/workitems` 返回 id、空值 400；`GET /api/workitems` 列表形状；`GET /api/workitems/{id}` 详情形状 + 404；SPA 托管(setenv AUTODEV_FRONTEND_DIST 指 tmp dist)：`GET /`、未知路由回退、`/assets/*`、**穿越拒绝**、`/api` 不被 catch-all 遮蔽；无 dist→占位页含"前端尚未构建"。
- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现 app.py + config.py + __main__.py + 占位 static/index.html + pyproject web 组**。
- [ ] **Step 4: 跑通** `./venv/bin/python -m pytest tests/webapp -q`。
- [ ] **Step 5: 组合根 boot 冒烟**：`AUTODEV_HOME=$(mktemp -d) ./venv/bin/python -c "from autodev.webapp.config import build_app_from_env; build_app_from_env()"` 不报错。
- [ ] **Step 6: 门禁 + 提交** `feat(webapp): FastAPI WorkItem 路由 + 组合根 + 前端产物托管`。

---

## Task 3: 前端脚手架

**Files:** `frontend/`(Vite react-ts)：package.json(scripts: dev/build/typecheck/test/lint/format/format:check)、vite.config.ts(base '/' + server.proxy '/api'→127.0.0.1:8000 + vitest jsdom/setup)、src/styles/{tokens.css,global.css}、src/main.tsx(自托管字体 + QueryClientProvider + RouterProvider(import './router'))、src/test/setup.ts、.prettierrc.json、index.html(标题 AutoDev 控制台)。删除脚手架 demo 文件。

设计令牌(冷色仪表盘，与 spec §4 一致)：`--paper #F4F6F9 --surface #FFF --ink #17202E --muted #667085 --line #E4E8EF --signal #D98A1F --done #2F8F5B --error #C0453B`(+ `--on-ink #fff` `--signal-ink #8a5a12` `--error-line #ebc9c4` `--error-surface #fcf3f2`)。字体：Space Grotesk(UI)/Newsreader(简报)/JetBrains Mono(数据)，@fontsource 本地打包。

- [ ] **Step 1**: `npm create vite@latest frontend -- --template react-ts` + `npm install` + 安装 `@tanstack/react-query react-router-dom marked dompurify @fontsource-variable/space-grotesk @fontsource/newsreader @fontsource-variable/jetbrains-mono` + dev `vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom prettier`。
- [ ] **Step 2**: 写 vite.config.ts(proxy+vitest)、tokens.css/global.css、main.tsx、setup.ts、.prettierrc、package.json scripts；删 demo。
- [ ] **Step 3**: `cd frontend && npm run build`(此时 router 未建，仅验证工具链；若因缺 router 失败可先放最小 App，T4 覆盖) → 确认脚手架可编译工具链。
- [ ] **Step 4**: 提交 `chore(frontend): Vite+React+TS 脚手架(令牌/字体/代理/vitest)`。node_modules/dist 不入库。

---

## Task 4: 前端 WorkItem 控制台应用

**Files(frontend/src/):** `api/{types,client}.ts`、`hooks/{useProjects,useWorkItems,useWorkItem,useCreateWorkItem}.ts`、`components/*`(AppHeader/NewWorkItemForm/WorkItemList/WorkItemCard/StatusBadge/LifelinePipeline/BriefDocument/FailurePanel/EmptyState/Notice，各带 .module.css)、`pages/{DashboardPage,WorkItemDetailPage}`、`router.tsx`、`lib/workitem.ts`(状态标签/时间格式)、对应 `*.test.tsx`。

**Interfaces / 行为：** 见 spec §4 与上文 DTO 契约。
- api/client：`getProjects()`、`listWorkItems()`、`getWorkItem(id)`、`createWorkItem(goal,repo)`；非 2xx 抛 `ApiError{status,detail}`。
- hooks：`useWorkItem(id)` 用 refetchInterval：state ∈ {INTAKE,TRIAGE,CONTEXT} → 2000，否则 false(DESIGN/DONE/FAILED/WAIT_HUMAN 停轮询)；`useCreateWorkItem` 成功后失效列表并 `navigate('/workitems/'+id)`。
- 路由：`/`=DashboardPage(新建表单 + WorkItem 列表)，`/workitems/:id`=WorkItemDetailPage(概览 + LifelinePipeline + 各阶段产物：CONTEXT 展开 BriefDocument；FAILED 显示 FailurePanel)。
- LifelinePipeline：按 `stages[].status` 着色(done 绿/current amber 声呐/pending 灰/blocked 置灰+“待建设”)。
- 安全：BriefDocument `marked.parse`→`DOMPurify.sanitize`→innerHTML；其余字符串走文本节点。可达性：标签/焦点/reduced-motion/响应式。

- [ ] **Step 1**: api/types.ts + client.ts + client.test.ts(mock fetch 断言 URL/method/body/ApiError)。
- [ ] **Step 2**: hooks + `useWorkItem` 轮询选择器单测(state→interval)。
- [ ] **Step 3**: 组件(用 frontend-design 保持设计身份) + 关键单测：NewWorkItemForm 校验、LifelinePipeline 阶段着色(blocked 显示待建设)、BriefDocument 消毒(注入 `<script>`/`onerror` 断言剥离)、StatusBadge、WorkItemCard。
- [ ] **Step 4**: pages + router，接线提交→详情→轮询。
- [ ] **Step 5**: 全部前端门禁绿：`npm run typecheck && npm run lint && npm run test && npm run build && (npm run format && npm run format:check)`。
- [ ] **Step 6**: 提交 `feat(frontend): WorkItem 控制台(列表/新建/生命周期/简报, 轮询)`。

---

## Task 5: 集成 · CI · 文档 · 端到端冒烟

**Files:** `.github/workflows/ci.yml`(加 frontend job: setup-node 22 + npm ci + typecheck/lint/test/format:check/build)、`README.md`(控制台前后端运行/构建说明 + 端口进度更新 F1/F3 真实化 + WorkItem 控制台)、`CHANGELOG.md`(条目)。

- [ ] **Step 1**: ci.yml 加 frontend job(working-directory: frontend, cache npm)。
- [ ] **Step 2**: README 控制台章节(生产：先 `cd frontend && npm ci && npm run build`，再 `pip install -e '.[web]'` + 环境变量 + `python -m autodev.webapp`；开发：后端 + `npm run dev`；前端门禁命令；Node≥20 前置)。端口进度：WorkspacePort/ContextPort 标真实；新增 WorkItem 控制台 driving adapter。
- [ ] **Step 3**: CHANGELOG [Unreleased] 加 WorkItem 控制台条目 + web 依赖。
- [ ] **Step 4**: 端到端 boot 冒烟(生产模式)：`cd frontend && npm run build`；起后端；curl `/`(SPA)、`/assets/*`、`/api/projects`、`/workitems/x`(SPA 回退)。
- [ ] **Step 5**: 全套门禁：Python(pytest/ruff/format/mypy/tests-docs) + 前端(5 项)全绿。
- [ ] **Step 6**: 提交 `docs+ci: 控制台运行说明 + 前端 CI 门禁`。

---

## Self-Review 备注

- spec §3 后端(真实 WorkItem/Engine/有界驱动/视图/路由/托管) → T1+T2；§4 前端 → T3+T4；§5 集成 → T2(托管)+T5；§6 测试门禁 → 各任务 + T5；均有覆盖。
- 类型一致：DTO 契约(WorkItemSummary/StageView/WorkItemDetail)在 T1(views)产出、T2(app)透传、T4(types)消费，字段名一致。
- 有界驱动 RUN 集合(INTAKE/TRIAGE/CONTEXT)与"止于 DESIGN"在 T1 测试固化(test_driver_never_calls_unimplemented_stages)。
