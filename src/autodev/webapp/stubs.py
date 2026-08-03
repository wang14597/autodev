# src/autodev/webapp/stubs.py
"""DESIGN 及之后阶段的占位端口实现。

有界驱动（见 service.py）绝不会在正常流程中调用到这些方法；一旦被调用即视为越界
（比如引擎实现出现回归），因此统一抛 `StageError(FailureKind.FATAL, ...)`，快速
收敛到 FAILED 而不是静默跑出错误结果。一个类即可结构化满足 DesignPort/ReviewPort/
ExecutionPort/VerificationPort/DeliveryPort 五个协议。
"""

from __future__ import annotations

from autodev.domain.artifacts import (
    AcceptanceArtifact,
    ContextArtifact,
    DeliveryArtifact,
    DesignArtifact,
    ImplArtifact,
    ReviewArtifact,
    VerificationArtifact,
)
from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError
from autodev.domain.value_objects import Requirement, WorkspaceHandle

_MESSAGE = "stage not yet implemented"


class UnavailableStage:
    """DesignPort ∪ ReviewPort ∪ ExecutionPort ∪ VerificationPort ∪ DeliveryPort 的桩实现。"""

    def propose(
        self,
        requirement: Requirement,
        context: ContextArtifact,
        prior_review: ReviewArtifact | None = None,
    ) -> DesignArtifact:
        raise StageError(FailureKind.FATAL, _MESSAGE)

    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact:
        raise StageError(FailureKind.FATAL, _MESSAGE)

    def implement(self, design: DesignArtifact, handle: WorkspaceHandle) -> ImplArtifact:
        raise StageError(FailureKind.FATAL, _MESSAGE)

    def verify(self, criteria: AcceptanceArtifact, handle: WorkspaceHandle) -> VerificationArtifact:
        raise StageError(FailureKind.FATAL, _MESSAGE)

    def submit(
        self, requirement: Requirement, design: DesignArtifact, handle: WorkspaceHandle
    ) -> DeliveryArtifact:
        raise StageError(FailureKind.FATAL, _MESSAGE)
