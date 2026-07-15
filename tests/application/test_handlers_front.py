from datetime import datetime

from autodev.application.context import StageContext
from autodev.application.handlers import handle_context, handle_design, handle_intake, handle_triage
from autodev.domain.enums import FailureKind, TaskType, WorkspaceMode
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
)

NOW = datetime(2026, 7, 15)


def _ctx(ws=None):
    return StageContext(
        workspace=ws or FakeWorkspace(local=True),
        gatherer=FakeContext(),
        designer=FakeDesign(),
        reviewer=FakeReview(),
        executor=FakeExecution(),
        verifier=FakeVerification(),
        delivery=FakeDelivery(),
        triage_policy=TriagePolicy(),
        gate_policy=GatePolicy(),
    )


def _wi(goal="fix typo", repo="repo-a"):
    return WorkItem.create(
        WorkItemId.new(),
        RepoRef(repo),
        Requirement(goal, repo, (), "raw"),
        AutonomyDial.all_human(),
        NOW,
    )


def test_intake_ok_when_complete():
    assert handle_intake(_wi(), _ctx(), NOW).kind == "success"


def test_intake_fatal_when_incomplete():
    out = handle_intake(_wi(goal=""), _ctx(), NOW)
    assert out.kind == "failure" and out.failure_kind is FailureKind.FATAL


def test_triage_sets_type_and_mode():
    wi = _wi()
    out = handle_triage(wi, _ctx(FakeWorkspace(local=True)), NOW)
    assert out.kind == "success" and out.artifact_key == "triage"
    assert wi.type is TaskType.SMALL_CHANGE
    assert out.artifact.workspace_mode is WorkspaceMode.REUSE


def test_context_provisions_workspace():
    from autodev.domain.artifacts import TriageArtifact

    wi = _wi()
    wi.type = TaskType.SMALL_CHANGE
    wi.add_artifact("triage", TriageArtifact(TaskType.SMALL_CHANGE, 0.9, WorkspaceMode.REUSE))
    out = handle_context(wi, _ctx(), NOW)
    assert out.kind == "success" and out.artifact_key == "context"
    assert out.artifact.workspace_label.startswith("autodev/")


def test_design_reads_context():
    wi = _wi()
    from autodev.domain.artifacts import ContextArtifact

    wi.add_artifact("context", ContextArtifact("/tmp/x", "autodev/abc", ("app.py",), "s"))
    out = handle_design(wi, _ctx(), NOW)
    assert out.kind == "success" and out.artifact_key == "design"
    assert "fix typo" in out.artifact.change_summary
