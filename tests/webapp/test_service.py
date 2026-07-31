# tests/webapp/test_service.py
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from autodev.adapters.event_bus import InMemoryEventBus
from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.application.context import StageContext
from autodev.application.engine import Engine
from autodev.domain.enums import FailureKind, GatePoint
from autodev.domain.enums import WorkflowState as S
from autodev.domain.errors import StageError
from autodev.domain.policies import GatePolicy
from autodev.webapp.drive import IMPLEMENTED_STAGES, auto_drive
from autodev.webapp.service import SyncExecutor, WorkItemConsoleService
from autodev.webapp.stubs import UnavailableStage
from tests.fakes import FakeContext, FakeDesign, FakeTriage, FakeWorkspace

NOW = datetime(2026, 7, 22, 12, 0, 0)


def _engine(repo, gatherer=None):
    stage = UnavailableStage()
    ctx = StageContext(
        FakeWorkspace(),
        gatherer if gatherer is not None else FakeContext(),
        stage,
        stage,
        stage,
        stage,
        stage,
        FakeTriage(),
        GatePolicy(),
    )
    return Engine(repo, InMemoryEventBus(), ctx, clock=lambda: NOW)


def _service(engine, repo=None, clock=lambda: NOW):
    repo = repo or InMemoryWorkItemRepository()
    return repo, WorkItemConsoleService(repo, engine, SyncExecutor(), clock=clock)


def _increasing_clock():
    state = {"n": 0}

    def clock() -> datetime:
        state["n"] += 1
        return NOW + timedelta(seconds=state["n"])

    return clock


class _AlwaysFailingGatherer:
    def gather(self, requirement, handle):
        raise StageError(FailureKind.TRANSIENT, "boom")


def test_create_drives_to_context_and_rests_at_context_gate():
    # 默认关自主 → 收集上下文后停在 CONTEXT_GATE 等用户决定（不再自动进 DESIGN）。
    repo = InMemoryWorkItemRepository()
    engine = _engine(repo)
    _, svc = _service(engine, repo)

    work_item_id = svc.create("加限流", "demo")
    wi = svc.get(work_item_id)

    assert wi is not None
    assert wi.state == S.WAIT_HUMAN and wi.pending_gate is GatePoint.CONTEXT_GATE
    assert "context" in wi.artifacts


def test_driver_never_calls_unimplemented_stages():
    # UnavailableStage 的 designer/reviewer/... 一旦被调用即抛 FATAL -> FAILED。
    # 断言最终态是 WAIT_HUMAN（CONTEXT_GATE，而非 FAILED），证明没有越界调用桩端口。
    repo = InMemoryWorkItemRepository()
    engine = _engine(repo)
    _, svc = _service(engine, repo)

    work_item_id = svc.create("加限流", "demo")
    wi = svc.get(work_item_id)

    assert wi is not None
    assert wi.state == S.WAIT_HUMAN and wi.pending_gate is GatePoint.CONTEXT_GATE


def test_stage_error_converges_to_failed():
    repo = InMemoryWorkItemRepository()
    engine = _engine(repo, gatherer=_AlwaysFailingGatherer())
    _, svc = _service(engine, repo)

    work_item_id = svc.create("加限流", "demo")
    wi = svc.get(work_item_id)

    assert wi is not None
    assert wi.state == S.FAILED
    assert wi.history[-1].reason.startswith("failed:")


def test_create_rejects_empty():
    repo = InMemoryWorkItemRepository()
    engine = _engine(repo)
    _, svc = _service(engine, repo)

    with pytest.raises(ValueError):
        svc.create("", "demo")
    with pytest.raises(ValueError):
        svc.create("   ", "demo")
    with pytest.raises(ValueError):
        svc.create("加限流", "")
    with pytest.raises(ValueError):
        svc.create("加限流", "   ")


def test_create_applies_project_resolver():
    # resolve_project 把原始"项目"输入(如本地路径)映射成 repo_map 里的项目名,
    # WorkItem 的 repo_ref / requirement.target_repo 用解析后的名字。
    repo = InMemoryWorkItemRepository()
    engine = _engine(repo)
    calls: list[str] = []

    def resolver(raw: str) -> str:
        calls.append(raw)
        return "voice-agent" if raw.startswith("/") else raw

    svc = WorkItemConsoleService(
        repo, engine, SyncExecutor(), clock=lambda: NOW, resolve_project=resolver
    )
    wid = svc.create("修 preflight", "/Users/me/projects/voice-agent")
    wi = svc.get(wid)

    assert calls == ["/Users/me/projects/voice-agent"]
    assert wi is not None
    assert wi.repo_ref.name == "voice-agent"
    assert wi.requirement.target_repo == "voice-agent"


def test_list_get():
    repo = InMemoryWorkItemRepository()
    engine = _engine(repo)
    _, svc = _service(engine, repo, clock=_increasing_clock())

    assert svc.list() == []
    assert svc.get("unknown-id") is None

    id_a = svc.create("需求 A", "demo-a")
    id_b = svc.create("需求 B", "demo-b")

    items = svc.list()
    assert [wi.id.value for wi in items] == [id_b, id_a]  # 新到旧

    assert svc.get(id_a) is not None
    assert svc.get(id_a).requirement.goal == "需求 A"  # type: ignore[union-attr]


def test_drive_reaches_review_and_stops_without_calling_review_stub():
    from autodev.domain.enums import TriageIntent
    from autodev.domain.ids import WorkItemId
    from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
    from autodev.domain.work_item import WorkItem

    repo = InMemoryWorkItemRepository()
    stage = UnavailableStage()
    ctx = StageContext(
        FakeWorkspace(),
        FakeContext(),
        FakeDesign(),  # designer 真实产出
        stage,  # reviewer 桩：一旦被调用即 FATAL
        stage,
        stage,
        stage,
        FakeTriage(intent=TriageIntent.ACTIONABLE),
        GatePolicy(),
    )
    engine = Engine(repo, InMemoryEventBus(), ctx, clock=lambda: NOW)

    wid = WorkItemId("wireview1")
    # 注：goal 用完整英文短句 + 非空 acceptance_hints——FakeTriage 的启发式对短/未识别
    # 目标会扣置信分（<0.5 阈值触发 AutonomyPolicy 规则 1 强制人审，与 autonomy_enabled
    # 无关）；brief 示例的短中文目标 "加限流" 实测置信 0.45，会在 CONTEXT_GATE 挂起，
    # 无法验证本用例要证明的「自动跑完 DESIGN」路径，故在此调整措辞以达到置信阈值。
    wi = WorkItem.create(
        wid,
        RepoRef("demo"),
        Requirement(
            "add rate limiting for the api gateway",
            "demo",
            ("no regression in throughput",),
            "add rate limiting for the api gateway to protect it from abuse",
        ),
        AutonomyDial.all_human(),
        NOW,
        autonomy_enabled=True,
    )
    repo.save(wi)
    auto_drive(repo, engine, wid, IMPLEMENTED_STAGES)

    got = repo.get(wid)
    assert got.state == S.REVIEW  # 跑完 DESIGN，停在 REVIEW（∉IMPLEMENTED_STAGES）
    assert "design" in got.artifacts


def _project_service_with_fakes():
    """返回 (ProjectConsoleService, work_repo)，执行器用 SyncExecutor 便于同步断言。"""
    from autodev.adapters.project_repository import InMemoryProjectRepository
    from autodev.webapp.projects import ProjectRegistry
    from autodev.webapp.service import ProjectConsoleService
    from tests.fakes import build_engine_with_fakes

    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)
    svc = ProjectConsoleService(
        InMemoryProjectRepository(),
        repo,
        FakeWorkspace(),
        engine,
        SyncExecutor(),
        ProjectRegistry({}, None),
    )
    return svc, repo


def _seed_workitem(repo, *, state: S, autonomy: bool):
    from autodev.domain.artifacts import ContextArtifact
    from autodev.domain.ids import WorkItemId
    from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
    from autodev.domain.work_item import WorkItem

    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("demo"),
        Requirement("加限流", "demo", (), "加限流"),
        AutonomyDial.all_human(),
        NOW,
        autonomy_enabled=autonomy,
    )
    if state is not S.INTAKE:
        wi.state = state
    # DESIGN 及之后的阶段处理器读取既有 context 产物（真实流水线里由 CONTEXT 阶段产出）；
    # 这里直接跳状态而非走完整驱动，需手动补上，否则 handle_design 会因 KeyError("context")
    # 被 Engine 吞成 TRANSIENT 重试、静默空转（state/artifacts 均不变，非本用例意图）。
    if state not in (S.INTAKE, S.TRIAGE, S.CONTEXT, S.WAIT_HUMAN):
        wi.add_artifact("context", ContextArtifact("/tmp/demo", "demo", "/tmp/demo/context.md"))
    repo.save(wi)
    return wi.id


def test_advance_workitem_steps_one_stage_and_exposes_capability() -> None:
    """手动挡搁浅在 DESIGN 的工作项：advance 推进一个阶段。"""
    svc, repo = _project_service_with_fakes()
    wid = _seed_workitem(repo, state=S.DESIGN, autonomy=False)

    assert svc.implemented_stages == IMPLEMENTED_STAGES
    svc.advance_workitem(wid.value)

    assert "design" in repo.get(wid).artifacts


def test_advance_workitem_rejects_illegal_state() -> None:
    """终态/未实现阶段：advance 抛 InvariantError（路由映射 409）。"""
    from autodev.domain.errors import InvariantError

    svc, repo = _project_service_with_fakes()
    wid = _seed_workitem(repo, state=S.DONE, autonomy=False)

    with pytest.raises(InvariantError):
        svc.advance_workitem(wid.value)


def test_advance_workitem_missing_returns_none() -> None:
    svc, _ = _project_service_with_fakes()
    assert svc.advance_workitem("does-not-exist") is None
