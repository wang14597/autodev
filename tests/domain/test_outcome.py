from autodev.domain.artifacts import DesignArtifact
from autodev.domain.enums import FailureKind, GatePoint
from autodev.domain.events import HumanApprovalRequested, WorkItemCreated
from autodev.domain.ids import WorkItemId
from autodev.domain.outcome import StageOutcome


def test_stage_outcome_variants():
    a = DesignArtifact(design_file="/f/d.md")
    ok = StageOutcome.ok("design", a)
    assert ok.kind == "success" and ok.artifact_key == "design" and ok.artifact is a
    sus = StageOutcome.suspend(GatePoint.REVIEW_GATE, "review", a)
    assert sus.kind == "suspend" and sus.gate_point is GatePoint.REVIEW_GATE
    fail = StageOutcome.fail(FailureKind.LOGIC, "nope")
    assert fail.kind == "failure" and fail.failure_kind is FailureKind.LOGIC


def test_events_carry_work_item_id():
    wid = WorkItemId.new()
    assert WorkItemCreated(wid).work_item_id == wid
    assert HumanApprovalRequested(wid, GatePoint.MERGE_GATE).gate_point is GatePoint.MERGE_GATE
