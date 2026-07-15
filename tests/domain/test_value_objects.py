import pytest
from autodev.domain.enums import TaskType, GatePoint, FailureKind
from autodev.domain.errors import DomainError, InvariantError, StageError
from autodev.domain.value_objects import (
    RepoRef, Requirement, Verdict, GateDecision, RepoStatus,
    WorkspaceHandle, Cost, RetryLedger, AutonomyDial,
)

def test_stage_error_carries_kind():
    e = StageError(FailureKind.LOGIC, "boom")
    assert e.failure_kind is FailureKind.LOGIC and e.message == "boom"
    assert isinstance(e, DomainError)

def test_requirement_completeness():
    assert Requirement("fix typo", "repo-a", (), "raw").is_complete()
    assert not Requirement("", "repo-a", (), "raw").is_complete()
    assert not Requirement("goal", "", (), "raw").is_complete()

def test_cost_and_retry_ledger_are_immutable():
    c = Cost(0).plus(10).plus(5)
    assert c.tokens == 15
    led = RetryLedger().incremented("k").incremented("k")
    assert led.count("k") == 2 and led.count("other") == 0

def test_autonomy_dial_defaults_to_human():
    dial = AutonomyDial.all_human()
    assert dial.needs_human(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)
    auto = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    assert not auto.needs_human(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)
    assert auto.needs_human(TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE)
