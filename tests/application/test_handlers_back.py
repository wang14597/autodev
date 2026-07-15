from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import TaskType, GatePoint, FailureKind, WorkflowState as S
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial
from autodev.domain.artifacts import (DesignArtifact, ContextArtifact,
                                       AcceptanceArtifact, ImplArtifact)
from autodev.domain.work_item import WorkItem
from autodev.domain.policies import TriagePolicy, GatePolicy
from autodev.application.context import StageContext
from autodev.application.handlers import (
    handle_review, handle_impl, handle_accept, handle_verify, handle_submit_mr, HANDLERS,
)
from tests.fakes import (FakeWorkspace, FakeContext, FakeDesign, FakeReview,
                         FakeExecution, FakeVerification, FakeDelivery)

NOW = datetime(2026, 7, 15)

def _ctx(review_ok=True, verify_ok=True, dial=None):
    return StageContext(
        workspace=FakeWorkspace(), gatherer=FakeContext(), designer=FakeDesign(),
        reviewer=FakeReview(approved=review_ok), executor=FakeExecution(),
        verifier=FakeVerification(passed=verify_ok), delivery=FakeDelivery(),
        triage_policy=TriagePolicy(), gate_policy=GatePolicy(),
    ), (dial or AutonomyDial.all_human())

def _wi(dial):
    wi = WorkItem.create(WorkItemId.new(), RepoRef("repo-a"),
                         Requirement("fix typo", "repo-a", ("msg correct",), "raw"), dial, NOW)
    wi.type = TaskType.SMALL_CHANGE
    wi.add_artifact("context", ContextArtifact("/tmp/x", "autodev/abc", ("app.py",), "s"))
    wi.add_artifact("design", DesignArtifact("do: fix typo", ("app.py",)))
    return wi

def test_review_suspends_when_human_required():
    ctx, dial = _ctx(review_ok=True)
    out = handle_review(_wi(dial), ctx, NOW)
    assert out.kind == "suspend" and out.gate_point is GatePoint.REVIEW_GATE
    assert out.artifact_key == "review"

def test_review_ok_when_auto():
    auto = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    ctx, _ = _ctx(review_ok=True, dial=auto)
    out = handle_review(_wi(auto), ctx, NOW)
    assert out.kind == "success" and out.artifact_key == "review"

def test_review_rejected_is_logic_failure():
    ctx, dial = _ctx(review_ok=False)
    out = handle_review(_wi(dial), ctx, NOW)
    assert out.kind == "failure" and out.failure_kind is FailureKind.LOGIC

def test_impl_and_accept():
    ctx, dial = _ctx()
    wi = _wi(dial)
    out_impl = handle_impl(wi, ctx, NOW)
    assert out_impl.kind == "success" and out_impl.artifact_key == "impl"
    wi.add_artifact("impl", out_impl.artifact)
    out_acc = handle_accept(wi, ctx, NOW)
    assert out_acc.kind == "success"
    assert "msg correct" in out_acc.artifact.criteria

def test_verify_pass_and_fail():
    ctx_ok, dial = _ctx(verify_ok=True)
    wi = _wi(dial)
    wi.add_artifact("accept", AcceptanceArtifact(("relevant tests pass",)))
    assert handle_verify(wi, ctx_ok, NOW).kind == "success"
    ctx_bad, dial2 = _ctx(verify_ok=False)
    wi2 = _wi(dial2)
    wi2.add_artifact("accept", AcceptanceArtifact(("relevant tests pass",)))
    out = handle_verify(wi2, ctx_bad, NOW)
    assert out.kind == "failure" and out.failure_kind is FailureKind.LOGIC

def test_submit_mr_suspends_at_merge_gate():
    ctx, dial = _ctx()
    out = handle_submit_mr(_wi(dial), ctx, NOW)
    assert out.kind == "suspend" and out.gate_point is GatePoint.MERGE_GATE
    assert out.artifact.change_request_url

def test_handlers_registry_covers_all_active_states():
    assert set(HANDLERS.keys()) == {
        S.INTAKE, S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW,
        S.IMPL, S.ACCEPT, S.VERIFY, S.SUBMIT_MR,
    }
