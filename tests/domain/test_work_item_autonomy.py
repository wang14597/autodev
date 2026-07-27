from datetime import datetime

from autodev.domain.enums import WorkflowState as S
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem

NOW = datetime(2026, 7, 27)


def _wi(enabled: bool = False) -> WorkItem:
    return WorkItem.create(
        WorkItemId.new(),
        RepoRef("r"),
        Requirement("g", "r", (), "g"),
        AutonomyDial.all_human(),
        NOW,
        autonomy_enabled=enabled,
    )


def test_autonomy_enabled_defaults_false():
    assert _wi().autonomy_enabled is False


def test_autonomy_enabled_settable():
    assert _wi(True).autonomy_enabled is True


def test_context_can_suspend_and_resume_to_design():
    wi = _wi()
    wi.transition_to(S.TRIAGE, "", NOW)
    wi.transition_to(S.CONTEXT, "", NOW)
    wi.transition_to(S.WAIT_HUMAN, "gate", NOW)  # CONTEXT → WAIT_HUMAN 合法
    wi.transition_to(S.DESIGN, "proceed", NOW)  # WAIT_HUMAN → DESIGN 合法


def test_context_can_go_done_directly():
    wi = _wi()
    wi.transition_to(S.TRIAGE, "", NOW)
    wi.transition_to(S.CONTEXT, "", NOW)
    wi.transition_to(S.DONE, "collect-only", NOW)  # CONTEXT → DONE 合法
