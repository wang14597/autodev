from __future__ import annotations
from dataclasses import dataclass
from autodev.domain.ports import (
    WorkspacePort, ContextPort, DesignPort, ReviewPort,
    ExecutionPort, VerificationPort, DeliveryPort,
)
from autodev.domain.policies import TriagePolicy, GatePolicy

@dataclass
class StageContext:
    workspace: WorkspacePort
    gatherer: ContextPort
    designer: DesignPort
    reviewer: ReviewPort
    executor: ExecutionPort
    verifier: VerificationPort
    delivery: DeliveryPort
    triage_policy: TriagePolicy
    gate_policy: GatePolicy
