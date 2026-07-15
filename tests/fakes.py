# tests/fakes.py
from __future__ import annotations
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkspaceMode
from autodev.domain.value_objects import (
    RepoRef, Requirement, RepoStatus, WorkspaceHandle, Verdict,
)
from autodev.domain.artifacts import (
    ContextArtifact, DesignArtifact, ReviewArtifact, ImplArtifact,
    AcceptanceArtifact, VerificationArtifact, DeliveryArtifact,
)
from autodev.domain.events import DomainEvent

class FakeWorkspace:
    def __init__(self, local: bool = True, remote: bool = True):
        self.local, self.remote = local, remote
        self.cleaned: list[str] = []
    def repo_status(self, repo: RepoRef) -> RepoStatus:
        return RepoStatus(self.local, self.remote)
    def provision(self, work_item_id: WorkItemId, repo: RepoRef,
                  mode: WorkspaceMode, branch: str) -> WorkspaceHandle:
        return WorkspaceHandle(f"/tmp/{repo.name}/{work_item_id.value[:8]}", branch)
    def cleanup(self, handle: WorkspaceHandle) -> None:
        self.cleaned.append(handle.worktree_path)

class FakeContext:
    def gather(self, requirement: Requirement, handle: WorkspaceHandle) -> ContextArtifact:
        return ContextArtifact(handle.worktree_path, handle.branch, ("app.py",), "fake context")

class FakeDesign:
    def propose(self, requirement: Requirement, context: ContextArtifact) -> DesignArtifact:
        return DesignArtifact(f"do: {requirement.goal}", ("app.py",))

class FakeReview:
    def __init__(self, approved: bool = True):
        self.approved = approved
    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact:
        return ReviewArtifact(self.approved, () if self.approved else ("rejected",))

class FakeExecution:
    def __init__(self, test_passed: bool = True):
        self.test_passed = test_passed
        self.calls = 0
    def implement(self, design: DesignArtifact, handle: WorkspaceHandle) -> ImplArtifact:
        self.calls += 1
        return ImplArtifact("--- diff ---", self.test_passed, "fake impl")

class FakeVerification:
    def __init__(self, passed: bool = True):
        self.passed = passed
    def verify(self, criteria: AcceptanceArtifact, handle: WorkspaceHandle) -> VerificationArtifact:
        return VerificationArtifact(Verdict(self.passed, () if self.passed else ("tests failed",)),
                                    ("ran fake checks",))

class FakeDelivery:
    def submit(self, requirement: Requirement, design: DesignArtifact,
               handle: WorkspaceHandle) -> DeliveryArtifact:
        return DeliveryArtifact(f"https://gitlab.example/mr/{handle.branch}", handle.branch)

class RecordingPublisher:
    def __init__(self):
        self.events: list[DomainEvent] = []
    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)
