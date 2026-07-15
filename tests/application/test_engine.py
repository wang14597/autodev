# tests/application/test_engine.py
from datetime import datetime

from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.application.context import StageContext
from autodev.application.engine import Engine, run_until_quiescent
from autodev.domain.enums import GatePoint, TaskType
from autodev.domain.enums import WorkflowState as S
from autodev.domain.events import HumanApprovalRequested, WorkItemFailed
from autodev.domain.ids import WorkItemId
from autodev.domain.policies import GatePolicy, TriagePolicy
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem
from tests.fakes import (
    FakeContext,
    FakeDelivery,
    FakeDesign,
    FakeExecution,
    FakeReview,
    FakeVerification,
    FakeWorkspace,
    RecordingPublisher,
)

NOW = datetime(2026, 7, 15)


def _engine(repo, pub, review_ok=True, verify_ok=True):
    ctx = StageContext(
        workspace=FakeWorkspace(local=True),
        gatherer=FakeContext(),
        designer=FakeDesign(),
        reviewer=FakeReview(approved=review_ok),
        executor=FakeExecution(),
        verifier=FakeVerification(passed=verify_ok),
        delivery=FakeDelivery(),
        triage_policy=TriagePolicy(),
        gate_policy=GatePolicy(),
    )
    return Engine(repo, pub, ctx, clock=lambda: NOW)


def _wi(dial):
    return WorkItem.create(
        WorkItemId.new(), RepoRef("repo-a"), Requirement("fix typo", "repo-a", (), "raw"), dial, NOW
    )


def test_runs_until_merge_gate_suspend():
    # REVIEW_GATE 自动、MERGE_GATE 人审
    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    wi = _wi(dial)
    repo.save(wi)
    run_until_quiescent(repo, _engine(repo, pub))
    got = repo.get(wi.id)
    assert got.state is S.WAIT_HUMAN and got.pending_gate is GatePoint.MERGE_GATE
    assert any(isinstance(e, HumanApprovalRequested) for e in pub.events)
    assert "delivery" in got.artifacts


def test_verify_failure_rolls_back_and_eventually_fails():
    dial = AutonomyDial(
        frozenset(
            {
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE),
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE),
            }
        )
    )
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    eng = _engine(repo, pub, verify_ok=False)
    wi = _wi(dial)
    repo.save(wi)
    run_until_quiescent(repo, eng)
    got = repo.get(wi.id)
    assert got.state is S.FAILED
    assert any(isinstance(e, WorkItemFailed) for e in pub.events)
    assert eng.ctx.executor.calls == 4
    assert len(got.versions_of("impl")) == 4


def test_transient_failure_retries_then_succeeds():
    from autodev.domain.artifacts import ContextArtifact

    class FlakyContext:
        def __init__(self, fail_times):
            self.fail_times = fail_times
            self.calls = 0

        def gather(self, requirement, handle):
            self.calls += 1
            if self.calls <= self.fail_times:
                raise RuntimeError("transient blip")
            return ContextArtifact(handle.location, handle.label, ("app.py",), "ok")

    dial = AutonomyDial(
        frozenset(
            {
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE),
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE),
            }
        )
    )
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    eng = _engine(repo, pub)
    eng.ctx.gatherer = FlakyContext(fail_times=2)  # fail twice, succeed on 3rd
    wi = _wi(dial)
    repo.save(wi)
    run_until_quiescent(repo, eng)
    got = repo.get(wi.id)
    assert got.state is S.DONE  # recovered after retries
    assert got.retry_ledger.count("CONTEXT:transient") == 2
    assert eng.ctx.gatherer.calls == 3


def test_fully_auto_reaches_done_and_cleans_up():
    dial = AutonomyDial(
        frozenset(
            {
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE),
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE),
            }
        )
    )
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    eng = _engine(repo, pub)
    wi = _wi(dial)
    repo.save(wi)
    run_until_quiescent(repo, eng)
    got = repo.get(wi.id)
    assert got.state is S.DONE
    assert eng.ctx.workspace.cleaned  # cleanup 被调用
