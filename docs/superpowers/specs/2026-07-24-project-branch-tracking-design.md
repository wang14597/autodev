# Project 跟踪分支 + 刷新 fetch 设计（增量）

> 日期：2026-07-24
> 状态：设计已定（关键决策已确认），承接 2026-07-24-project-aggregate。
> 背景：真实使用澄清——**Project 关联的是"仓库 + 它跟踪的分支本身"**；点「刷新」除更新信息外**必须执行 `git fetch`** 把远端更新同步到本地；worktree 仍是每个 WorkItem 才分配。当前实现：Project 只"探测"默认分支、刷新对本地仓不 fetch、worktree 基于可能陈旧的本地 HEAD——需纠正。

## 1. 已确认决策

- 项目跟踪分支**创建时显式指定**（留空 = 仓库默认分支）。
- 刷新 = 重新 `prepare` = **重新 `git fetch`**（远程仓 fetch 镜像；本地仓 fetch 其 `origin`，best-effort）+ 更新信息。
- worktree **基于跟踪分支的最新**：`origin/<branch>`（fetch 后），本地仓无 origin 时退回本地 `<branch>`。
- worktree 每个 WorkItem 一个（不变）。

## 2. 变更

### 2.1 领域
- `Project` 增字段 `branch: str`（跟踪分支；create 时传入，可为默认解析后的值）。`create(id, name, repo_source, branch, now)`；`mark_prepared(branch, now)`（把解析后的分支写回）。
- `WorkItem` 增 `base_branch: str | None = None`（建工作项时从 `Project.branch` 冗余下来，作为 worktree 基点）；`create(..., base_branch=None)`。
- `WorkspacePort.prepare(repo: RepoRef, branch: str | None = None) -> str`：fetch + 解析跟踪分支（branch 给定则校验并用之；None → 默认分支），返回解析后的分支名。
- `WorkspacePort.provision(work_item_id, repo, mode, branch, base_branch: str | None = None) -> WorkspaceHandle`：新增 base_branch，指定 worktree 基点分支。

### 2.2 F1（GitWorkspaceAdapter）
- `prepare(repo, branch)`：
  - 本地 worktree 仓：`git -C <src> fetch --all --prune`（best-effort，try/except 忽略无 origin/离线）；解析分支：branch 给定→用之；否则 `git -C <src> symbolic-ref --short HEAD`（当前分支）。返回分支名。
  - 远程仓：`_ensure_mirror(FETCH)`（建/刷新镜像 = fetch）；解析分支：branch 给定→用之；否则 `_base_ref`（origin/HEAD 去前缀）。返回分支名。
- `provision(..., base_branch)`：计算 worktree 基点 `base`：
  - 本地 worktree 仓：若 `git -C <src> rev-parse --verify origin/<base_branch>` 成功 → base=`origin/<base_branch>`（fetch 后最新）；否则 base=`<base_branch>`（本地分支）；base_branch 为空→退回 `_local_base`。`git -C <src> worktree add -b <branch> <ws> <base>`。
  - 远程仓（镜像）：base=`origin/<base_branch>` 若存在，否则 `_base_ref`。worktree add off 镜像。
- `repo_status` 短路不变。

### 2.3 应用/handler
- `handle_context`：`ctx.workspace.provision(id, repo_ref, mode, branch_for(wi), base_branch=wi.base_branch)`。

### 2.4 服务/API/前端
- `create_project(name, repo_input, branch)`：registry.register→`prepare(RepoRef(name), branch)` 得解析分支→`Project.create(..., branch=解析分支)`+mark_prepared→save。prepare 失败回滚（沿用现逻辑）。
- `refresh_project(id)`：`prepare(RepoRef(name), project.branch)`（重新 fetch + 保持跟踪分支）→ mark_prepared → save → 返回分支。
- `create_workitem(project_id, goal)`：`WorkItem.create(..., base_branch=project.branch)`。
- API：`POST /api/projects {name, repo, branch?}`；`view_project` 增 `branch` 字段（DTO：Project 增 `branch: string`）。
- 前端：NewProjectForm 加"分支(可选)"输入；Project 类型加 `branch`；项目详情展示"跟踪分支"（替代/并列现"默认分支"）。

## 3. 测试
- F1：prepare 本地 fetch(best-effort，注入 run 断言执行了 fetch；无 origin 不报错)、prepare 指定分支/默认分支、provision base_branch → 基于 `origin/<branch>`（预置远程分支后新提交，worktree 含新提交）、本地无 origin 退回本地分支。
- 服务：create_project 带 branch 透传 prepare + 存 Project.branch；create_workitem base_branch=project.branch；refresh 重新 fetch。
- 端点：POST projects 带 branch；view_project 含 branch。
- 前端：NewProjectForm 分支字段；Project 类型/详情展示 branch。
- 全套门禁绿；CHANGELOG/README/diagrams 同步（Project.branch）。

## 4. 非目标
- 不做分支切换后自动重建已存在 worktree（工作项 worktree 建时定基点）。
- 不做分支列表下拉（先自由输入；未来可枚举远程分支）。
- 不改真实分诊；不改删除语义。
