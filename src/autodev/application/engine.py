from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import cast

from autodev.application.context import StageContext
from autodev.application.handlers import HANDLERS
from autodev.domain.artifacts import ContextArtifact
from autodev.domain.enums import FailureKind
from autodev.domain.enums import WorkflowState as S
from autodev.domain.errors import StageError
from autodev.domain.events import (
    HumanApprovalRequested,
    WorkItemCompleted,
    WorkItemFailed,
)
from autodev.domain.policies import RetryPolicy, TransitionRules
from autodev.domain.ports import EventPublisher, WorkItemRepository
from autodev.domain.value_objects import WorkspaceHandle
from autodev.domain.work_item import WorkItem


class Engine:
    def __init__(
        self,
        repo: WorkItemRepository,
        publisher: EventPublisher,
        ctx: StageContext,
        clock: Callable[[], datetime],
        transition_rules: TransitionRules | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.repo = repo
        self.publisher = publisher
        self.ctx = ctx
        self.clock = clock
        self.transition_rules = transition_rules or TransitionRules()
        self.retry_policy = retry_policy or RetryPolicy()

    def advance(self, work_item: WorkItem) -> None:
        if not work_item.is_runnable():
            return
        now = self.clock()
        handler = HANDLERS[work_item.state]
        try:
            outcome = handler(work_item, self.ctx, now)
        except StageError as e:
            outcome = _to_failure(e.failure_kind, e.message)
        except Exception as e:  # noqa: BLE001 未预期异常 → 有界 TRANSIENT
            outcome = _to_failure(FailureKind.TRANSIENT, f"unexpected: {e}")

        if outcome.kind == "success":
            self._on_success(work_item, outcome, now)
        elif outcome.kind == "suspend":
            self._on_suspend(work_item, outcome, now)
        else:
            self._on_failure(work_item, outcome, now)
        self.repo.save(work_item)

    def _on_success(self, wi: WorkItem, outcome, now: datetime) -> None:
        if outcome.artifact_key:
            wi.add_artifact(outcome.artifact_key, outcome.artifact)
        nxt = self.transition_rules.next_state(wi.state)
        wi.transition_to(nxt, "stage ok", now)
        if nxt is S.DONE:
            self._finalize_done(wi)

    def _on_suspend(self, wi: WorkItem, outcome, now: datetime) -> None:
        if outcome.artifact_key:
            wi.add_artifact(outcome.artifact_key, outcome.artifact)
        wi.suspend(outcome.gate_point, f"awaiting human at {outcome.gate_point.name}", now)
        self.publisher.publish(HumanApprovalRequested(wi.id, outcome.gate_point))

    def _on_failure(self, wi: WorkItem, outcome, now: datetime) -> None:
        decision = self.retry_policy.decide(wi.state, outcome.failure_kind, wi.retry_ledger)
        if decision.action == "retry":
            wi.record_retry(decision.key)  # 状态不变, 下轮重试
        elif decision.action == "rollback":
            wi.record_retry(decision.key)
            # rollback always carries a target state (RetryPolicy invariant)
            wi.transition_to(cast(S, decision.target), f"rollback: {outcome.message}", now)
        else:  # fail
            origin = wi.state.name
            wi.transition_to(S.FAILED, f"failed: {outcome.message}", now)
            self.publisher.publish(WorkItemFailed(wi.id, origin, outcome.message))

    def _finalize_done(self, wi: WorkItem) -> None:
        delivery = wi.artifacts.get("delivery")
        context = wi.artifacts.get("context")
        if context is not None:
            context = cast(ContextArtifact, context)
            self.ctx.workspace.cleanup(
                WorkspaceHandle(context.workspace_location, context.workspace_label)
            )
        change_request_url = getattr(delivery, "change_request_url", "")
        self.publisher.publish(WorkItemCompleted(wi.id, change_request_url))


def _to_failure(kind: FailureKind, message: str):
    from autodev.domain.outcome import StageOutcome

    return StageOutcome.fail(kind, message)


def run_until_quiescent(repo, engine: Engine) -> None:
    while True:
        runnable = repo.claim_runnable()
        if not runnable:
            return
        for wi in runnable:
            engine.advance(wi)
