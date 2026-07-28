from datetime import datetime

from autodev.domain.enums import FailureKind, GatePoint, TaskType
from autodev.domain.enums import WorkflowState as S
from autodev.domain.policies import GatePolicy, RetryPolicy, TransitionRules
from autodev.domain.value_objects import (
    AutonomyDial,
    RepoRef,
    Requirement,
    RetryLedger,
)
from autodev.domain.work_item import WorkItem

NOW = datetime(2026, 7, 15)


def _wi(dial):
    wi = WorkItem.create(
        __import__("autodev.domain.ids", fromlist=["WorkItemId"]).WorkItemId.new(),
        RepoRef("repo-a"),
        Requirement("g", "repo-a", (), "r"),
        dial,
        NOW,
    )
    wi.type = TaskType.SMALL_CHANGE
    return wi


# 分诊的 workspace_mode 判定已抽为 workspace_mode_for（见 tests/domain/test_workspace_mode.py），
# 分诊本身现为 TriagePort（见 tests/adapters/test_fake_triage.py）。此处不再测 TriagePolicy。


def test_gate_policy_reads_dial():
    human = GatePolicy().decide(_wi(AutonomyDial.all_human()), GatePoint.REVIEW_GATE)
    assert human.needs_human
    auto_dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    assert not GatePolicy().decide(_wi(auto_dial), GatePoint.REVIEW_GATE).needs_human


def test_transition_rules_linear():
    assert TransitionRules().next_state(S.INTAKE) is S.TRIAGE
    assert TransitionRules().next_state(S.SUBMIT_MR) is S.DONE


def test_retry_policy_transient_then_fail():
    p = RetryPolicy()
    led = RetryLedger()
    d = p.decide(S.CONTEXT, FailureKind.TRANSIENT, led)
    assert d.action == "retry" and d.target is S.CONTEXT
    led = led.incremented(d.key).incremented(d.key).incremented(d.key)
    assert p.decide(S.CONTEXT, FailureKind.TRANSIENT, led).action == "fail"


def test_retry_policy_logic_rollback_and_fatal():
    p = RetryPolicy()
    d = p.decide(S.VERIFY, FailureKind.LOGIC, RetryLedger())
    assert d.action == "rollback" and d.target is S.IMPL
    # 无回退目标的 logic 失败直接 fail
    assert p.decide(S.CONTEXT, FailureKind.LOGIC, RetryLedger()).action == "fail"
    assert p.decide(S.CONTEXT, FailureKind.FATAL, RetryLedger()).action == "fail"
