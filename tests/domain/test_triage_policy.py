"""真实分诊策略（切片 2.1）：关键词/规模/验收启发式 → type + confidence + risk + signals。

分诊必须确定性（无网络/无 AI），以便可重复断言与 E2E 稳定触发。
"""

from __future__ import annotations

from autodev.domain.enums import RiskLevel, TaskType
from autodev.domain.policies import TriagePolicy
from autodev.domain.value_objects import RepoStatus, Requirement

LOCAL = RepoStatus(True, True)


def _req(goal: str, hints: tuple[str, ...] = ()) -> Requirement:
    return Requirement(goal, "repo-a", hints, goal)


def test_trivial_typo_is_small_low_risk_high_confidence() -> None:
    art = TriagePolicy().triage(_req("fix typo in README", ("readme renders",)), LOCAL)
    assert art.level is TaskType.SMALL_CHANGE
    assert art.risk is RiskLevel.LOW
    assert art.confidence >= 0.7


def test_dangerous_keywords_raise_risk_to_high() -> None:
    art = TriagePolicy().triage(
        _req("migrate auth to new credential store and delete old tokens"), LOCAL
    )
    assert art.risk is RiskLevel.HIGH


def test_triage_signals_are_explainable() -> None:
    art = TriagePolicy().triage(_req("delete the payment module"), LOCAL)
    # 分诊依据可解释（供控制台展示 / 审计），高风险任务至少给出一条信号。
    assert art.signals
    assert any("delete" in s or "payment" in s for s in art.signals)


def test_vague_goal_without_hints_lowers_confidence() -> None:
    vague = TriagePolicy().triage(_req("do stuff"), LOCAL).confidence
    clear = TriagePolicy().triage(_req("fix typo in README", ("readme renders",)), LOCAL).confidence
    assert vague < clear


def test_multi_module_scope_is_not_small_change() -> None:
    art = TriagePolicy().triage(
        _req("refactor the authentication flow across multiple modules and services"), LOCAL
    )
    assert art.level in (TaskType.MEDIUM_FEATURE, TaskType.COMPLEX_FEATURE)


def test_workspace_mode_preserved() -> None:
    from autodev.domain.enums import WorkspaceMode

    assert TriagePolicy().triage(_req("x"), RepoStatus(True, True)).workspace_mode is (
        WorkspaceMode.REUSE
    )
    assert TriagePolicy().triage(_req("x"), RepoStatus(False, False)).workspace_mode is (
        WorkspaceMode.CREATE
    )
