# src/autodev/webapp/service.py
"""WorkItem 控制台应用服务：创建 + 驱动(自动/单步) + 查询。

驱动边界(`implemented_stages`, 生产默认 `IMPLEMENTED_STAGES`)与停因判定的单一真源见
`drive.py`；本模块只负责按场景选用 `auto_drive`(自动挡/建工作项收集段)或
`step`(手动挡人工单步推进)，绝不会调用到未实现阶段之后的桩端口(见 stubs.py)。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol, cast

from autodev.application.engine import Engine
from autodev.application.entrypoints import decide_work_item
from autodev.domain.artifacts import ContextArtifact
from autodev.domain.enums import WorkflowState as S
from autodev.domain.errors import StageError
from autodev.domain.ids import ProjectId, WorkItemId
from autodev.domain.ports import ProjectRepository, WorkItemRepository, WorkspacePort
from autodev.domain.project import Project
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement, WorkspaceHandle
from autodev.domain.work_item import WorkItem
from autodev.webapp.drive import IMPLEMENTED_STAGES, DriveStop, auto_drive, ensure_advanceable, step
from autodev.webapp.projects import ProjectRegistry

_Driver = Callable[[WorkItemRepository, Engine, WorkItemId, frozenset[S]], DriveStop | None]


def _default_clock() -> datetime:
    return datetime.now(UTC)


class Executor(Protocol):
    def submit(self, fn: Callable[[], None]) -> None: ...


class SyncExecutor:
    """同步执行器：`submit` 立即原地调用，供测试/单进程场景使用。"""

    def submit(self, fn: Callable[[], None]) -> None:
        fn()


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
        auto_drive(self._repo, self._engine, work_item_id)


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
        dial_factory: Callable[[str], AutonomyDial] = lambda _name: AutonomyDial.all_human(),
        implemented_stages: frozenset[S] = IMPLEMENTED_STAGES,
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
        # dial_factory：按运行时 repo 名构造 AutonomyDial（生产默认全人审；演示传放行工厂）。
        # implemented_stages：本组合根下平台能执行的阶段集合（唯一真源，见 drive.py）。
        # 三处消费：自动驱动边界、视图「待建设」标记、「推进」按钮可用性。
        self._dial_factory = dial_factory
        self._implemented_stages = implemented_stages

    @property
    def implemented_stages(self) -> frozenset[S]:
        """供路由投影使用——视图层据此标注「待建设」并计算 next_action。"""
        return self._implemented_stages

    def _run_driver(self, runner: _Driver, work_item_id: WorkItemId) -> None:
        # Executor.submit 要求 Callable[[], None]；auto_drive/step 返回 DriveStop | None，
        # 这里丢弃返回值以匹配签名（提交时是"fire and forget"，前端靠轮询取新状态）。
        runner(self._work_repo, self._engine, work_item_id, self._implemented_stages)

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

    def create_workitem(self, project_id: str, goal: str, autonomy_enabled: bool = False) -> str:
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
            self._dial_factory(project.name),
            self._clock(),
            project_id=project.id,
            base_branch=project.branch,
            autonomy_enabled=autonomy_enabled,
        )
        self._work_repo.save(work_item)
        self._executor.submit(lambda: self._run_driver(auto_drive, work_item_id))
        return work_item_id.value

    def decide_workitem(self, work_item_id: str, decision: str) -> WorkItem | None:
        """人审决策一个 WAIT_HUMAN 工作项：proceed / close / reject，随后（非终态）继续驱动。

        复用领域入口 `decide_work_item`（正确处理 finalize/事件），proceed 后须显式再驱动
        （resume 本身不驱动）。close/reject 到终态无需再驱动。
        """
        wid = WorkItemId(work_item_id)
        try:
            decide_work_item(wid, decision, self._work_repo, self._engine, self._clock())
        except KeyError:
            return None
        if decision == "proceed":
            # 手动挡下，门禁的「继续」即视为"授权走这一步"——跑一个阶段就交还控制权，
            # 免得为同一个意图点两下（先点「继续」再点「推进」）。自动挡照旧连续跑。
            wi = self._work_repo.get(wid)
            runner = auto_drive if wi.autonomy_enabled else step
            self._executor.submit(lambda: self._run_driver(runner, wid))
        return self.get_workitem(work_item_id)

    def approve_workitem(self, work_item_id: str, approved: bool = True) -> WorkItem | None:
        """向后兼容薄壳：True→proceed / False→reject，委托到 decide_workitem。"""
        return self.decide_workitem(work_item_id, "proceed" if approved else "reject")

    def advance_workitem(self, work_item_id: str) -> WorkItem | None:
        """人工单步推进一个阶段。

        **校验同步、执行异步**：单个阶段可能跑数分钟（Claude Code 子进程），因此这里
        只同步判定合法性（非法立即抛 `InvariantError` → 路由 409），真正推进交后台，
        前端靠轮询取新状态。与 `decide_workitem` 同一模式。
        """
        wid = WorkItemId(work_item_id)
        try:
            wi = self._work_repo.get(wid)
        except KeyError:
            return None
        # 准入规则只在 drive.py 定义一处；这里同步校验以立刻回 409，step 在后台再校验一次。
        ensure_advanceable(wi, self._implemented_stages)
        self._executor.submit(lambda: self._run_driver(step, wid))
        return self.get_workitem(work_item_id)

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
