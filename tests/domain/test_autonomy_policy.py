from datetime import datetime

from autodev.domain.artifacts import TriageArtifact
from autodev.domain.enums import RiskLevel, TaskType, TriageIntent, WorkspaceMode
from autodev.domain.ids import WorkItemId
from autodev.domain.policies import AutonomyPolicy
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem

NOW = datetime(2026, 7, 27)


def _wi(
    enabled: bool,
    *,
    risk: RiskLevel = RiskLevel.LOW,
    conf: float = 0.9,
    intent: TriageIntent = TriageIntent.ACTIONABLE,
    signals: tuple[str, ...] = (),
    with_triage: bool = True,
) -> WorkItem:
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("r"),
        Requirement("g", "r", (), "g"),
        AutonomyDial.all_human(),
        NOW,
        autonomy_enabled=enabled,
    )
    if with_triage:
        wi.add_artifact(
            "triage",
            TriageArtifact(TaskType.SMALL_CHANGE, conf, WorkspaceMode.REUSE, risk, signals, intent),
        )
    return wi


def test_disabled_suspends():
    assert AutonomyPolicy().decide_after_context(_wi(False)) == "suspend"


def test_enabled_consultation_finishes():
    assert (
        AutonomyPolicy().decide_after_context(_wi(True, intent=TriageIntent.CONSULTATION))
        == "finish"
    )


def test_enabled_actionable_proceeds():
    assert AutonomyPolicy().decide_after_context(_wi(True)) == "proceed"


def test_low_confidence_suspends_even_when_enabled():
    assert AutonomyPolicy().decide_after_context(_wi(True, conf=0.3)) == "suspend"


def test_triage_unavailable_suspends_even_when_enabled_consultation():
    # 安全兜底优先：unavailable 即便"开+咨询"也挂起，绝不误 finish
    assert (
        AutonomyPolicy().decide_after_context(
            _wi(True, conf=0.0, signals=("triage-unavailable",), intent=TriageIntent.CONSULTATION)
        )
        == "suspend"
    )


def test_no_triage_suspends():
    assert AutonomyPolicy().decide_after_context(_wi(True, with_triage=False)) == "suspend"
