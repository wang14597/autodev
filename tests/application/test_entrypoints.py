from datetime import datetime

from autodev.adapters.event_bus import InMemoryEventBus
from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.application.context import StageContext
from autodev.application.engine import Engine, run_until_quiescent
from autodev.application.entrypoints import create_work_item, resume_work_item
from autodev.domain.enums import GatePoint, TaskType
from autodev.domain.enums import WorkflowState as S
from autodev.domain.events import WorkItemCompleted, WorkItemCreated, WorkItemFailed
from autodev.domain.ids import WorkItemId
from autodev.domain.policies import GatePolicy
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from tests.fakes import (
    FakeContext,
    FakeDelivery,
    FakeDesign,
    FakeExecution,
    FakeReview,
    FakeTriage,
    FakeVerification,
    FakeWorkspace,
)

NOW = datetime(2026, 7, 15)


def _engine(repo, pub):
    ctx = StageContext(
        FakeWorkspace(local=True),
        FakeContext(),
        FakeDesign(),
        FakeReview(),
        FakeExecution(),
        FakeVerification(),
        FakeDelivery(),
        FakeTriage(),
        GatePolicy(),
    )
    return Engine(repo, pub, ctx, clock=lambda: NOW)


def test_create_emits_created_event():
    repo, bus = InMemoryWorkItemRepository(), InMemoryEventBus()
    seen = []
    bus.subscribe(seen.append)
    wi = create_work_item(
        repo,
        bus,
        work_item_id=WorkItemId.new(),
        repo_ref=RepoRef("repo-a"),
        requirement=Requirement("fix typo", "repo-a", (), "raw"),
        autonomy_dial=AutonomyDial.all_human(),
        now=NOW,
    )
    assert repo.get(wi.id).state is S.INTAKE
    assert any(isinstance(e, WorkItemCreated) for e in seen)


def test_resume_at_merge_gate_completes():
    repo, bus = InMemoryWorkItemRepository(), InMemoryEventBus()
    seen = []
    bus.subscribe(seen.append)
    # REVIEW 自动, MERGE 人审 → 跑到 WAIT_HUMAN(MERGE)；开启自主以流过 CONTEXT
    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    eng = _engine(repo, bus)
    wi = create_work_item(
        repo,
        bus,
        work_item_id=WorkItemId.new(),
        repo_ref=RepoRef("repo-a"),
        requirement=Requirement("fix typo", "repo-a", (), "raw"),
        autonomy_dial=dial,
        now=NOW,
        autonomy_enabled=True,
    )
    run_until_quiescent(repo, eng)
    assert repo.get(wi.id).state is S.WAIT_HUMAN
    assert repo.get(wi.id).pending_gate is GatePoint.MERGE_GATE
    resume_work_item(wi.id, True, repo, eng, NOW)
    assert repo.get(wi.id).state is S.DONE
    assert any(isinstance(e, WorkItemCompleted) for e in seen)


def test_resume_denied_fails():
    repo, bus = InMemoryWorkItemRepository(), InMemoryEventBus()
    seen = []
    bus.subscribe(seen.append)
    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    eng = _engine(repo, bus)
    wi = create_work_item(
        repo,
        bus,
        work_item_id=WorkItemId.new(),
        repo_ref=RepoRef("repo-a"),
        requirement=Requirement("fix typo", "repo-a", (), "raw"),
        autonomy_dial=dial,
        now=NOW,
    )
    run_until_quiescent(repo, eng)
    resume_work_item(wi.id, False, repo, eng, NOW)
    assert repo.get(wi.id).state is S.FAILED
    assert any(isinstance(e, WorkItemFailed) for e in seen)
