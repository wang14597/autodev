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
from autodev.domain.ids import ProjectId, WorkItemId
from autodev.domain.project import Project
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
        self,
        work_item_id: WorkItemId,
        repo: RepoRef,
        mode: WorkspaceMode,
        branch: str,
        base_branch: str | None = None,
    ) -> WorkspaceHandle: ...
    def cleanup(self, handle: WorkspaceHandle) -> None: ...
    def prepare(self, repo: RepoRef, branch: str | None = None) -> str: ...
    def list_branches(self, repo: RepoRef) -> list[str]: ...


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
    def list_all(self) -> list[WorkItem]: ...
    def delete(self, work_item_id: WorkItemId) -> None: ...


class ProjectRepository(Protocol):
    def save(self, project: Project) -> None: ...
    def get(self, project_id: ProjectId) -> Project: ...
    def get_by_name(self, name: str) -> Project | None: ...
    def list_all(self) -> list[Project]: ...
    def delete(self, project_id: ProjectId) -> None: ...


class EventPublisher(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
