from autodev.domain.enums import (
    FailureKind,
    GatePoint,
    TaskType,
    WorkflowState,
    WorkspaceMode,
)
from autodev.domain.ids import WorkItemId


def test_work_item_id_is_unique_and_hashable():
    a, b = WorkItemId.new(), WorkItemId.new()
    assert a != b
    assert isinstance(a.value, str) and len(a.value) > 0
    assert len({a, b}) == 2


def test_enum_members_present():
    assert {e.name for e in WorkflowState} >= {
        "INTAKE",
        "TRIAGE",
        "CONTEXT",
        "DESIGN",
        "REVIEW",
        "IMPL",
        "ACCEPT",
        "VERIFY",
        "SUBMIT_MR",
        "DONE",
        "WAIT_HUMAN",
        "FAILED",
    }
    assert TaskType.SMALL_CHANGE and WorkspaceMode.REUSE
    assert GatePoint.REVIEW_GATE and FailureKind.TRANSIENT
