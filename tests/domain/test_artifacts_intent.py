from autodev.domain.artifacts import TriageArtifact
from autodev.domain.enums import GatePoint, RiskLevel, TaskType, TriageIntent, WorkspaceMode


def test_triage_artifact_defaults_intent_actionable():
    art = TriageArtifact(TaskType.SMALL_CHANGE, 0.9, WorkspaceMode.REUSE)
    assert art.intent is TriageIntent.ACTIONABLE


def test_triage_artifact_carries_consultation_intent():
    art = TriageArtifact(
        TaskType.SMALL_CHANGE,
        0.9,
        WorkspaceMode.REUSE,
        RiskLevel.LOW,
        ("x",),
        TriageIntent.CONSULTATION,
    )
    assert art.intent is TriageIntent.CONSULTATION


def test_context_gate_exists():
    assert GatePoint.CONTEXT_GATE
