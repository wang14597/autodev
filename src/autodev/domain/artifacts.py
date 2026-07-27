from __future__ import annotations

from dataclasses import dataclass

from autodev.domain.enums import RiskLevel, TaskType, WorkspaceMode
from autodev.domain.value_objects import Verdict


@dataclass(frozen=True)
class TriageArtifact:
    level: TaskType
    confidence: float
    workspace_mode: WorkspaceMode
    # 风险维度（切片 2.1）：喂给 GatePolicy 做风险感知门禁；signals 为可解释依据。
    # 加默认值保证向后兼容（旧持久化产物、现有构造点无需改）。
    risk: RiskLevel = RiskLevel.LOW
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextArtifact:
    workspace_location: str
    workspace_label: str
    context_file: str


@dataclass(frozen=True)
class DesignArtifact:
    change_summary: str
    target_files: tuple[str, ...]


@dataclass(frozen=True)
class ReviewArtifact:
    approved: bool
    comments: tuple[str, ...]


@dataclass(frozen=True)
class ImplArtifact:
    diff: str
    test_passed: bool
    summary: str


@dataclass(frozen=True)
class AcceptanceArtifact:
    criteria: tuple[str, ...]


@dataclass(frozen=True)
class VerificationArtifact:
    verdict: Verdict
    details: tuple[str, ...]


@dataclass(frozen=True)
class DeliveryArtifact:
    change_request_url: str
    label: str
