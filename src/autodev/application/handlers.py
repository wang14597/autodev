from __future__ import annotations
from datetime import datetime
from autodev.domain.work_item import WorkItem
from autodev.domain.outcome import StageOutcome
from autodev.domain.enums import FailureKind
from autodev.application.context import StageContext

def branch_for(work_item: WorkItem) -> str:
    return f"autodev/{work_item.id.value[:8]}"

def handle_intake(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    if not work_item.requirement.is_complete():
        return StageOutcome.fail(FailureKind.FATAL, "requirement incomplete; needs human clarification")
    return StageOutcome.ok()

def handle_triage(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    status = ctx.workspace.repo_status(work_item.repo_ref)
    artifact = ctx.triage_policy.triage(work_item.requirement, status)
    work_item.type = artifact.level
    return StageOutcome.ok("triage", artifact)

def handle_context(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    triage = work_item.artifacts["triage"]
    handle = ctx.workspace.provision(
        work_item.id, work_item.repo_ref, triage.workspace_mode, branch_for(work_item),
    )
    artifact = ctx.gatherer.gather(work_item.requirement, handle)
    return StageOutcome.ok("context", artifact)

def handle_design(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    context = work_item.artifacts["context"]
    artifact = ctx.designer.propose(work_item.requirement, context)
    return StageOutcome.ok("design", artifact)

from typing import Callable
from autodev.domain.enums import GatePoint, WorkflowState
from autodev.domain.artifacts import AcceptanceArtifact

def handle_review(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    context = work_item.artifacts["context"]
    design = work_item.artifacts["design"]
    review = ctx.reviewer.review(design, context)
    if not review.approved:
        return StageOutcome.fail(FailureKind.LOGIC, f"review rejected: {review.comments}")
    decision = ctx.gate_policy.decide(work_item, GatePoint.REVIEW_GATE)
    if decision.needs_human:
        return StageOutcome.suspend(GatePoint.REVIEW_GATE, "review", review)
    return StageOutcome.ok("review", review)

def handle_impl(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    design = work_item.artifacts["design"]
    context = work_item.artifacts["context"]
    handle = _handle_from_context(context)
    impl = ctx.executor.implement(design, handle)
    return StageOutcome.ok("impl", impl)

def handle_accept(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    criteria = ("relevant tests pass", "build succeeds") + tuple(work_item.requirement.acceptance_hints)
    return StageOutcome.ok("accept", AcceptanceArtifact(criteria))

def handle_verify(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    criteria = work_item.artifacts["accept"]
    context = work_item.artifacts["context"]
    handle = _handle_from_context(context)
    ver = ctx.verifier.verify(criteria, handle)
    if not ver.verdict.passed:
        return StageOutcome.fail(FailureKind.LOGIC, f"verification failed: {ver.verdict.reasons}")
    return StageOutcome.ok("verify", ver)

def handle_submit_mr(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    design = work_item.artifacts["design"]
    context = work_item.artifacts["context"]
    handle = _handle_from_context(context)
    delivery = ctx.delivery.submit(work_item.requirement, design, handle)
    decision = ctx.gate_policy.decide(work_item, GatePoint.MERGE_GATE)
    if decision.needs_human:
        return StageOutcome.suspend(GatePoint.MERGE_GATE, "delivery", delivery)
    return StageOutcome.ok("delivery", delivery)

def _handle_from_context(context):
    from autodev.domain.value_objects import WorkspaceHandle
    return WorkspaceHandle(context.worktree_path, context.branch)

HANDLERS: dict[WorkflowState, Callable] = {
    WorkflowState.INTAKE: handle_intake,
    WorkflowState.TRIAGE: handle_triage,
    WorkflowState.CONTEXT: handle_context,
    WorkflowState.DESIGN: handle_design,
    WorkflowState.REVIEW: handle_review,
    WorkflowState.IMPL: handle_impl,
    WorkflowState.ACCEPT: handle_accept,
    WorkflowState.VERIFY: handle_verify,
    WorkflowState.SUBMIT_MR: handle_submit_mr,
}
