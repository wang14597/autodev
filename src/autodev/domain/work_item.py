from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from autodev.domain.enums import GatePoint, TaskType, WorkflowState
from autodev.domain.enums import WorkflowState as S
from autodev.domain.errors import InvariantError
from autodev.domain.ids import ProjectId, WorkItemId
from autodev.domain.value_objects import AutonomyDial, Cost, RepoRef, Requirement, RetryLedger


@dataclass(frozen=True)
class StateTransition:
    from_state: WorkflowState
    to_state: WorkflowState
    reason: str
    at: datetime


_TERMINAL = {S.DONE, S.FAILED}


def _build_allowed() -> dict[WorkflowState, frozenset[WorkflowState]]:
    linear = [
        S.INTAKE,
        S.TRIAGE,
        S.CONTEXT,
        S.DESIGN,
        S.REVIEW,
        S.IMPL,
        S.ACCEPT,
        S.VERIFY,
        S.SUBMIT_MR,
        S.DONE,
    ]
    allowed: dict[WorkflowState, set[WorkflowState]] = {s: set() for s in S}
    for a, b in zip(linear, linear[1:], strict=False):
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
    project_id: ProjectId | None = None
    state: WorkflowState = S.INTAKE
    artifact_versions: dict[str, list] = field(default_factory=dict)
    history: list[StateTransition] = field(default_factory=list)
    retry_ledger: RetryLedger = field(default_factory=RetryLedger)
    cost: Cost = field(default_factory=Cost)
    pending_gate: GatePoint | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    ALLOWED = _build_allowed()

    @classmethod
    def create(
        cls,
        id: WorkItemId,
        repo_ref: RepoRef,
        requirement: Requirement,
        autonomy_dial: AutonomyDial,
        now: datetime,
        project_id: ProjectId | None = None,
    ) -> WorkItem:
        return cls(
            id=id,
            repo_ref=repo_ref,
            requirement=requirement,
            autonomy_dial=autonomy_dial,
            project_id=project_id,
            created_at=now,
            updated_at=now,
        )

    def is_runnable(self) -> bool:
        return self.state not in (S.DONE, S.FAILED, S.WAIT_HUMAN)

    @property
    def artifacts(self) -> dict[str, object]:
        """便捷只读视图：每个阶段键的最新版本产物。"""
        return {k: v[-1] for k, v in self.artifact_versions.items()}

    def add_artifact(self, key: str, artifact: object) -> None:
        # 版本化 append-only：向该键的版本列表追加新版本，永不修改/删除已存版本。
        self.artifact_versions.setdefault(key, []).append(artifact)

    def current_artifact(self, key: str) -> object:
        return self.artifact_versions[key][-1]

    def versions_of(self, key: str) -> tuple:
        return tuple(self.artifact_versions.get(key, ()))

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
