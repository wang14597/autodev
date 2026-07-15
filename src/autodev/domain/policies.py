from __future__ import annotations
from dataclasses import dataclass
from autodev.domain.enums import (
    WorkflowState as S, WorkflowState, WorkspaceMode, TaskType, GatePoint, FailureKind,
)
from autodev.domain.errors import InvariantError
from autodev.domain.value_objects import Requirement, RepoStatus, RetryLedger, GateDecision
from autodev.domain.artifacts import TriageArtifact
from autodev.domain.work_item import WorkItem

class TriagePolicy:
    def triage(self, requirement: Requirement, status: RepoStatus) -> TriageArtifact:
        if status.exists_local:
            mode = WorkspaceMode.WORKTREE
        elif status.exists_remote:
            mode = WorkspaceMode.CLONE
        else:
            mode = WorkspaceMode.CREATE
        return TriageArtifact(level=TaskType.SMALL_CHANGE, confidence=0.9, workspace_mode=mode)

class GatePolicy:
    def decide(self, work_item: WorkItem, gate: GatePoint) -> GateDecision:
        if work_item.type is None:
            return GateDecision(True, "type unknown -> require human")
        needs = work_item.autonomy_dial.needs_human(work_item.type, work_item.repo_ref.name, gate)
        return GateDecision(needs, "per autonomy dial")

_NEXT = {
    S.INTAKE: S.TRIAGE, S.TRIAGE: S.CONTEXT, S.CONTEXT: S.DESIGN,
    S.DESIGN: S.REVIEW, S.REVIEW: S.IMPL, S.IMPL: S.ACCEPT,
    S.ACCEPT: S.VERIFY, S.VERIFY: S.SUBMIT_MR, S.SUBMIT_MR: S.DONE,
}

class TransitionRules:
    def next_state(self, state: WorkflowState) -> WorkflowState:
        if state not in _NEXT:
            raise InvariantError(f"no linear successor for {state.name}")
        return _NEXT[state]

@dataclass(frozen=True)
class RetryDecision:
    action: str  # "retry" | "rollback" | "fail"
    target: WorkflowState | None
    key: str

class RetryPolicy:
    CAP = 3
    ROLLBACK_TARGET = {S.VERIFY: S.IMPL, S.REVIEW: S.DESIGN}

    def decide(self, state: WorkflowState, failure_kind: FailureKind,
               ledger: RetryLedger) -> RetryDecision:
        if failure_kind is FailureKind.FATAL:
            return RetryDecision("fail", None, "")
        if failure_kind is FailureKind.TRANSIENT:
            key = f"{state.name}:transient"
            if ledger.count(key) >= self.CAP:
                return RetryDecision("fail", None, key)
            return RetryDecision("retry", state, key)
        # LOGIC
        target = self.ROLLBACK_TARGET.get(state)
        if target is None:
            return RetryDecision("fail", None, f"{state.name}:logic")
        key = f"{state.name}:logic"
        if ledger.count(key) >= self.CAP:
            return RetryDecision("fail", None, key)
        return RetryDecision("rollback", target, key)
