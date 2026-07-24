# src/autodev/adapters/project_repository.py
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from autodev.domain.enums import GatePoint, TaskType
from autodev.domain.ids import ProjectId
from autodev.domain.project import Project
from autodev.domain.value_objects import AutonomyDial


class SqliteProjectRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS projects ("
                "id TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL)"
            )

    @contextmanager
    def _conn(self):
        # 每次用完提交并关闭连接, 避免长跑进程句柄泄漏; WAL + busy_timeout 容忍并发访问。
        conn = sqlite3.connect(self._db_path, timeout=5)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            with conn:  # 事务: 成功提交, 异常回滚
                yield conn
        finally:
            conn.close()  # 无论如何关闭连接

    def save(self, project: Project) -> None:
        data = json.dumps(_to_dict(project))
        with self._conn() as c:
            c.execute(
                "INSERT INTO projects(id, name, data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, data=excluded.data",
                (project.id.value, project.name, data),
            )

    def get(self, project_id: ProjectId) -> Project:
        with self._conn() as c:
            row = c.execute("SELECT data FROM projects WHERE id=?", (project_id.value,)).fetchone()
        if row is None:
            raise KeyError(project_id.value)
        return _from_dict(json.loads(row[0]))

    def get_by_name(self, name: str) -> Project | None:
        with self._conn() as c:
            row = c.execute("SELECT data FROM projects WHERE name=?", (name,)).fetchone()
        if row is None:
            return None
        return _from_dict(json.loads(row[0]))

    def list_all(self) -> list[Project]:
        with self._conn() as c:
            rows = c.execute("SELECT data FROM projects").fetchall()
        return [_from_dict(json.loads(r[0])) for r in rows]

    def delete(self, project_id: ProjectId) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM projects WHERE id=?", (project_id.value,))


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self._store: dict[str, Project] = {}

    def save(self, project: Project) -> None:
        self._store[project.id.value] = project

    def get(self, project_id: ProjectId) -> Project:
        return self._store[project_id.value]

    def get_by_name(self, name: str) -> Project | None:
        for p in self._store.values():
            if p.name == name:
                return p
        return None

    def list_all(self) -> list[Project]:
        return list(self._store.values())

    def delete(self, project_id: ProjectId) -> None:
        del self._store[project_id.value]


# ---------- 序列化（领域 ↔ dict），核心不感知 ----------


def _to_dict(p: Project) -> dict:
    return {
        "id": p.id.value,
        "name": p.name,
        "repo_source": p.repo_source,
        "branch": p.branch,
        "autonomy_dial": [[t.name, r, g.name] for (t, r, g) in p.autonomy_dial.auto_gates],
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _from_dict(d: dict) -> Project:
    return Project(
        id=ProjectId(d["id"]),
        name=d["name"],
        repo_source=d["repo_source"],
        # 兼容旧数据(字段曾名 default_branch): 新字段缺失时退回旧键。
        branch=d.get("branch") or d.get("default_branch") or "",
        autonomy_dial=AutonomyDial(
            frozenset((TaskType[t], r, GatePoint[g]) for (t, r, g) in d["autonomy_dial"])
        ),
        created_at=datetime.fromisoformat(d["created_at"]) if d.get("created_at") else None,
        updated_at=datetime.fromisoformat(d["updated_at"]) if d.get("updated_at") else None,
    )
