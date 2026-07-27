from __future__ import annotations

from dataclasses import dataclass

from autodev.domain.policies import GatePolicy
from autodev.domain.ports import (
    ContextPort,
    DeliveryPort,
    DesignPort,
    ExecutionPort,
    ReviewPort,
    TriagePort,
    VerificationPort,
    WorkspacePort,
)


@dataclass
class StageContext:
    workspace: WorkspacePort
    gatherer: ContextPort
    designer: DesignPort
    reviewer: ReviewPort
    executor: ExecutionPort
    verifier: VerificationPort
    delivery: DeliveryPort
    triage: TriagePort
    gate_policy: GatePolicy
