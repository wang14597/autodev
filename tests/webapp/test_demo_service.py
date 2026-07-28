"""演示组合根应用层行为（切片 2.1）：真实 Triage/Gate + 演示适配器驱动全生命周期。

验证差异化：低风险自动流转到 DONE；高风险即便 dial 放行仍在 WAIT_HUMAN 挂起；approve 后放行到 DONE。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
from autodev.webapp.projects import ProjectRegistry
from autodev.webapp.service import FULL_DRIVE, ProjectConsoleService, SyncExecutor

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
        run_states=FULL_DRIVE,
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


def test_deny_high_risk_fails_cleanly(tmp_path: Path) -> None:
    svc = _demo_service(tmp_path)
    pid = svc.create_project("demo-proj", "demo://repo")
    wid = svc.create_workitem(pid, "delete the legacy credential tokens")
    svc.approve_workitem(wid, approved=False)
    assert svc.get_workitem(wid).state is S.FAILED
