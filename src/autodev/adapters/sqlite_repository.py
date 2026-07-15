# src/autodev/adapters/sqlite_repository.py
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState, TaskType, WorkspaceMode, GatePoint
from autodev.domain.value_objects import (
    RepoRef, Requirement, AutonomyDial, RetryLedger, Cost, Verdict,
)
from autodev.domain.artifacts import (
    TriageArtifact, ContextArtifact, DesignArtifact, ReviewArtifact,
    ImplArtifact, AcceptanceArtifact, VerificationArtifact, DeliveryArtifact,
)
from autodev.domain.work_item import WorkItem, StateTransition

_TERMINAL_OR_WAIT = ("DONE", "FAILED", "WAIT_HUMAN")

class SqliteWorkItemRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS work_items ("
                      "id TEXT PRIMARY KEY, state TEXT NOT NULL, data TEXT NOT NULL)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def save(self, work_item: WorkItem) -> None:
        data = json.dumps(_to_dict(work_item))
        with self._conn() as c:
            c.execute("INSERT INTO work_items(id, state, data) VALUES(?,?,?) "
                      "ON CONFLICT(id) DO UPDATE SET state=excluded.state, data=excluded.data",
                      (work_item.id.value, work_item.state.name, data))

    def get(self, work_item_id: WorkItemId) -> WorkItem:
        with self._conn() as c:
            row = c.execute("SELECT data FROM work_items WHERE id=?",
                            (work_item_id.value,)).fetchone()
        if row is None:
            raise KeyError(work_item_id.value)
        return _from_dict(json.loads(row[0]))

    def claim_runnable(self) -> list[WorkItem]:
        q = ("SELECT data FROM work_items WHERE state NOT IN (?,?,?)")
        with self._conn() as c:
            rows = c.execute(q, _TERMINAL_OR_WAIT).fetchall()
        return [_from_dict(json.loads(r[0])) for r in rows]

# ---------- 序列化（领域 ↔ dict），核心不感知 ----------

def _to_dict(wi: WorkItem) -> dict:
    return {
        "id": wi.id.value,
        "repo_ref": wi.repo_ref.name,
        "requirement": {
            "goal": wi.requirement.goal, "target_repo": wi.requirement.target_repo,
            "acceptance_hints": list(wi.requirement.acceptance_hints),
            "raw_text": wi.requirement.raw_text,
        },
        "autonomy_dial": [[t.name, r, g.name] for (t, r, g) in wi.autonomy_dial.auto_gates],
        "type": wi.type.name if wi.type else None,
        "state": wi.state.name,
        "artifact_versions": {k: [_artifact_to_dict(a) for a in versions]
                              for k, versions in wi.artifact_versions.items()},
        "history": [[h.from_state.name, h.to_state.name, h.reason, h.at.isoformat()]
                    for h in wi.history],
        "retry_ledger": list(wi.retry_ledger.counts),
        "cost": wi.cost.tokens,
        "pending_gate": wi.pending_gate.name if wi.pending_gate else None,
        "created_at": wi.created_at.isoformat() if wi.created_at else None,
        "updated_at": wi.updated_at.isoformat() if wi.updated_at else None,
    }

def _from_dict(d: dict) -> WorkItem:
    wi = WorkItem(
        id=WorkItemId(d["id"]),
        repo_ref=RepoRef(d["repo_ref"]),
        requirement=Requirement(d["requirement"]["goal"], d["requirement"]["target_repo"],
                                tuple(d["requirement"]["acceptance_hints"]),
                                d["requirement"]["raw_text"]),
        autonomy_dial=AutonomyDial(frozenset(
            (TaskType[t], r, GatePoint[g]) for (t, r, g) in d["autonomy_dial"])),
        type=TaskType[d["type"]] if d["type"] else None,
        state=WorkflowState[d["state"]],
        artifact_versions={k: [_artifact_from_dict(a) for a in versions]
                           for k, versions in d["artifact_versions"].items()},
        history=[StateTransition(WorkflowState[a], WorkflowState[b], reason,
                                 datetime.fromisoformat(at)) for (a, b, reason, at) in d["history"]],
        retry_ledger=RetryLedger(frozenset(tuple(x) for x in d["retry_ledger"])),
        cost=Cost(d["cost"]),
        pending_gate=GatePoint[d["pending_gate"]] if d["pending_gate"] else None,
        created_at=datetime.fromisoformat(d["created_at"]) if d["created_at"] else None,
        updated_at=datetime.fromisoformat(d["updated_at"]) if d["updated_at"] else None,
    )
    return wi

def _artifact_to_dict(a: object) -> dict:
    t = type(a).__name__
    if isinstance(a, TriageArtifact):
        return {"__t": t, "level": a.level.name, "confidence": a.confidence,
                "workspace_mode": a.workspace_mode.name}
    if isinstance(a, ContextArtifact):
        return {"__t": t, "worktree_path": a.worktree_path, "branch": a.branch,
                "relevant_files": list(a.relevant_files), "summary": a.summary}
    if isinstance(a, DesignArtifact):
        return {"__t": t, "change_summary": a.change_summary, "target_files": list(a.target_files)}
    if isinstance(a, ReviewArtifact):
        return {"__t": t, "approved": a.approved, "comments": list(a.comments)}
    if isinstance(a, ImplArtifact):
        return {"__t": t, "diff": a.diff, "test_passed": a.test_passed, "summary": a.summary}
    if isinstance(a, AcceptanceArtifact):
        return {"__t": t, "criteria": list(a.criteria)}
    if isinstance(a, VerificationArtifact):
        return {"__t": t, "passed": a.verdict.passed, "reasons": list(a.verdict.reasons),
                "details": list(a.details)}
    if isinstance(a, DeliveryArtifact):
        return {"__t": t, "mr_url": a.mr_url, "branch": a.branch}
    raise TypeError(f"unknown artifact type {t}")

def _artifact_from_dict(d: dict) -> object:
    t = d["__t"]
    if t == "TriageArtifact":
        return TriageArtifact(TaskType[d["level"]], d["confidence"], WorkspaceMode[d["workspace_mode"]])
    if t == "ContextArtifact":
        return ContextArtifact(d["worktree_path"], d["branch"], tuple(d["relevant_files"]), d["summary"])
    if t == "DesignArtifact":
        return DesignArtifact(d["change_summary"], tuple(d["target_files"]))
    if t == "ReviewArtifact":
        return ReviewArtifact(d["approved"], tuple(d["comments"]))
    if t == "ImplArtifact":
        return ImplArtifact(d["diff"], d["test_passed"], d["summary"])
    if t == "AcceptanceArtifact":
        return AcceptanceArtifact(tuple(d["criteria"]))
    if t == "VerificationArtifact":
        return VerificationArtifact(Verdict(d["passed"], tuple(d["reasons"])), tuple(d["details"]))
    if t == "DeliveryArtifact":
        return DeliveryArtifact(d["mr_url"], d["branch"])
    raise TypeError(f"unknown artifact type {t}")
