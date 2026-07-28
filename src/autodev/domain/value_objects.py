from __future__ import annotations

from dataclasses import dataclass, field

from autodev.domain.enums import GatePoint, RiskLevel, TaskType, TriageIntent


@dataclass(frozen=True)
class RepoRef:
    name: str


@dataclass(frozen=True)
class Requirement:
    goal: str
    target_repo: str
    acceptance_hints: tuple[str, ...]
    raw_text: str

    def is_complete(self) -> bool:
        return bool(self.goal) and bool(self.target_repo)


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class TriageSignal:
    """分诊端口的结构化产出（不含 workspace_mode——那是机械判断，见 workspace_mode_for）。"""

    level: TaskType
    confidence: float
    risk: RiskLevel
    intent: TriageIntent
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateDecision:
    needs_human: bool
    reason: str


@dataclass(frozen=True)
class RepoStatus:
    exists_local: bool
    exists_remote: bool


@dataclass(frozen=True)
class WorkspaceHandle:
    location: str
    label: str


@dataclass(frozen=True)
class Cost:
    tokens: int = 0

    def plus(self, n: int) -> Cost:
        return Cost(self.tokens + n)


@dataclass(frozen=True)
class RetryLedger:
    counts: frozenset[tuple[str, int]] = field(default_factory=frozenset)

    def _as_dict(self) -> dict[str, int]:
        return dict(self.counts)

    def count(self, key: str) -> int:
        return self._as_dict().get(key, 0)

    def incremented(self, key: str) -> RetryLedger:
        d = self._as_dict()
        d[key] = d.get(key, 0) + 1
        return RetryLedger(frozenset(d.items()))


@dataclass(frozen=True)
class AutonomyDial:
    auto_gates: frozenset[tuple[TaskType, str, GatePoint]]

    @classmethod
    def all_human(cls) -> AutonomyDial:
        return cls(frozenset())

    def needs_human(self, task_type: TaskType, repo: str, gate: GatePoint) -> bool:
        return (task_type, repo, gate) not in self.auto_gates
