# src/autodev/adapters/memory_repository.py
from __future__ import annotations

from autodev.domain.ids import WorkItemId
from autodev.domain.work_item import WorkItem


class InMemoryWorkItemRepository:
    def __init__(self) -> None:
        self._store: dict[str, WorkItem] = {}

    def save(self, work_item: WorkItem) -> None:
        self._store[work_item.id.value] = work_item

    def get(self, work_item_id: WorkItemId) -> WorkItem:
        return self._store[work_item_id.value]

    def claim_runnable(self) -> list[WorkItem]:
        return [wi for wi in self._store.values() if wi.is_runnable()]

    def list_all(self) -> list[WorkItem]:
        return list(self._store.values())

    def delete(self, work_item_id: WorkItemId) -> None:
        self._store.pop(work_item_id.value, None)
