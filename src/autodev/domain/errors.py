from __future__ import annotations
from autodev.domain.enums import FailureKind

class DomainError(Exception):
    pass

class InvariantError(DomainError):
    pass

class StageError(DomainError):
    def __init__(self, failure_kind: FailureKind, message: str) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind
        self.message = message
