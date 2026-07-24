from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkItemId:
    value: str

    @classmethod
    def new(cls) -> WorkItemId:
        return cls(uuid.uuid4().hex)


@dataclass(frozen=True)
class ProjectId:
    value: str

    @classmethod
    def new(cls) -> ProjectId:
        return cls(uuid.uuid4().hex)
