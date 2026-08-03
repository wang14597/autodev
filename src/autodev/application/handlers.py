from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import cast

from autodev.application.context import StageContext
from autodev.domain.artifacts import (
    AcceptanceArtifact,
    ContextArtifact,
    DesignArtifact,
    ReviewArtifact,
    TriageArtifact,
)
from autodev.domain.enums import (
    FailureKind,
    GatePoint,
    RiskLevel,
    TaskType,
    TriageIntent,
    WorkflowState,
)
from autodev.domain.errors import StageError
from autodev.domain.outcome import StageOutcome
from autodev.domain.policies import AutonomyPolicy, workspace_mode_for
from autodev.domain.work_item import WorkItem


def branch_for(work_item: WorkItem) -> str:
    return f"autodev/{work_item.id.value[:8]}"


def handle_intake(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    if not work_item.requirement.is_complete():
        return StageOutcome.fail(
            FailureKind.FATAL, "requirement incomplete; needs human clarification"
        )
    return StageOutcome.ok()


def handle_triage(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    status = ctx.workspace.repo_status(work_item.repo_ref)
    mode = workspace_mode_for(status)
    try:
        sig = ctx.triage.classify(work_item.requirement)
        artifact = TriageArtifact(
            sig.level, sig.confidence, mode, sig.risk, sig.signals, sig.intent
        )
    except StageError:
        # 分诊基础设施失败（已在 ACL 边界翻译）→ 降级产物：低置信 + unavailable 信号，
        # 使 AutonomyPolicy 规则 1 随后导向 CONTEXT_GATE 人审（失败→挂起，不 FAILED）。
        artifact = TriageArtifact(
            TaskType.SMALL_CHANGE,
            0.0,
            mode,
            RiskLevel.HIGH,
            ("triage-unavailable",),
            TriageIntent.ACTIONABLE,
        )
    work_item.type = artifact.level
    return StageOutcome.ok("triage", artifact)


def handle_context(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    triage = cast(TriageArtifact, work_item.artifacts["triage"])
    handle = ctx.workspace.provision(
        work_item.id,
        work_item.repo_ref,
        triage.workspace_mode,
        branch_for(work_item),
        base_branch=work_item.base_branch,
    )
    artifact = ctx.gatherer.gather(work_item.requirement, handle)
    # 上下文后决策（AutonomyPolicy 只读 triage 产物，已入库；context 产物由引擎按 outcome 入库）。
    decision = AutonomyPolicy().decide_after_context(work_item)
    if decision == "suspend":
        return StageOutcome.suspend(GatePoint.CONTEXT_GATE, "context", artifact)
    if decision == "finish":
        return StageOutcome.finish("context", artifact)
    return StageOutcome.ok("context", artifact)


def handle_design(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    context = cast(ContextArtifact, work_item.artifacts["context"])
    # 回退重设计时把上一轮评审意见带回设计员：否则同样输入产同样方案、招来同样打回，
    # 烧完 RetryPolicy 的 CAP 后收敛 FAILED（这条回退路径此前不可达，故从未暴露）。
    prior = work_item.artifacts.get("review")
    prior_review = prior if isinstance(prior, ReviewArtifact) else None
    artifact = ctx.designer.propose(work_item.requirement, context, prior_review)
    return StageOutcome.ok("design", artifact)


def handle_review(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    context = cast(ContextArtifact, work_item.artifacts["context"])
    design = cast(DesignArtifact, work_item.artifacts["design"])
    review = ctx.reviewer.review(design, context)
    if not review.approved:
        return StageOutcome.fail(FailureKind.LOGIC, f"review rejected: {review.comments}")
    decision = ctx.gate_policy.decide(work_item, GatePoint.REVIEW_GATE)
    if decision.needs_human:
        return StageOutcome.suspend(GatePoint.REVIEW_GATE, "review", review)
    return StageOutcome.ok("review", review)


def handle_impl(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    design = cast(DesignArtifact, work_item.artifacts["design"])
    context = work_item.artifacts["context"]
    handle = _handle_from_context(context)
    impl = ctx.executor.implement(design, handle)
    return StageOutcome.ok("impl", impl)


def handle_accept(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    criteria = ("relevant tests pass", "build succeeds") + tuple(
        work_item.requirement.acceptance_hints
    )
    return StageOutcome.ok("accept", AcceptanceArtifact(criteria))


def handle_verify(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    criteria = cast(AcceptanceArtifact, work_item.artifacts["accept"])
    context = work_item.artifacts["context"]
    handle = _handle_from_context(context)
    ver = ctx.verifier.verify(criteria, handle)
    if not ver.verdict.passed:
        return StageOutcome.fail(FailureKind.LOGIC, f"verification failed: {ver.verdict.reasons}")
    return StageOutcome.ok("verify", ver)


def handle_submit_mr(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    design = cast(DesignArtifact, work_item.artifacts["design"])
    context = work_item.artifacts["context"]
    handle = _handle_from_context(context)
    delivery = ctx.delivery.submit(work_item.requirement, design, handle)
    decision = ctx.gate_policy.decide(work_item, GatePoint.MERGE_GATE)
    if decision.needs_human:
        return StageOutcome.suspend(GatePoint.MERGE_GATE, "delivery", delivery)
    return StageOutcome.ok("delivery", delivery)


def _handle_from_context(context):
    from autodev.domain.value_objects import WorkspaceHandle

    return WorkspaceHandle(context.workspace_location, context.workspace_label)


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
