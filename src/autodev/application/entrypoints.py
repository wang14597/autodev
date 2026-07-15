from __future__ import annotations
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState as S, GatePoint
from autodev.domain.errors import InvariantError
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial
from autodev.domain.work_item import WorkItem
from autodev.domain.events import WorkItemCreated, WorkItemFailed

GATE_RESUME_TARGET = {GatePoint.REVIEW_GATE: S.IMPL, GatePoint.MERGE_GATE: S.DONE}

def create_work_item(repo, publisher, *, work_item_id: WorkItemId, repo_ref: RepoRef,
                     requirement: Requirement, autonomy_dial: AutonomyDial,
                     now: datetime) -> WorkItem:
    wi = WorkItem.create(work_item_id, repo_ref, requirement, autonomy_dial, now)
    repo.save(wi)
    publisher.publish(WorkItemCreated(wi.id))
    return wi

def advance_work_item(work_item_id: WorkItemId, repo, engine) -> None:
    engine.advance(repo.get(work_item_id))

def resume_work_item(work_item_id: WorkItemId, approved: bool, repo, engine,
                     now: datetime) -> None:
    wi = repo.get(work_item_id)
    if wi.state is not S.WAIT_HUMAN:
        raise InvariantError("resume requires WAIT_HUMAN")
    gate = wi.pending_gate
    if approved:
        target = GATE_RESUME_TARGET[gate]
        wi.resume_to(target, f"approved at {gate.name}", now)
        if target is S.DONE:
            engine._finalize_done(wi)
    else:
        origin = wi.state.name
        wi.resume_to(S.FAILED, f"denied at {gate.name}", now)
        engine.publisher.publish(WorkItemFailed(wi.id, origin, "human denied"))
    repo.save(wi)
