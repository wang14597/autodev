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
