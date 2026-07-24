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
    branch: str = ""
    autonomy_dial: AutonomyDial = field(default_factory=AutonomyDial.all_human)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def create(
        cls, id: ProjectId, name: str, repo_source: str, branch: str, now: datetime
    ) -> Project:
        return cls(
            id=id,
            name=name,
            repo_source=repo_source,
            branch=branch,
            created_at=now,
            updated_at=now,
        )

    def mark_prepared(self, branch: str, now: datetime) -> None:
        self.branch = branch
        self.updated_at = now
