"""风险感知门禁（切片 2.1）：风险信号只能进一步收紧、绝不放宽（OR 单调性）。

AutonomyDial 是"允许自动的上限"；高风险 / 低置信在此之上强制人审。
"""

from __future__ import annotations

from datetime import datetime

from autodev.domain.artifacts import TriageArtifact
from autodev.domain.enums import GatePoint, RiskLevel, TaskType, WorkspaceMode
from autodev.domain.ids import WorkItemId
from autodev.domain.policies import GatePolicy
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem

NOW = datetime(2026, 7, 25)
REVIEW = GatePoint.REVIEW_GATE
# 对 (SMALL_CHANGE, repo-a, REVIEW_GATE) 放行的 dial。
AUTO = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", REVIEW)}))


def _wi(
    dial: AutonomyDial,
    *,
    risk: RiskLevel = RiskLevel.LOW,
    confidence: float = 0.9,
    with_triage: bool = True,
    task: TaskType = TaskType.SMALL_CHANGE,
) -> WorkItem:
    wi = WorkItem.create(
        WorkItemId.new(), RepoRef("repo-a"), Requirement("g", "repo-a", (), "g"), dial, NOW
    )
    wi.type = task
    if with_triage:
        wi.add_artifact("triage", TriageArtifact(task, confidence, WorkspaceMode.REUSE, risk, ()))
    return wi


def test_high_risk_forces_human_even_under_auto_dial() -> None:
    assert GatePolicy().decide(_wi(AUTO, risk=RiskLevel.HIGH), REVIEW).needs_human


def test_low_risk_high_confidence_auto_dial_no_human() -> None:
    assert (
        not GatePolicy().decide(_wi(AUTO, risk=RiskLevel.LOW, confidence=0.9), REVIEW).needs_human
    )


def test_low_confidence_forces_human_even_under_auto_dial() -> None:
    assert GatePolicy().decide(_wi(AUTO, risk=RiskLevel.LOW, confidence=0.3), REVIEW).needs_human


def test_no_triage_artifact_falls_back_to_dial() -> None:
    assert not GatePolicy().decide(_wi(AUTO, with_triage=False), REVIEW).needs_human
    assert GatePolicy().decide(_wi(AutonomyDial.all_human(), with_triage=False), REVIEW).needs_human


def test_monotonic_low_risk_never_relaxes_human_dial() -> None:
    # dial 要求人审；再低的风险 / 再高的置信也不得放宽成 auto。
    wi = _wi(AutonomyDial.all_human(), risk=RiskLevel.LOW, confidence=0.99)
    assert GatePolicy().decide(wi, REVIEW).needs_human
