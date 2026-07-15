# src/autodev/domain/ports.py
from __future__ import annotations

from typing import Protocol

from autodev.domain.artifacts import (
    AcceptanceArtifact,
    ContextArtifact,
    DeliveryArtifact,
    DesignArtifact,
    ImplArtifact,
    ReviewArtifact,
    VerificationArtifact,
)
from autodev.domain.enums import WorkspaceMode
from autodev.domain.events import DomainEvent
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import (
    RepoRef,
    RepoStatus,
    Requirement,
    WorkspaceHandle,
)
from autodev.domain.work_item import WorkItem


class WorkspacePort(Protocol):
    def repo_status(self, repo: RepoRef) -> RepoStatus: ...
    def provision(
        self, work_item_id: WorkItemId, repo: RepoRef, mode: WorkspaceMode, branch: str
    ) -> WorkspaceHandle: ...
    def cleanup(self, handle: WorkspaceHandle) -> None: ...


class ContextPort(Protocol):
    def gather(self, requirement: Requirement, handle: WorkspaceHandle) -> ContextArtifact: ...


class DesignPort(Protocol):
    def propose(self, requirement: Requirement, context: ContextArtifact) -> DesignArtifact: ...


class ReviewPort(Protocol):
    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact: ...


class ExecutionPort(Protocol):
    def implement(self, design: DesignArtifact, handle: WorkspaceHandle) -> ImplArtifact: ...


class VerificationPort(Protocol):
    def verify(
        self, criteria: AcceptanceArtifact, handle: WorkspaceHandle
    ) -> VerificationArtifact: ...


class DeliveryPort(Protocol):
    def submit(
        self, requirement: Requirement, design: DesignArtifact, handle: WorkspaceHandle
    ) -> DeliveryArtifact: ...


class WorkItemRepository(Protocol):
    def save(self, work_item: WorkItem) -> None: ...
    def get(self, work_item_id: WorkItemId) -> WorkItem: ...
    def claim_runnable(self) -> list[WorkItem]: ...


class EventPublisher(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
