"""演示组合根应用层行为（切片 2.1）：真实 Triage/Gate + 演示适配器驱动全生命周期。

验证差异化：低风险自动流转到 DONE；高风险即便 dial 放行仍在 WAIT_HUMAN 挂起；approve 后放行到 DONE。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from autodev.adapters.demo import (
    DemoContext,
    DemoDelivery,
    DemoDesign,
    DemoExecution,
    DemoReview,
    DemoVerification,
    DemoWorkspace,
    FakeTriage,
    release_all_dial,
)
from autodev.adapters.event_bus import InMemoryEventBus
from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.adapters.project_repository import InMemoryProjectRepository
from autodev.application.context import StageContext
from autodev.application.engine import Engine
from autodev.domain.enums import WorkflowState as S
from autodev.domain.policies import GatePolicy
from autodev.webapp.drive import ALL_STAGES
from autodev.webapp.projects import ProjectRegistry
from autodev.webapp.service import ProjectConsoleService, SyncExecutor

NOW = datetime(2026, 7, 25, 12, 0, 0)


def _demo_service(tmp_path: Path) -> ProjectConsoleService:
    project_repo = InMemoryProjectRepository()
    work_repo = InMemoryWorkItemRepository()
    workspace = DemoWorkspace()
    ctx = StageContext(
        workspace,
        DemoContext(autodev_home=tmp_path),
        DemoDesign(),
        DemoReview(),
        DemoExecution(),
        DemoVerification(),
        DemoDelivery(),
        FakeTriage(),
        GatePolicy(),
    )
    engine = Engine(work_repo, InMemoryEventBus(), ctx, clock=lambda: NOW)
    registry = ProjectRegistry({}, tmp_path / "repos.json")
    return ProjectConsoleService(
        project_repo,
        work_repo,
        workspace,
        engine,
        SyncExecutor(),
        registry,
        clock=lambda: NOW,
        dial_factory=release_all_dial,
        implemented_stages=ALL_STAGES,
    )


def test_low_risk_workitem_drives_to_done(tmp_path: Path) -> None:
    svc = _demo_service(tmp_path)
    pid = svc.create_project("demo-proj", "demo://repo")
    wid = svc.create_workitem(pid, "fix typo in README", autonomy_enabled=True)
    wi = svc.get_workitem(wid)
    assert wi is not None and wi.state is S.DONE


def test_high_risk_workitem_suspends_at_wait_human(tmp_path: Path) -> None:
    from autodev.domain.enums import GatePoint

    svc = _demo_service(tmp_path)
    pid = svc.create_project("demo-proj", "demo://repo")
    # 开启自主：低置信/开关不拦，靠"风险 HIGH"在 REVIEW 门挡下（证明是风险而非开关）。
    wid = svc.create_workitem(
        pid, "migrate auth to new credential store and delete old tokens", autonomy_enabled=True
    )
    wi = svc.get_workitem(wid)
    assert wi is not None
    assert wi.state is S.WAIT_HUMAN and wi.pending_gate is GatePoint.REVIEW_GATE
    assert wi.artifacts["triage"].risk.name == "HIGH"


def test_approve_resumes_high_risk_through_both_gates_to_done(tmp_path: Path) -> None:
    # 高风险在 REVIEW 与 MERGE 两个门都挂起（纵深防御）——需两次人审放行才到 DONE。
    from autodev.domain.enums import GatePoint

    svc = _demo_service(tmp_path)
    pid = svc.create_project("demo-proj", "demo://repo")
    wid = svc.create_workitem(pid, "delete the legacy credential tokens", autonomy_enabled=True)

    first = svc.get_workitem(wid)
    assert first.state is S.WAIT_HUMAN and first.pending_gate is GatePoint.REVIEW_GATE

    svc.approve_workitem(wid, approved=True)
    second = svc.get_workitem(wid)
    assert second.state is S.WAIT_HUMAN and second.pending_gate is GatePoint.MERGE_GATE

    svc.approve_workitem(wid, approved=True)
    assert svc.get_workitem(wid).state is S.DONE


def test_manual_tempo_high_risk_drives_through_both_gates_to_done_without_error(
    tmp_path: Path,
) -> None:
    """回归(BLOCKER)：手动挡(shipped 默认 autonomy_enabled=False)下人一路点「继续」/
    「推进」，最终应落到 DONE 且全程不抛异常。

    `resume_target(GatePoint.MERGE_GATE, "proceed")` 是 `S.DONE`（终态）——手动挡下
    `decide_workitem` 曾在 resume 落地终态后仍无条件提交 `step` runner，`step` 经
    `ensure_advanceable` → `classify` 判定 TERMINAL 抛 `InvariantError`，把"人审后已
    正常完成"误报成推进失败。`test_approve_resumes_high_risk_through_both_gates_to_done`
    用 `autonomy_enabled=True`（自动挡走 `auto_drive`），从未走到这条路径；本用例专门
    用手动挡把两个门(REVIEW_GATE / MERGE_GATE，加上手动挡特有的 CONTEXT_GATE)都走一遍。
    """
    svc = _demo_service(tmp_path)
    pid = svc.create_project("demo-proj", "demo://repo")
    wid = svc.create_workitem(pid, "delete the legacy credential tokens", autonomy_enabled=False)

    for _ in range(20):
        wi = svc.get_workitem(wid)
        assert wi is not None
        if wi.state is S.DONE:
            break
        if wi.state is S.WAIT_HUMAN:
            svc.approve_workitem(wid, approved=True)  # 不得抛异常（含 MERGE_GATE→DONE 那一步）
        else:
            svc.advance_workitem(wid)  # 手动挡「推进」；不得抛异常
    else:
        pytest.fail("did not reach DONE within bounded manual-tempo loop")

    assert svc.get_workitem(wid).state is S.DONE


def test_deny_high_risk_fails_cleanly(tmp_path: Path) -> None:
    svc = _demo_service(tmp_path)
    pid = svc.create_project("demo-proj", "demo://repo")
    wid = svc.create_workitem(pid, "delete the legacy credential tokens")
    svc.approve_workitem(wid, approved=False)
    assert svc.get_workitem(wid).state is S.FAILED
