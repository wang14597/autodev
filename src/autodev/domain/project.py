# src/autodev/domain/project.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from autodev.domain.ids import ProjectId
from autodev.domain.value_objects import AutonomyDial


@dataclass
class Project:
    id: ProjectId
    name: str
    repo_source: str
    default_branch: str | None = None
    autonomy_dial: AutonomyDial = field(default_factory=AutonomyDial.all_human)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def create(cls, id: ProjectId, name: str, repo_source: str, now: datetime) -> Project:
        return cls(
            id=id,
            name=name,
            repo_source=repo_source,
            created_at=now,
            updated_at=now,
        )

    def mark_prepared(self, default_branch: str, now: datetime) -> None:
        self.default_branch = default_branch
        self.updated_at = now
