"""确定性演示适配器 + 放行 dial 工厂（切片 2.1，仅用于演示/E2E 组合根）。

放行 dial 是最隐蔽的坑：`AutonomyDial.needs_human` 按 (TaskType, repo, GatePoint) 精确
匹配，故 dial 必须按运行时 repo 名动态构造，不能硬编码固定名。
"""

from __future__ import annotations

from autodev.adapters.demo import (
    DemoContext,
    DemoDelivery,
    DemoDesign,
    DemoExecution,
    DemoReview,
    DemoVerification,
    DemoWorkspace,
    release_all_dial,
)
from autodev.domain.artifacts import (
    AcceptanceArtifact,
    ContextArtifact,
    DesignArtifact,
)
from autodev.domain.enums import GatePoint, TaskType, WorkspaceMode
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import RepoRef, Requirement, WorkspaceHandle


def test_release_all_dial_releases_named_repo_for_all_combos() -> None:
    dial = release_all_dial("demo-proj")
    for t in TaskType:
        for g in GatePoint:
            assert not dial.needs_human(t, "demo-proj", g)


def test_release_all_dial_does_not_release_other_repos() -> None:
    dial = release_all_dial("demo-proj")
    assert dial.needs_human(TaskType.SMALL_CHANGE, "other-proj", GatePoint.REVIEW_GATE)


def test_demo_workspace_is_deterministic_and_has_cleanup() -> None:
    ws = DemoWorkspace()
    assert ws.repo_status(RepoRef("r")).exists_local is True
    assert ws.prepare(RepoRef("r")) == ws.prepare(RepoRef("r"))  # 确定性
    handle = ws.provision(WorkItemId.new(), RepoRef("r"), WorkspaceMode.REUSE, "b")
    assert isinstance(handle, WorkspaceHandle)
    ws.cleanup(handle)  # cleanup 必须存在（finalize_done 会调用），no-op 即可
    assert ws.list_branches(RepoRef("r"))


def test_demo_stage_adapters_return_valid_artifacts(tmp_path) -> None:
    req = Requirement("g", "r", (), "g")
    handle = WorkspaceHandle(str(tmp_path), "b")
    ctx = DemoContext(autodev_home=tmp_path).gather(req, handle)
    assert isinstance(ctx, ContextArtifact)
    design = DemoDesign().propose(req, ctx)
    assert isinstance(design, DesignArtifact)
    assert DemoReview().review(design, ctx).approved is True
    assert DemoExecution().implement(design, handle).test_passed is True
    verdict = DemoVerification().verify(AcceptanceArtifact(("ok",)), handle).verdict
    assert verdict.passed is True
    assert DemoDelivery().submit(req, design, handle).change_request_url
