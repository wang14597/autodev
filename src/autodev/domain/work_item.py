from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState as S, WorkflowState, TaskType, GatePoint
from autodev.domain.errors import InvariantError
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial, RetryLedger, Cost

@dataclass(frozen=True)
class StateTransition:
    from_state: WorkflowState
    to_state: WorkflowState
    reason: str
    at: datetime

_TERMINAL = {S.DONE, S.FAILED}

def _build_allowed() -> dict[WorkflowState, frozenset[WorkflowState]]:
    linear = [S.INTAKE, S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW,
              S.IMPL, S.ACCEPT, S.VERIFY, S.SUBMIT_MR, S.DONE]
    allowed: dict[WorkflowState, set[WorkflowState]] = {s: set() for s in S}
    for a, b in zip(linear, linear[1:]):
        allowed[a].add(b)
    # 回退
    allowed[S.VERIFY].add(S.IMPL)
    allowed[S.REVIEW].add(S.DESIGN)
    # 人审挂起
    allowed[S.REVIEW].add(S.WAIT_HUMAN)
    allowed[S.SUBMIT_MR].add(S.WAIT_HUMAN)
    allowed[S.WAIT_HUMAN].update({S.IMPL, S.DONE})
    # 任意非终态可失败
    for s in S:
        if s not in _TERMINAL:
            allowed[s].add(S.FAILED)
    return {s: frozenset(v) for s, v in allowed.items()}

@dataclass
class WorkItem:
    id: WorkItemId
    repo_ref: RepoRef
    requirement: Requirement
    autonomy_dial: AutonomyDial
    type: TaskType | None = None
    state: WorkflowState = S.INTAKE
    artifacts: dict[str, object] = field(default_factory=dict)
    history: list[StateTransition] = field(default_factory=list)
    retry_ledger: RetryLedger = field(default_factory=RetryLedger)
    cost: Cost = field(default_factory=Cost)
    pending_gate: GatePoint | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    ALLOWED = _build_allowed()

    @classmethod
    def create(cls, id: WorkItemId, repo_ref: RepoRef, requirement: Requirement,
               autonomy_dial: AutonomyDial, now: datetime) -> "WorkItem":
        return cls(id=id, repo_ref=repo_ref, requirement=requirement,
                   autonomy_dial=autonomy_dial, created_at=now, updated_at=now)

    def is_runnable(self) -> bool:
        return self.state not in (S.DONE, S.FAILED, S.WAIT_HUMAN)

    def add_artifact(self, key: str, artifact: object) -> None:
        if key in self.artifacts:
            raise InvariantError(f"artifact '{key}' already exists (append-only)")
        self.artifacts[key] = artifact

    def transition_to(self, new_state: WorkflowState, reason: str, now: datetime) -> None:
        if new_state not in self.ALLOWED[self.state]:
            raise InvariantError(f"illegal transition {self.state.name} -> {new_state.name}")
        self.history.append(StateTransition(self.state, new_state, reason, now))
        self.state = new_state
        self.updated_at = now

    def suspend(self, gate_point: GatePoint, reason: str, now: datetime) -> None:
        self.transition_to(S.WAIT_HUMAN, reason, now)
        self.pending_gate = gate_point

    def resume_to(self, target: WorkflowState, reason: str, now: datetime) -> None:
        if self.state is not S.WAIT_HUMAN:
            raise InvariantError("resume requires WAIT_HUMAN state")
        self.transition_to(target, reason, now)
        self.pending_gate = None

    def record_retry(self, key: str) -> None:
        self.retry_ledger = self.retry_ledger.incremented(key)

    def add_cost(self, tokens: int) -> None:
        self.cost = self.cost.plus(tokens)
