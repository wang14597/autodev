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
from autodev.webapp.service import RUN, SyncExecutor, WorkItemConsoleService, _bounded_drive
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
    _bounded_drive(repo, engine, wid, RUN)

    got = repo.get(wid)
    assert got.state == S.REVIEW  # 跑完 DESIGN，停在 REVIEW（∉RUN）
    assert "design" in got.artifacts
