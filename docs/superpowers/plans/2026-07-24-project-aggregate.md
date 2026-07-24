# Project 一等概念 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 引入一等 Project 领域聚合：两步创建(先建项目再在其下建工作项)、项目为中心控制台、同项目共享一次性 setup(不重复 ls-remote/fetch)、支持删除项目(级联)。

**Architecture:** Project 为 domain 聚合 + ProjectRepository；WorkItem 增 project_id(repo_ref 从项目名冗余)；WorkspacePort.prepare 做一次性 setup + repo_status 短路；webapp 换成 ProjectConsoleService + 项目路由；前端项目为中心导航。

**Tech Stack:** Python/FastAPI/pytest；Vite/React/TS/TanStack Query/React Router/Vitest。

设计见 docs/superpowers/specs/2026-07-24-project-aggregate-design.md。分支 project-aggregate。

## Global Constraints

- 铁律：`src/autodev/domain` 仅标准库，不 import adapters/application。新领域概念放 domain；实现放 adapters；驱动侧(FastAPI/前端)放 webapp/frontend。
- mypy `files=["src"]`：**给 Protocol 端口加方法时，src 内所有被赋值到该端口类型的实现必须同时实现该方法**(否则 mypy 红)。GitWorkspaceAdapter→WorkspacePort、Sqlite/InMemoryWorkItemRepository→WorkItemRepository 在 config.py 里被按端口类型使用。
- 命名一致：`Project.name` == repo_map key == `repo_ref.name`；`repo_map[name] = repo_source`。
- 有界驱动不变(止于 DESIGN)；不做真实分诊。
- Conventional Commits；每任务跑门禁。前端门禁：typecheck/oxlint/vitest/build/prettier。Python：pytest/ruff/mypy/tests-docs。

## 关键接口契约

**领域(新增/改)：**
- ProjectId(ids.py)：`@dataclass(frozen=True) value: str`；`@classmethod new() -> ProjectId`(uuid hex)。
- Project(project.py, `@dataclass`)：`id: ProjectId; name: str; repo_source: str; default_branch: str|None=None; autonomy_dial: AutonomyDial=all_human; created_at/updated_at: datetime|None=None`。
  - `@classmethod create(id, name, repo_source, now) -> Project`
  - `mark_prepared(default_branch: str, now: datetime) -> None`(设 default_branch + updated_at)
- ProjectRepository(Protocol)：`save(p)/get(id)->Project/get_by_name(name)->Project|None/list_all()->list[Project]/delete(id)->None`。get 未找到 raise KeyError。
- `WorkItemRepository` 增 `delete(work_item_id: WorkItemId) -> None`。
- `WorkspacePort` 增 `prepare(repo: RepoRef) -> str`(返回默认分支名, 幂等)。
- `WorkItem`：增 `project_id: ProjectId | None = None`；`create(..., project_id=None)`。

**DTO(前端契约)：**
```
Project        = { id, name, repo_source, default_branch: string|null, workitem_count: number, created_at: string|null }
ProjectDetail  = Project & { workitems: WorkItemSummary[] }
WorkItemSummary/WorkItemDetail/StageView 同前(不变)
```

---

## Task 1: 领域 Project 聚合 + ProjectRepository + WorkItem.project_id + 序列化

**Files:**
- Modify: `src/autodev/domain/ids.py`(加 ProjectId)
- Create: `src/autodev/domain/project.py`(Project)
- Modify: `src/autodev/domain/ports.py`(加 ProjectRepository)
- Modify: `src/autodev/domain/work_item.py`(加 project_id 字段 + create 参数)
- Create: `src/autodev/adapters/project_repository.py`(SqliteProjectRepository + InMemoryProjectRepository) —— 或分别加到现有 sqlite_repository.py/memory_repository.py；新文件更清晰。
- Modify: `src/autodev/adapters/sqlite_repository.py`(WorkItem `_to_dict`/`_from_dict` 加 project_id)
- Test: `tests/domain/test_project.py`, `tests/adapters/test_project_repository.py`, 扩 `tests/adapters/test_sqlite_repository.py`(project_id 往返)

**Interfaces produced:** ProjectId, Project, ProjectRepository(见契约); SqliteProjectRepository(db_path)/InMemoryProjectRepository()。

- [ ] Step 1: 写 `tests/domain/test_project.py`：`Project.create` 设字段/时间戳；`mark_prepared` 设 default_branch + 更新 updated_at；`ProjectId.new()` 唯一。
- [ ] Step 2: 跑失败。
- [ ] Step 3: 实现 ids.ProjectId + project.Project。
- [ ] Step 4: 写 `tests/adapters/test_project_repository.py`(sqlite + 内存)：save/get 往返、get_by_name(命中/None)、list_all、delete、get 未找到 raise KeyError。用 tmp_path sqlite。
- [ ] Step 5: 实现 ports.ProjectRepository + SqliteProjectRepository(projects 表 id/name/data JSON, WAL+busy_timeout) + InMemoryProjectRepository。
- [ ] Step 6: WorkItem 加 `project_id: ProjectId | None = None` + `create(..., project_id: ProjectId | None = None)`；`_to_dict` 加 `"project_id": wi.project_id.value if wi.project_id else None`；`_from_dict` 读 `ProjectId(d["project_id"]) if d.get("project_id") else None`。扩 test_sqlite_repository：带 project_id 的 WorkItem 往返、旧数据(无 project_id 键)→ None。
- [ ] Step 7: 门禁(pytest/ruff/mypy/tests-docs)+ 提交 `feat(domain): Project 聚合 + ProjectRepository + WorkItem.project_id`。

## Task 2: WorkspacePort.prepare + repo_status 短路 + WorkItemRepository.delete

**Files:**
- Modify: `src/autodev/domain/ports.py`(WorkspacePort 加 prepare；WorkItemRepository 加 delete)
- Modify: `src/autodev/adapters/workspace_git.py`(实现 prepare + repo_status 短路)
- Modify: `src/autodev/adapters/sqlite_repository.py` + `memory_repository.py`(delete)
- Modify: `tests/fakes.py`(FakeWorkspace 加 prepare)
- Test: 扩 `tests/adapters/test_workspace_git.py`、`test_sqlite_repository.py`

**Interfaces produced:** `WorkspacePort.prepare(repo)->str`；`WorkItemRepository.delete(id)`。

- [ ] Step 1: 写测试：
  - `test_prepare_remote_builds_mirror_and_returns_default_branch`：用 `_make_remote` 作 repo_map 值(远程)；`prepare(RepoRef)` → 返回 "main"，镜像已建。
  - `test_prepare_local_worktree_returns_default_branch`：`worktree:<src>` → 返回源仓当前分支(main)，不建镜像。
  - `test_prepare_idempotent`：连调两次不报错、结果一致。
  - `test_repo_status_skips_ls_remote_when_mirror_exists`：mirror 已在 → exists_local=True 且**不调 ls-remote**(注入 run 断言未出现 ls-remote，或用不可达 url + mirror 预置断言仍 exists_local=True 不抛)。
  - `test_delete_removes_work_item`(sqlite + 内存)。
- [ ] Step 2: 跑失败。
- [ ] Step 3: workspace_git：
  - `prepare(repo)`: `src = self._local_source(name)`; if src → return `self._local_base(src)`; else → `self._ensure_mirror(mirror, name, FETCH)` + return `self._base_ref(mirror)`(即 `symbolic-ref --short refs/remotes/origin/HEAD`)。
  - `repo_status` 短路：`mirror = self._mirror_path(name); if self._local_source(name) or mirror.exists(): return RepoStatus(exists_local=True, exists_remote=False)`(跳过 ls-remote)。(保留未就绪时的 ls-remote 探测。)
- [ ] Step 4: sqlite/memory delete；FakeWorkspace.prepare(返回 "main" 或 handle.label 逻辑, 供测试)。
- [ ] Step 5: 门禁 + 提交 `feat(workspace): prepare 一次性setup + repo_status 短路 + repo.delete`。

## Task 3: ProjectConsoleService(应用服务)

**Files:**
- Modify: `src/autodev/webapp/service.py`(新增 ProjectConsoleService；保留有界驱动/Executor/RUN)
- Modify: `src/autodev/webapp/projects.py`(ProjectRegistry 增 `register(name, repo_input)->repo_source` 供两步显式登记 + `unregister(name)` 供删除)
- Modify: `src/autodev/webapp/views.py`(加 `view_project(project, workitem_count)`, `view_project_detail(project, workitems)`)
- Test: `tests/webapp/test_project_service.py`, 扩 `test_views.py`

**Interfaces produced:** `ProjectConsoleService(project_repo, work_repo, workspace, engine, executor, registry, clock, id_gen)` with:
- `create_project(name, repo_input)->str`(空/重名 ValueError；registry.register 解析并写 repo_map；`workspace.prepare(RepoRef(name))` 得默认分支；Project.create+mark_prepared；project_repo.save)
- `list_projects()->list[tuple[Project,int]]`(计数=该项目 workitem 数)
- `get_project(id)->Project|None`
- `refresh_project(id)->str`(workspace.prepare 再来一次 + mark_prepared + save；返回 default_branch)
- `delete_project(id)->bool`(遍历其 workitems：有 context artifact→workspace.cleanup(handle from artifact)；work_repo.delete；registry.unregister(name)；project_repo.delete)
- `create_workitem(project_id, goal)->str`(项目不存在→LookupError；WorkItem.create(project_id, RepoRef(project.name), Requirement(goal, project.name,(),goal))→save→executor 驱动)
- `list_workitems(project_id)->list[WorkItem]`(work_repo.list_all() 过滤 project_id)
- `get_workitem(id)->WorkItem|None`

- [ ] Step 1: 写 `test_project_service.py`(注入 InMemoryProjectRepository + InMemoryWorkItemRepository + FakeWorkspace + Engine(fakes) + SyncExecutor + ProjectRegistry(tmp))：
  - create_project→prepare 被调、Project 持久化含 default_branch、repo_map 有条目；重名/空→ValueError。
  - create_workitem→驱动到 DESIGN、project_id 正确、repo_ref.name==project.name。
  - list_workitems 只返回该项目的。
  - refresh_project 更新 default_branch。
  - delete_project→工作项被删、cleanup 被调(FakeWorkspace 记录)、registry 条目移除、project 消失；含"删有 context 产物的工作项会 cleanup"。
- [ ] Step 2-4: 实现 registry.register/unregister、views、ProjectConsoleService，跑通。
- [ ] Step 5: 门禁 + 提交 `feat(webapp): ProjectConsoleService(两步创建/共享setup/删除级联)`。

## Task 4: HTTP API + 组合根

**Files:** Modify `src/autodev/webapp/app.py`(项目路由 + DTO), `config.py`(装配 SqliteProjectRepository + ProjectConsoleService)。Test: 重写 `tests/webapp/test_app.py`。

**Routes(见 spec §6):** GET/POST `/api/projects`；GET `/api/projects/{id}`；POST `/api/projects/{id}/refresh`；DELETE `/api/projects/{id}`；POST `/api/projects/{id}/workitems`；GET `/api/workitems/{id}`。SPA 托管不变。ConsoleService Protocol 更新为 ProjectConsoleService 形状。ValueError→400、LookupError/None→404。

- [ ] Step 1: 写 test_app.py(TestClient + FakeProjectConsoleService 或注入内存实现)：projects 列表/创建/详情/刷新/删除/项目下建工作项 的形状/状态码/404/400；SPA 托管/回退/穿越/占位(沿用现有)。
- [ ] Step 2-4: 实现 app 路由 + config 装配(SqliteProjectRepository(home/"projects.sqlite3") 或复用 console.sqlite3 另表；ProjectConsoleService 注入 registry=load_registry(...))，跑通；组合根 boot 冒烟。
- [ ] Step 5: 门禁 + 提交 `feat(webapp): 项目 CRUD 路由 + 组合根装配`。

## Task 5: 前端(项目为中心导航重构)

**Files(frontend/src/):** api/types+client(projects), hooks(useProjects/useProject/useCreateProject/useRefreshProject/useDeleteProject/useCreateWorkItem/useWorkItem), components(ProjectList/ProjectCard/NewProjectForm/ProjectHeader + 复用 StatusBadge/LifelinePipeline/BriefDocument/FailurePanel/Notice/EmptyStage), pages(ProjectsPage `/`, ProjectDetailPage `/projects/:pid`, WorkItemDetailPage `/projects/:pid/workitems/:id`), router.tsx。设计令牌/字体不变。

**API 契约见上 DTO + spec §6。** 行为：ProjectsPage 列项目+新建(name+repo/path);ProjectDetailPage 概览(default_branch/仓库源)+工作项列表(轮询, 有运行中每3s)+在此新建工作项(仅 goal)+刷新+删除(二次确认→删成功导航回 `/`);WorkItemDetailPage 复用现有生命周期/简报/轮询。相对 `/api`;marked→DOMPurify 消毒;可达性/reduced-motion/响应式。

- [ ] Step 1: api/types+client + client.test。
- [ ] Step 2: hooks(含 useProjects 列表轮询选择器复用、useWorkItem 轮询不变)+ 选择器单测。
- [ ] Step 3: 组件(NewProjectForm 校验、ProjectCard、ProjectHeader 删除确认)+ 关键单测。
- [ ] Step 4: pages + router 接线(两步流:建项目→进详情→建工作项→工作项详情)。
- [ ] Step 5: 前端门禁全绿(typecheck/lint/test/build/format)。
- [ ] Step 6: 提交 `feat(frontend): 项目为中心控制台(项目列表/详情/删除/项目下建工作项)`。

## Task 6: 集成 · 文档 · CI · e2e 冒烟

**Files:** CHANGELOG.md, README.md(控制台章节:两步/项目为中心/删除), docs/architecture/diagrams.md(数据模型图加 Project→WorkItem 归属;端口图加 ProjectRepository)。

- [ ] Step 1: diagrams.md 数据模型加 Project(1..* WorkItem) + ProjectRepository 端口;prose 同步。
- [ ] Step 2: README 控制台章节改为"两步:建项目(登记仓库/本地路径, 一次性 setup)→ 项目下建工作项;可刷新/删除;项目为中心导航"。
- [ ] Step 3: CHANGELOG [Unreleased] 加 Project 一等概念条目。
- [ ] Step 4: e2e boot 冒烟(生产):build 前端;起后端;`POST /api/projects`(用本地 git 仓)→`POST /api/projects/{id}/workitems`→轮询→`GET /api/projects/{id}` 见工作项;`DELETE`。
- [ ] Step 5: 全套门禁(Python 5 项 + 前端 5 项 + doc-impact origin/main..HEAD)。
- [ ] Step 6: 提交 `docs+ci: Project 概念文档/图/CHANGELOG 同步`。

## Self-Review 备注

- spec §2 领域→T1+T2；§3 共享setup→T2(prepare/短路)+T3(create_project 调 prepare);§4 服务→T3;§5 持久化→T1(project repo/序列化);§6 API→T4;§7 前端→T5;§8/§10→各任务+T6;删除→T2(repo.delete)+T3(delete_project 级联)+T4(DELETE 路由)+T5(删除按钮)。
- mypy 绿约束:T1 只加新端口(ProjectRepository,新实现齐)+ 加 WorkItem 字段(additive);T2 给 WorkspacePort/WorkItemRepository 加方法**同时**补 GitWorkspaceAdapter/sqlite/memory 实现 → 两任务各自 mypy 绿。
- 命名一致:Project.name==repo_map key==repo_ref.name 贯穿 T3(create_project register / create_workitem RepoRef(project.name))。
- DTO 字段(Project/ProjectDetail)在 T3(views)产、T4(app)透传、T5(types)消费, 名称一致。
