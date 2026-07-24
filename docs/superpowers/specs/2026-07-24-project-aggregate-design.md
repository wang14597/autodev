# Project 一等概念（领域聚合 + 控制台）设计

> 日期：2026-07-24
> 状态：设计中（brainstorming 关键决策已定），待 review 后转实现计划
> 背景：真实使用发现——大型项目下会有很多次任务(WorkItem)。需要引入一等 **Project** 概念：同一项目下共享一次性 setup（分支是否存在、是否拉远程等不重复），且所有工作项有归属，便于区分与隔离。架构基准见 docs/architecture/2026-07-15-strategic-direction-and-domain-model.md。

## 1. 已确认决策

1. **Project 建模为领域一等聚合**（domain 层，非仅 webapp）。
2. **两步创建**：先建 Project（登记仓库 + 一次性 setup），再在项目下建 WorkItem（从已有项目选）。
3. **项目为中心导航**：首页项目列表 → 项目详情(其下工作项 + 在此新建) → 工作项详情。
4. 推荐默认：共享 setup 在建项目时做一次 + 项目页手动"刷新"；工作项创建不再自动 fetch。老数据 `project_id` 缺失按"未归类"优雅显示，不写迁移脚本。

## 2. 领域层

### 2.1 Project 聚合（新增 `src/autodev/domain/project.py`）
- `ProjectId`（`src/autodev/domain/ids.py` 增，仿 WorkItemId：`.value` hex、`.new()`）。
- `Project`（dataclass 聚合根）：
  - `id: ProjectId`
  - `name: str`（人类可读，唯一性由应用层保证）
  - `repo_source: str`（仓库来源：远程 URL / 本地 `worktree:` 标记 / 裸路径——沿用现 repo_map 值语义）
  - `default_branch: str | None`（prepare 时探测缓存）
  - `autonomy_dial: AutonomyDial`（project 级默认，默认 all_human）
  - `created_at / updated_at: datetime | None`
  - 方法：`create(id, name, repo_source, now)`；`mark_prepared(default_branch, now)`（幂等更新缓存）。
- 不承载 git 内部就绪状态（镜像是否 fetch 等）——那是 F1 基础设施缓存，按 repo 名共享。

### 2.2 端口（`src/autodev/domain/ports.py`）
- 新增 `ProjectRepository`(Protocol)：`save/get/get_by_name/list_all`。
- `WorkspacePort` 增 `prepare(repo: RepoRef) -> str`：一次性把仓库准备好并返回默认分支名（远程：建/刷新镜像 + set-head；本地 worktree：校验 + 读 HEAD 分支）。幂等。

### 2.3 WorkItem 变更（`src/autodev/domain/work_item.py`）
- 增字段 `project_id: ProjectId | None = None`（归属；旧数据为 None=未归类）。
- `repo_ref` 保留：创建工作项时 `repo_ref.name = Project.name`（handlers/引擎/AutonomyDial 以 repo 名为维度，几乎不改）。
- `WorkItem.create` 增可选 `project_id` 参数。

**命名一致性(重要)**：`Project.name` 同时充当 **repo_map 的 key** 与 **`repo_ref.name`**；`repo_map[Project.name] = Project.repo_source`。即项目名是仓库的逻辑标识，来源(URL/worktree 标记)是其值。create_project 时把 `(name → 解析后的 repo_source)` 写入共享 repo_map（登记表）。

## 3. 共享一次性 setup 的语义

- **建项目**：应用层调用 `WorkspacePort.prepare(RepoRef(projectName))` → 远程仓建镜像 + fetch + set-head 得默认分支；本地 worktree 仓校验 + 读默认分支。结果 `default_branch` 存入 Project（`mark_prepared`）。
- **同项目下建工作项 → 驱动 CONTEXT**：provision 复用已就绪镜像/本地仓：
  - 远程：镜像已存在 → provision 用 **REUSE**（不再 fetch）。（TriagePolicy 见下。）
  - 本地 worktree：直接在源仓开 worktree（本就秒级、无 fetch）。
- **TRIAGE 不再每次 ls-remote**：`repo_status` 短路优化——当镜像已存在(或本地 worktree 仓存在)即 `exists_local=True` 且**跳过 `ls-remote`**(不再探测远程)→ TriagePolicy 选 REUSE。（本地 worktree 已实现该短路；本 feature 对"镜像已存在"也短路。）
- **刷新**：项目页"刷新"按钮 → 再次 `prepare`（远程重新 fetch，更新 default_branch）。

## 4. 应用层 / 服务

`ProjectConsoleService`（webapp，替代/扩展现 WorkItemConsoleService）：
- `create_project(name, repo_input) -> project_id`：校验非空/重名；用 ProjectRegistry 解析 repo_input（本地路径→worktree 标记登记）；`WorkspacePort.prepare` 一次性 setup；`Project.create` + `mark_prepared`；持久化。
- `list_projects() -> [Project + workitem 计数]`。
- `get_project(id) -> Project`。
- `refresh_project(id)`：再 prepare，更新 default_branch。
- `create_workitem(project_id, goal) -> id`：查 Project → `WorkItem.create(project_id=..., repo_ref=项目名, ...)` → 后台有界驱动（不变，止于 DESIGN）。
- `list_workitems(project_id) -> [...]`；`get_workitem(id)`（不变）。
- 驱动/引擎/handlers：不变（仍按 repo_ref 走）。

## 5. 持久化

- `SqliteProjectRepository`（新）：projects 表（id/name/data JSON），save/get/get_by_name/list_all；WAL+busy_timeout。
- `InMemoryProjectRepository`（测试）。
- WorkItem 序列化增 `project_id`（`_to_dict/_from_dict` 容忍缺失→None）。
- SQLite work_items 查询按 project_id 过滤：`list_workitems(project_id)` 在 service 层过滤 `repo.list_all()`（或加索引查询，先过滤即可）。

## 6. HTTP API（`src/autodev/webapp/app.py`）

- `GET /api/projects` → `[{id,name,repo_source,default_branch,workitem_count,created_at}]`
- `POST /api/projects` `{name, repo}` → `{id}`（空/重名 400）
- `GET /api/projects/{id}` → 项目详情 `{...project, workitems:[summary...]}`；未知 404
- `POST /api/projects/{id}/refresh` → `{default_branch}`
- `POST /api/projects/{id}/workitems` `{goal}` → `{id}`（空 400；项目不存在 404）
- `GET /api/workitems/{id}` → 工作项详情（不变）
- SPA 托管不变。

## 7. 前端（`frontend/`，项目为中心重构导航）

- 路由：`/`=ProjectsPage(项目列表+新建项目)、`/projects/:pid`=ProjectDetailPage(项目概览+其工作项列表+在此新建工作项+刷新)、`/projects/:pid/workitems/:id`=WorkItemDetailPage(复用现有生命周期/简报)。
- 组件复用现有 StatusBadge/LifelinePipeline/BriefDocument 等；新增 ProjectList/ProjectCard/NewProjectForm/ProjectHeader。
- hooks：useProjects/useProject/useCreateProject/useRefreshProject/useCreateWorkItem(project 维度)/useWorkItem(不变)。
- 设计身份沿用；文案围绕"项目/工作项"。

## 8. 测试与门禁

- 领域：Project 聚合(create/mark_prepared)、ProjectRepository(sqlite/内存 save/get/get_by_name/list_all)。
- F1：`prepare` 远程(建镜像+默认分支)、本地 worktree(读默认分支)、幂等；REUSE 复用不 fetch。
- 服务：create_project(prepare 调用+持久化+重名拒绝)、create_workitem(归属 project_id、repo_ref 冗余正确)、list_workitems 按项目过滤、refresh。
- 端点：projects CRUD 形状/状态码/404/400、项目下建工作项。
- 前端:api/hooks/组件/页面(项目列表、项目详情、在项目下建工作项、轮询)。
- Python + 前端全套门禁绿;CHANGELOG/README/diagrams 更新(doc-impact)。

## 9. 范围边界与非目标

- 不做真实分诊(TaskType 仍恒 SMALL_CHANGE，可能未来丢弃)。
- 不做鉴权/多租户/项目级权限(后续)。
- 不做 project 删除的级联清理策略深挖(先支持基本删除或暂不删)。
- 不改 DESIGN 及之后阶段(仍置灰待建设)。
- 老数据不迁移(project_id 缺失=未归类，优雅显示)。

## 10. 验收标准

- 可建项目(一次性 setup 探测默认分支)、在项目下建多个工作项并见其归属;项目页列出其工作项。
- 同项目下第 2+ 个工作项**不再重复 ls-remote/fetch**(远程 REUSE / 本地 worktree 直挂)。
- 领域含 Project 聚合 + ProjectRepository;WorkItem 带 project_id;引擎/handlers 不回归。
- 前后端门禁全绿;文档一致(第1/2层 + mermaid)。
