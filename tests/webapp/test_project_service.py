# tests/webapp/test_project_service.py
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.adapters.project_repository import InMemoryProjectRepository
from autodev.application.context import StageContext
from autodev.application.engine import Engine
from autodev.domain.artifacts import ContextArtifact
from autodev.domain.enums import WorkflowState as S
from autodev.domain.policies import GatePolicy, TriagePolicy
from autodev.webapp.projects import ProjectRegistry
from autodev.webapp.service import ProjectConsoleService, SyncExecutor
from autodev.webapp.stubs import UnavailableStage
from tests.fakes import FakeContext, FakeWorkspace

NOW = datetime(2026, 7, 24, 12, 0, 0)


def _engine(work_repo, workspace):
    stage = UnavailableStage()
    ctx = StageContext(
        workspace,
        FakeContext(),
        stage,
        stage,
        stage,
        stage,
        stage,
        TriagePolicy(),
        GatePolicy(),
    )
    return Engine(work_repo, _NoopPublisher(), ctx, clock=lambda: NOW)


class _NoopPublisher:
    def publish(self, event) -> None:
        pass


def _increasing_clock():
    state = {"n": 0}

    def clock() -> datetime:
        state["n"] += 1
        return NOW + timedelta(seconds=state["n"])

    return clock


def _service(tmp_path: Path, clock=lambda: NOW, workspace: FakeWorkspace | None = None):
    project_repo = InMemoryProjectRepository()
    work_repo = InMemoryWorkItemRepository()
    workspace = workspace if workspace is not None else FakeWorkspace()
    engine = _engine(work_repo, workspace)
    registry = ProjectRegistry({}, tmp_path / "repos.json")
    svc = ProjectConsoleService(
        project_repo,
        work_repo,
        workspace,
        engine,
        SyncExecutor(),
        registry,
        clock=clock,
    )
    return svc, project_repo, work_repo, workspace, registry


def test_create_project_prepares_workspace_and_persists(tmp_path: Path):
    svc, project_repo, _work_repo, workspace, registry = _service(tmp_path)

    project_id = svc.create_project("demo", "git@host:team/demo.git")

    assert workspace.prepared == [("demo", None)]
    project = project_repo.get_by_name("demo")
    assert project is not None
    assert project.id.value == project_id
    assert project.branch == "main"
    assert registry.repo_map["demo"] == "git@host:team/demo.git"


def test_create_project_passes_explicit_branch_to_prepare(tmp_path: Path):
    svc, project_repo, _work_repo, workspace, _registry = _service(tmp_path)

    svc.create_project("demo", "git@host:team/demo.git", "feature/x")

    assert workspace.prepared == [("demo", "feature/x")]
    project = project_repo.get_by_name("demo")
    assert project is not None
    assert project.branch == "feature/x"


def test_create_project_blank_branch_passes_none_to_prepare(tmp_path: Path):
    svc, project_repo, _work_repo, workspace, _registry = _service(tmp_path)

    svc.create_project("demo", "git@host:team/demo.git", "")

    assert workspace.prepared == [("demo", None)]
    project = project_repo.get_by_name("demo")
    assert project is not None
    assert project.branch == "main"  # FakeWorkspace 默认分支解析结果


def test_create_project_rejects_duplicate_name(tmp_path: Path):
    svc, *_ = _service(tmp_path)
    svc.create_project("demo", "git@host:team/demo.git")

    with pytest.raises(ValueError):
        svc.create_project("demo", "git@host:team/other.git")


def test_create_project_rejects_empty_name_or_repo(tmp_path: Path):
    svc, *_ = _service(tmp_path)

    with pytest.raises(ValueError):
        svc.create_project("", "git@host:team/demo.git")
    with pytest.raises(ValueError):
        svc.create_project("   ", "git@host:team/demo.git")
    with pytest.raises(ValueError):
        svc.create_project("demo", "")
    with pytest.raises(ValueError):
        svc.create_project("demo", "   ")


def test_create_project_rolls_back_when_prepare_fails(tmp_path: Path):
    # 仓库不可达/未连 VPN 等: prepare 抛 StageError → 转 ValueError(→400), 且回滚登记,
    # 项目名不被永久占住, 可同名重试。
    from autodev.domain.enums import FailureKind
    from autodev.domain.errors import StageError

    class FailingWorkspace(FakeWorkspace):
        def prepare(self, repo, branch=None):  # type: ignore[override]
            raise StageError(FailureKind.FATAL, "仓库不可达")

    svc, project_repo, _wr, _ws, registry = _service(tmp_path, workspace=FailingWorkspace())

    with pytest.raises(ValueError):
        svc.create_project("demo", "git@host:team/demo.git")

    assert project_repo.get_by_name("demo") is None
    assert "demo" not in registry.repo_map  # 回滚, 无残留


def test_create_workitem_drives_to_design_and_sets_project_id(tmp_path: Path):
    svc, project_repo, _work_repo, _workspace, _registry = _service(tmp_path)
    project_id = svc.create_project("demo", "git@host:team/demo.git")

    work_item_id = svc.create_workitem(project_id, "加限流")
    wi = svc.get_workitem(work_item_id)

    assert wi is not None
    assert wi.state == S.DESIGN
    project = project_repo.get_by_name("demo")
    assert wi.project_id == project.id
    assert wi.repo_ref.name == project.name
    assert wi.base_branch == project.branch
    saved = _work_repo.get(wi.id)
    assert saved.base_branch == project.branch


def test_create_workitem_auto_fetches_project_branch(tmp_path: Path):
    # 建工作项时自动 fetch(prepare 项目默认分支), 保证 worktree 基于最新。
    svc, _project_repo, _work_repo, workspace, _registry = _service(tmp_path)
    pid = svc.create_project("demo", "git@host:team/demo.git", branch="main")
    assert workspace.prepared == [("demo", "main")]  # 建项目那次

    svc.create_workitem(pid, "加限流")

    # 建工作项又触发一次 prepare(fetch), 带项目默认分支
    assert workspace.prepared == [("demo", "main"), ("demo", "main")]


def test_create_workitem_tolerates_fetch_failure(tmp_path: Path):
    # 自动 fetch 失败(网络等)不应阻断建工作项(best-effort)。
    from autodev.domain.enums import FailureKind
    from autodev.domain.errors import StageError

    class FetchFailsAfterCreate(FakeWorkspace):
        def __init__(self):
            super().__init__()
            self._calls = 0

        def prepare(self, repo, branch=None):  # type: ignore[override]
            self._calls += 1
            if self._calls > 1:  # 第一次(建项目)成功, 之后(建工作项)失败
                raise StageError(FailureKind.TRANSIENT, "网络不可达")
            return super().prepare(repo, branch)

    svc, _pr, _wr, _ws, _reg = _service(tmp_path, workspace=FetchFailsAfterCreate())
    pid = svc.create_project("demo", "git@host:team/demo.git", branch="main")
    wid = svc.create_workitem(pid, "加限流")  # 不应抛
    assert svc.get_workitem(wid) is not None


def test_create_workitem_rejects_empty_goal(tmp_path: Path):
    svc, *_ = _service(tmp_path)
    project_id = svc.create_project("demo", "git@host:team/demo.git")

    with pytest.raises(ValueError):
        svc.create_workitem(project_id, "")
    with pytest.raises(ValueError):
        svc.create_workitem(project_id, "   ")


def test_create_workitem_unknown_project_raises_lookup_error(tmp_path: Path):
    svc, *_ = _service(tmp_path)

    with pytest.raises(LookupError):
        svc.create_workitem("unknown-id", "加限流")


def test_list_workitems_filters_by_project(tmp_path: Path):
    svc, *_ = _service(tmp_path, clock=_increasing_clock())
    p1 = svc.create_project("demo1", "git@host:team/demo1.git")
    p2 = svc.create_project("demo2", "git@host:team/demo2.git")

    id_a = svc.create_workitem(p1, "需求 A")
    id_b = svc.create_workitem(p1, "需求 B")
    svc.create_workitem(p2, "需求 C")

    items = svc.list_workitems(p1)
    assert {wi.id.value for wi in items} == {id_a, id_b}
    assert [wi.id.value for wi in items] == [id_b, id_a]  # 新到旧


def test_list_projects_returns_workitem_counts(tmp_path: Path):
    svc, *_ = _service(tmp_path, clock=_increasing_clock())
    p1 = svc.create_project("demo1", "git@host:team/demo1.git")
    p2 = svc.create_project("demo2", "git@host:team/demo2.git")
    svc.create_workitem(p1, "需求 A")
    svc.create_workitem(p1, "需求 B")

    results = svc.list_projects()
    counts = {p.id.value: n for p, n in results}
    assert counts[p1] == 2
    assert counts[p2] == 0
    # newest project first
    assert [p.id.value for p, _ in results][0] == p2


def test_get_project_returns_none_for_unknown(tmp_path: Path):
    svc, *_ = _service(tmp_path)
    assert svc.get_project("nope") is None


def test_get_project_returns_project(tmp_path: Path):
    svc, *_ = _service(tmp_path)
    project_id = svc.create_project("demo", "git@host:team/demo.git")
    project = svc.get_project(project_id)
    assert project is not None
    assert project.name == "demo"


def test_refresh_project_refetches_and_keeps_tracking_branch(tmp_path: Path):
    workspace = FakeWorkspace(default_branch="main")
    svc, project_repo, _work_repo, workspace, _registry = _service(tmp_path, workspace=workspace)
    project_id = svc.create_project("demo", "git@host:team/demo.git")

    branch = svc.refresh_project(project_id)

    # 刷新 = 重新 fetch, 但沿用已解析的跟踪分支(project.branch), 不是重新解析默认分支。
    assert branch == "main"
    project = project_repo.get_by_name("demo")
    assert project.branch == "main"
    assert workspace.prepared == [("demo", None), ("demo", "main")]


def test_refresh_unknown_project_raises_lookup_error(tmp_path: Path):
    svc, *_ = _service(tmp_path)
    with pytest.raises(LookupError):
        svc.refresh_project("nope")


def test_delete_project_cascades_workitems_and_cleanup(tmp_path: Path):
    svc, project_repo, work_repo, workspace, registry = _service(tmp_path)
    project_id = svc.create_project("demo", "git@host:team/demo.git")
    wid = svc.create_workitem(project_id, "加限流")  # 驱动到 DESIGN, 带 context artifact

    result = svc.delete_project(project_id)

    assert result is True
    assert svc.get_workitem(wid) is None
    assert work_repo.list_all() == []
    assert "demo" not in registry.repo_map
    assert svc.get_project(project_id) is None
    # 该工作项在 CONTEXT 阶段生成了 context artifact → cleanup 应被调用一次
    assert len(workspace.cleaned) == 1


def test_delete_project_unknown_returns_false(tmp_path: Path):
    svc, *_ = _service(tmp_path)
    assert svc.delete_project("nope") is False


def test_delete_project_skips_cleanup_when_no_context_artifact(tmp_path: Path):
    # 手工构造一个还没有 context artifact 的工作项(用 executor 不会自动驱动的场景模拟:
    # 这里直接检验 delete 对没有 "context" key 的工作项不调用 cleanup)。
    svc, project_repo, work_repo, workspace, registry = _service(tmp_path)
    project_id = svc.create_project("demo", "git@host:team/demo.git")
    project = project_repo.get_by_name("demo")

    from autodev.domain.ids import WorkItemId
    from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
    from autodev.domain.work_item import WorkItem

    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("demo"),
        Requirement("g", "demo", (), "g"),
        AutonomyDial.all_human(),
        NOW,
        project_id=project.id,
    )
    work_repo.save(wi)

    result = svc.delete_project(project_id)

    assert result is True
    assert workspace.cleaned == []


def test_list_branches_returns_workspace_branches(tmp_path: Path):
    workspace = FakeWorkspace(branches=["main", "develop"])
    svc, *_ = _service(tmp_path, workspace=workspace)
    project_id = svc.create_project("demo", "git@host:team/demo.git")

    assert svc.list_branches(project_id) == ["main", "develop"]


def test_list_branches_unknown_project_raises_lookup_error(tmp_path: Path):
    svc, *_ = _service(tmp_path)
    with pytest.raises(LookupError):
        svc.list_branches("nope")


def test_set_project_branch_updates_project_branch(tmp_path: Path):
    workspace = FakeWorkspace(branches=["main", "develop"])
    svc, project_repo, _work_repo, workspace, _registry = _service(tmp_path, workspace=workspace)
    project_id = svc.create_project("demo", "git@host:team/demo.git")

    result = svc.set_project_branch(project_id, "develop")

    assert result == "develop"
    project = project_repo.get_by_name("demo")
    assert project is not None
    assert project.branch == "develop"


def test_set_project_branch_refetches_before_validating(tmp_path: Path):
    workspace = FakeWorkspace(branches=["main", "develop"])
    svc, _project_repo, _work_repo, workspace, _registry = _service(tmp_path, workspace=workspace)
    project_id = svc.create_project("demo", "git@host:team/demo.git")
    prepared_before = len(workspace.prepared)

    svc.set_project_branch(project_id, "develop")

    assert len(workspace.prepared) == prepared_before + 1


def test_set_project_branch_tolerates_fetch_failure(tmp_path: Path):
    from autodev.domain.enums import FailureKind
    from autodev.domain.errors import StageError

    class FetchFailsOnSetBranch(FakeWorkspace):
        def __init__(self):
            super().__init__(branches=["main", "develop"])
            self._calls = 0

        def prepare(self, repo, branch=None):  # type: ignore[override]
            self._calls += 1
            if self._calls > 1:
                raise StageError(FailureKind.TRANSIENT, "网络不可达")
            return super().prepare(repo, branch)

    svc, project_repo, _wr, _ws, _reg = _service(tmp_path, workspace=FetchFailsOnSetBranch())
    project_id = svc.create_project("demo", "git@host:team/demo.git")

    result = svc.set_project_branch(project_id, "develop")

    assert result == "develop"
    assert project_repo.get_by_name("demo").branch == "develop"


def test_set_project_branch_rejects_unknown_branch(tmp_path: Path):
    workspace = FakeWorkspace(branches=["main", "develop"])
    svc, *_ = _service(tmp_path, workspace=workspace)
    project_id = svc.create_project("demo", "git@host:team/demo.git")

    with pytest.raises(ValueError):
        svc.set_project_branch(project_id, "no-such-branch")


def test_set_project_branch_rejects_empty_branch(tmp_path: Path):
    svc, *_ = _service(tmp_path)
    project_id = svc.create_project("demo", "git@host:team/demo.git")

    with pytest.raises(ValueError):
        svc.set_project_branch(project_id, "")
    with pytest.raises(ValueError):
        svc.set_project_branch(project_id, "   ")


def test_set_project_branch_unknown_project_raises_lookup_error(tmp_path: Path):
    svc, *_ = _service(tmp_path)
    with pytest.raises(LookupError):
        svc.set_project_branch("nope", "develop")


def test_delete_project_cleanup_failure_is_best_effort(tmp_path: Path):
    svc, project_repo, work_repo, workspace, registry = _service(tmp_path)
    project_id = svc.create_project("demo", "git@host:team/demo.git")
    project = project_repo.get_by_name("demo")

    from autodev.domain.ids import WorkItemId
    from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
    from autodev.domain.work_item import WorkItem

    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("demo"),
        Requirement("g", "demo", (), "g"),
        AutonomyDial.all_human(),
        NOW,
        project_id=project.id,
    )
    wi.add_artifact("context", ContextArtifact("/tmp/gone", "branch", "/tmp/gone/context.md"))
    work_repo.save(wi)

    def boom(handle):
        raise OSError("worktree already gone")

    workspace.cleanup = boom  # type: ignore[method-assign]

    result = svc.delete_project(project_id)

    assert result is True  # best-effort: cleanup 异常不阻断删除
    assert svc.get_project(project_id) is None
