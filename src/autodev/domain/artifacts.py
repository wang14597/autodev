from __future__ import annotations

from dataclasses import dataclass

from autodev.domain.enums import TaskType, WorkspaceMode
from autodev.domain.value_objects import Verdict


@dataclass(frozen=True)
class TriageArtifact:
    level: TaskType
    confidence: float
    workspace_mode: WorkspaceMode


@dataclass(frozen=True)
class ContextArtifact:
    workspace_location: str
    workspace_label: str
    relevant_files: tuple[str, ...]
    summary: str


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
