from __future__ import annotations

from collections.abc import Callable

from autodev.domain.events import DomainEvent


class InMemoryEventBus:
    def __init__(self) -> None:
        self._subs: list[Callable[[DomainEvent], None]] = []

    def subscribe(self, handler: Callable[[DomainEvent], None]) -> None:
        self._subs.append(handler)

    def publish(self, event: DomainEvent) -> None:
        for h in list(self._subs):
            h(event)
