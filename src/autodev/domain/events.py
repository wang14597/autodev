from __future__ import annotations
from dataclasses import dataclass
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import GatePoint


@dataclass(frozen=True)
class DomainEvent:
    work_item_id: WorkItemId


@dataclass(frozen=True)
class WorkItemCreated(DomainEvent):
    pass


@dataclass(frozen=True)
class HumanApprovalRequested(DomainEvent):
    gate_point: GatePoint


@dataclass(frozen=True)
class WorkItemCompleted(DomainEvent):
    change_request_url: str


@dataclass(frozen=True)
class WorkItemFailed(DomainEvent):
    state_name: str
    reason: str
