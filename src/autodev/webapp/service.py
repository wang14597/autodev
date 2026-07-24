# src/autodev/webapp/service.py
"""WorkItem 控制台应用服务：创建 + 有界自动驱动(止于 DESIGN) + 查询。

有界驱动只允许引擎跑 INTAKE/TRIAGE/CONTEXT 三个已实现阶段；一旦 WorkItem 转移到
DESIGN(或任何未实现阶段) 或进入终态/挂起态，驱动循环立即停止，绝不会调用到
DESIGN 及之后的桩端口(见 stubs.py)。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol, cast

from autodev.application.engine import Engine
from autodev.domain.artifacts import ContextArtifact
from autodev.domain.enums import WorkflowState as S
from autodev.domain.errors import StageError
from autodev.domain.ids import ProjectId, WorkItemId
from autodev.domain.ports import ProjectRepository, WorkItemRepository, WorkspacePort
from autodev.domain.project import Project
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement, WorkspaceHandle
from autodev.domain.work_item import WorkItem
from autodev.webapp.projects import ProjectRegistry

# 有界驱动允许自动跑的阶段集合：仅到 CONTEXT 为止，绝不进入 DESIGN 及之后。
RUN: frozenset[S] = frozenset({S.INTAKE, S.TRIAGE, S.CONTEXT})


def _default_clock() -> datetime:
    return datetime.now(UTC)


class Executor(Protocol):
    def submit(self, fn: Callable[[], None]) -> None: ...


class SyncExecutor:
    """同步执行器：`submit` 立即原地调用，供测试/单进程场景使用。"""

    def submit(self, fn: Callable[[], None]) -> None:
        fn()


def _bounded_drive(repo: WorkItemRepository, engine: Engine, work_item_id: WorkItemId) -> None:
    """有界自动驱动循环：止于 CONTEXT，绝不越界调用 DESIGN 及之后的桩端口。

    抽成自由函数供 WorkItemConsoleService/ProjectConsoleService 共用，避免两个
    服务各自维护一份等价的驱动循环。
    """
    while True:
        try:
            work_item = repo.get(work_item_id)
        except KeyError:
            return
        if not work_item.is_runnable() or work_item.state not in RUN:
            return
        engine.advance(work_item)


class WorkItemConsoleService:
    def __init__(
        self,
        repo: WorkItemRepository,
        engine: Engine,
        executor: Executor,
        clock: Callable[[], datetime] = _default_clock,
        id_gen: Callable[[], WorkItemId] = WorkItemId.new,
        resolve_project: Callable[[str], str] = lambda raw: raw,
    ) -> None:
        self._repo = repo
        self._engine = engine
        self._executor = executor
        self._clock = clock
        self._id_gen = id_gen
        self._resolve_project = resolve_project

    def create(self, goal: str, repo: str) -> str:
        if not goal or not goal.strip():
            raise ValueError("goal must not be empty")
        if not repo or not repo.strip():
            raise ValueError("repo must not be empty")

        # 把"项目"输入解析成 repo_map 里的项目名(本地 git 路径会被自动登记)。
        project = self._resolve_project(repo)
        work_item_id = self._id_gen()
        requirement = Requirement(goal, project, (), goal)
        work_item = WorkItem.create(
            work_item_id,
            RepoRef(project),
            requirement,
            AutonomyDial.all_human(),
            self._clock(),
        )
        self._repo.save(work_item)
        self._executor.submit(lambda: self._drive(work_item_id))
        return work_item_id.value

    def get(self, work_item_id: str) -> WorkItem | None:
        try:
            return self._repo.get(WorkItemId(work_item_id))
        except KeyError:
            return None

    def list(self) -> list[WorkItem]:
        # 从仓库枚举全部工作项(持久化, 进程重启后仍可见), 按创建时间新到旧。
        # 用 timestamp 排序避免 naive/aware datetime 混比(created_at 恒为 UTC aware)。
        items = self._repo.list_all()
        items.sort(key=lambda wi: wi.created_at.timestamp() if wi.created_at else 0.0, reverse=True)
        return items

    def _drive(self, work_item_id: WorkItemId) -> None:
        _bounded_drive(self._repo, self._engine, work_item_id)


class ProjectConsoleService:
    """项目为中心的控制台应用服务：两步创建(建项目→建工作项)+ 共享一次性 setup +

    删除级联。替代/扩展 WorkItemConsoleService(后者暂保留, Task 4 切换 app.py)。
    """

    def __init__(
        self,
        project_repo: ProjectRepository,
        work_repo: WorkItemRepository,
        workspace: WorkspacePort,
        engine: Engine,
        executor: Executor,
        registry: ProjectRegistry,
        clock: Callable[[], datetime] = _default_clock,
        id_gen_project: Callable[[], ProjectId] = ProjectId.new,
        id_gen_work: Callable[[], WorkItemId] = WorkItemId.new,
    ) -> None:
        self._project_repo = project_repo
        self._work_repo = work_repo
        self._workspace = workspace
        self._engine = engine
        self._executor = executor
        self._registry = registry
        self._clock = clock
        self._id_gen_project = id_gen_project
        self._id_gen_work = id_gen_work

    def create_project(self, name: str, repo_input: str, branch: str = "") -> str:
        if not name or not name.strip():
            raise ValueError("name must not be empty")
        if not repo_input or not repo_input.strip():
            raise ValueError("repo_input must not be empty")
        name = name.strip()
        # 仅以已持久化的 Project 判重名: pre-seeded repo_map 条目 / 上次失败的残留
        # 不应把项目名永久占住(否则改不了、也不显示在项目列表)。
        if self._project_repo.get_by_name(name) is not None:
            raise ValueError("项目名已存在")

        repo_source = self._registry.register(name, repo_input)
        try:
            # 留空(branch or None → None)时交给 F1 解析仓库默认分支。
            default_branch = self._workspace.prepare(RepoRef(name), branch or None)
        except StageError as e:
            # 仓库不可达/路径错误/未连 VPN 等: 回滚登记(别占住项目名), 以可翻译错误(→400)反馈。
            self._registry.unregister(name)
            raise ValueError(f"项目仓库准备失败: {e.message}") from e
        now = self._clock()
        project = Project.create(self._id_gen_project(), name, repo_source, default_branch, now)
        project.mark_prepared(default_branch, now)
        self._project_repo.save(project)
        return project.id.value

    def list_projects(self) -> list[tuple[Project, int]]:
        projects = self._project_repo.list_all()
        work_items = self._work_repo.list_all()
        counts: dict[str, int] = {}
        for wi in work_items:
            if wi.project_id is not None:
                counts[wi.project_id.value] = counts.get(wi.project_id.value, 0) + 1
        results = [(p, counts.get(p.id.value, 0)) for p in projects]
        results.sort(
            key=lambda pair: pair[0].created_at.timestamp() if pair[0].created_at else 0.0,
            reverse=True,
        )
        return results

    def get_project(self, project_id: str) -> Project | None:
        try:
            return self._project_repo.get(ProjectId(project_id))
        except KeyError:
            return None

    def refresh_project(self, project_id: str) -> str:
        try:
            project = self._project_repo.get(ProjectId(project_id))
        except KeyError as e:
            raise LookupError(project_id) from e
        # 重新 fetch, 但保持跟踪当前 project.branch(不回退到仓库默认分支)。
        branch = self._workspace.prepare(RepoRef(project.name), project.branch or None)
        project.mark_prepared(branch, self._clock())
        self._project_repo.save(project)
        return branch

    def list_branches(self, project_id: str) -> list[str]:
        try:
            project = self._project_repo.get(ProjectId(project_id))
        except KeyError as e:
            raise LookupError(project_id) from e
        return self._workspace.list_branches(RepoRef(project.name))

    def set_project_branch(self, project_id: str, branch: str) -> str:
        if not branch or not branch.strip():
            raise ValueError("branch must not be empty")
        try:
            project = self._project_repo.get(ProjectId(project_id))
        except KeyError as e:
            raise LookupError(project_id) from e

        # 切换前先刷新 origin/* 引用(best-effort): 保证候选分支列表是最新的,
        # 网络不可达/离线时不阻断——退回上次 fetch 到的已知分支集合。
        try:
            self._workspace.prepare(RepoRef(project.name), None)
        except StageError:
            pass

        branches = self._workspace.list_branches(RepoRef(project.name))
        if branch not in branches:
            raise ValueError(f"分支不存在: {branch}")

        project.mark_prepared(branch, self._clock())
        self._project_repo.save(project)
        return branch

    def delete_project(self, project_id: str) -> bool:
        try:
            project = self._project_repo.get(ProjectId(project_id))
        except KeyError:
            return False

        pid = project.id
        for wi in self._work_repo.list_all():
            if wi.project_id != pid:
                continue
            if "context" in wi.artifacts:
                artifact = cast(ContextArtifact, wi.artifacts["context"])
                try:
                    self._workspace.cleanup(
                        WorkspaceHandle(artifact.workspace_location, artifact.workspace_label)
                    )
                except Exception:  # noqa: BLE001 best-effort：清理失败不阻断删除
                    pass
            self._work_repo.delete(wi.id)

        self._registry.unregister(project.name)
        self._project_repo.delete(pid)
        return True

    def create_workitem(self, project_id: str, goal: str) -> str:
        if not goal or not goal.strip():
            raise ValueError("goal must not be empty")
        try:
            project = self._project_repo.get(ProjectId(project_id))
        except KeyError as e:
            raise LookupError(project_id) from e

        # 建工作项时自动 fetch: 保证 worktree 基于默认分支的最新 origin/<branch>。
        # best-effort——拉取失败(网络/离线)不阻断创建, 退回上次 fetch 到的 origin。
        try:
            self._workspace.prepare(RepoRef(project.name), project.branch or None)
        except StageError:
            pass

        work_item_id = self._id_gen_work()
        requirement = Requirement(goal, project.name, (), goal)
        work_item = WorkItem.create(
            work_item_id,
            RepoRef(project.name),
            requirement,
            AutonomyDial.all_human(),
            self._clock(),
            project_id=project.id,
            base_branch=project.branch,
        )
        self._work_repo.save(work_item)
        self._executor.submit(lambda: _bounded_drive(self._work_repo, self._engine, work_item_id))
        return work_item_id.value

    def list_workitems(self, project_id: str) -> list[WorkItem]:
        pid = ProjectId(project_id)
        items = [wi for wi in self._work_repo.list_all() if wi.project_id == pid]
        items.sort(key=lambda wi: wi.created_at.timestamp() if wi.created_at else 0.0, reverse=True)
        return items

    def get_workitem(self, work_item_id: str) -> WorkItem | None:
        try:
            return self._work_repo.get(WorkItemId(work_item_id))
        except KeyError:
            return None
