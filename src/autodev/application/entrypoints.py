from __future__ import annotations

from datetime import datetime
from typing import cast

from autodev.application.engine import Engine
from autodev.domain.enums import GatePoint
from autodev.domain.enums import WorkflowState as S
from autodev.domain.errors import InvariantError
from autodev.domain.events import WorkItemCreated, WorkItemFailed
from autodev.domain.ids import WorkItemId
from autodev.domain.ports import EventPublisher, WorkItemRepository
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem


def resume_target(gate: GatePoint, decision: str) -> S:
    """把 (门, 决策) 映射到恢复目标态。decision ∈ {"proceed","close","reject"}。"""
    if decision == "reject":
        return S.FAILED
    table = {
        (GatePoint.CONTEXT_GATE, "proceed"): S.DESIGN,
        (GatePoint.CONTEXT_GATE, "close"): S.DONE,
        (GatePoint.REVIEW_GATE, "proceed"): S.IMPL,
        (GatePoint.MERGE_GATE, "proceed"): S.DONE,
    }
    if (gate, decision) not in table:
        raise InvariantError(f"illegal decision {decision!r} at {gate.name}")
    return table[(gate, decision)]


def create_work_item(
    repo: WorkItemRepository,
    publisher: EventPublisher,
    *,
    work_item_id: WorkItemId,
    repo_ref: RepoRef,
    requirement: Requirement,
    autonomy_dial: AutonomyDial,
    now: datetime,
    autonomy_enabled: bool = False,
) -> WorkItem:
    wi = WorkItem.create(
        work_item_id, repo_ref, requirement, autonomy_dial, now, autonomy_enabled=autonomy_enabled
    )
    repo.save(wi)
    publisher.publish(WorkItemCreated(wi.id))
    return wi


def advance_work_item(work_item_id: WorkItemId, repo: WorkItemRepository, engine: Engine) -> None:
    engine.advance(repo.get(work_item_id))


def decide_work_item(
    work_item_id: WorkItemId,
    decision: str,
    repo: WorkItemRepository,
    engine: Engine,
    now: datetime,
) -> None:
    """人审决策恢复：decision ∈ {"proceed","close","reject"}。承载真正逻辑。"""
    wi = repo.get(work_item_id)
    if wi.state is not S.WAIT_HUMAN:
        raise InvariantError("resume requires WAIT_HUMAN")
    # invariant: WAIT_HUMAN always carries a pending gate
    gate = cast(GatePoint, wi.pending_gate)
    target = resume_target(gate, decision)
    wi.resume_to(target, f"{decision} at {gate.name}", now)
    if target is S.DONE:
        engine._finalize_done(wi)
    elif target is S.FAILED:
        engine.publisher.publish(WorkItemFailed(wi.id, gate.name, f"human {decision}"))
    repo.save(wi)


def resume_work_item(
    work_item_id: WorkItemId,
    approved: bool,
    repo: WorkItemRepository,
    engine: Engine,
    now: datetime,
) -> None:
    """向后兼容薄壳：布尔批准委托到 decide_work_item（True→proceed / False→reject）。"""
    decide_work_item(work_item_id, "proceed" if approved else "reject", repo, engine, now)
