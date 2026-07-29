from datetime import datetime

import pytest

from autodev.domain.artifacts import DesignArtifact
from autodev.domain.enums import GatePoint
from autodev.domain.enums import WorkflowState as S
from autodev.domain.errors import InvariantError
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem

NOW = datetime(2026, 7, 15, 12, 0, 0)


def _wi():
    return WorkItem.create(
        WorkItemId.new(),
        RepoRef("repo-a"),
        Requirement("fix typo", "repo-a", (), "raw"),
        AutonomyDial.all_human(),
        NOW,
    )


def test_starts_in_intake_and_runnable():
    wi = _wi()
    assert wi.state is S.INTAKE and wi.is_runnable()


def test_artifacts_append_versions_without_mutating_prior():
    wi = _wi()
    a1 = DesignArtifact(design_file="/f/x.md")
    a2 = DesignArtifact(design_file="/f/y.md")
    wi.add_artifact("design", a1)
    wi.add_artifact("design", a2)
    assert wi.current_artifact("design") is a2
    assert wi.versions_of("design") == (a1, a2)
    assert wi.artifacts["design"] is a2


def test_illegal_transition_rejected():
    wi = _wi()
    with pytest.raises(InvariantError):
        wi.transition_to(S.DONE, "skip", NOW)


def test_legal_linear_transition_records_history():
    wi = _wi()
    wi.transition_to(S.TRIAGE, "ok", NOW)
    assert wi.state is S.TRIAGE and wi.history[-1].to_state is S.TRIAGE


def test_suspend_and_resume():
    wi = _wi()
    for s in [S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW]:
        wi.transition_to(s, "ok", NOW)
    wi.suspend(GatePoint.REVIEW_GATE, "need human", NOW)
    assert wi.state is S.WAIT_HUMAN and wi.pending_gate is GatePoint.REVIEW_GATE
    assert not wi.is_runnable()
    wi.resume_to(S.IMPL, "approved", NOW)
    assert wi.state is S.IMPL and wi.pending_gate is None


def test_any_state_can_fail():
    wi = _wi()
    wi.transition_to(S.FAILED, "fatal", NOW)
    assert wi.state is S.FAILED and not wi.is_runnable()
