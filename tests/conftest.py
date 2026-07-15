# tests/conftest.py
from datetime import datetime

import pytest

from autodev.application.context import StageContext
from autodev.application.engine import Engine
from autodev.domain.policies import GatePolicy, TriagePolicy
from tests.fakes import (
    FakeContext,
    FakeDelivery,
    FakeDesign,
    FakeExecution,
    FakeReview,
    FakeVerification,
    FakeWorkspace,
)

FIXED_NOW = datetime(2026, 7, 15, 9, 0, 0)


@pytest.fixture
def make_engine():
    def _make(repo, bus, *, review_ok=True, verify_ok=True):
        ctx = StageContext(
            FakeWorkspace(local=True),
            FakeContext(),
            FakeDesign(),
            FakeReview(approved=review_ok),
            FakeExecution(),
            FakeVerification(passed=verify_ok),
            FakeDelivery(),
            TriagePolicy(),
            GatePolicy(),
        )
        return Engine(repo, bus, ctx, clock=lambda: FIXED_NOW)

    return _make
