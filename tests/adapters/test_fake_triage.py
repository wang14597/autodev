from autodev.adapters.demo import FakeTriage
from autodev.domain.enums import RiskLevel, TaskType, TriageIntent
from autodev.domain.value_objects import Requirement


def _sig(goal: str):
    return FakeTriage().classify(Requirement(goal, "r", (), goal))


def test_high_risk_keyword():
    assert _sig("delete old credential tokens").risk is RiskLevel.HIGH


def test_low_risk_trivial_keyword():
    assert _sig("fix typo in readme").risk is RiskLevel.LOW


def test_consultation_intent_from_query_words():
    assert _sig("排查登录为什么偶发失败").intent is TriageIntent.CONSULTATION
    assert _sig("how does auth work, please explain").intent is TriageIntent.CONSULTATION


def test_actionable_intent_default():
    assert _sig("add a rate limiter to the api").intent is TriageIntent.ACTIONABLE


def test_multi_module_scope_not_small():
    sig = _sig("refactor the auth flow across multiple modules and services")
    assert sig.level in (TaskType.MEDIUM_FEATURE, TaskType.COMPLEX_FEATURE)


def test_explicit_intent_override():
    sig = FakeTriage(intent=TriageIntent.CONSULTATION).classify(Requirement("x", "r", (), "x"))
    assert sig.intent is TriageIntent.CONSULTATION
