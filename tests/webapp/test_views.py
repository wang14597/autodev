# tests/webapp/test_views.py
from __future__ import annotations

from datetime import datetime

from autodev.domain.artifacts import ContextArtifact
from autodev.domain.enums import WorkflowState as S
from autodev.domain.ids import ProjectId, WorkItemId
from autodev.domain.project import Project
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem
from autodev.webapp.views import (
    stage_views,
    view_detail,
    view_project,
    view_project_detail,
    view_summary,
)

NOW = datetime(2026, 7, 22, 9, 0, 0)


def _work_item(state: S = S.INTAKE) -> WorkItem:
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("demo"),
        Requirement("加限流", "demo", (), "加限流"),
        AutonomyDial.all_human(),
        NOW,
    )
    if state is not S.INTAKE:
        wi.transition_to(S.TRIAGE, "stage ok", NOW)
    if state not in (S.INTAKE, S.TRIAGE):
        wi.transition_to(S.CONTEXT, "stage ok", NOW)
    if state not in (S.INTAKE, S.TRIAGE, S.CONTEXT):
        wi.transition_to(S.DESIGN, "stage ok", NOW)
    if state is S.FAILED and wi.state is not S.FAILED:
        wi.transition_to(S.FAILED, "failed: boom", NOW)
    return wi


def _status_by_key(views: list[dict[str, str]]) -> dict[str, str]:
    return {v["key"]: v["status"] for v in views}


def test_stage_views_context_state_marks_done_current_blocked():
    wi = _work_item(S.CONTEXT)
    statuses = _status_by_key(stage_views(wi))

    assert statuses["INTAKE"] == "done"
    assert statuses["TRIAGE"] == "done"
    assert statuses["CONTEXT"] == "current"
    for blocked_key in ("DESIGN", "REVIEW", "IMPL", "ACCEPT", "VERIFY", "SUBMIT_MR", "DONE"):
        assert statuses[blocked_key] == "blocked"


def test_stage_views_intake_state_marks_rest_pending_or_blocked():
    wi = _work_item(S.INTAKE)
    statuses = _status_by_key(stage_views(wi))

    assert statuses["INTAKE"] == "current"
    assert statuses["TRIAGE"] == "pending"
    assert statuses["CONTEXT"] == "pending"
    assert statuses["DESIGN"] == "blocked"


def test_stage_views_design_state_marks_earlier_stages_done():
    wi = _work_item(S.DESIGN)
    statuses = _status_by_key(stage_views(wi))

    assert statuses["INTAKE"] == "done"
    assert statuses["TRIAGE"] == "done"
    assert statuses["CONTEXT"] == "done"
    assert statuses["DESIGN"] == "current"
    assert statuses["REVIEW"] == "blocked"


def test_view_summary_fields():
    wi = _work_item(S.CONTEXT)
    summary = view_summary(wi)

    assert summary["id"] == wi.id.value
    assert summary["goal"] == "加限流"
    assert summary["repo"] == "demo"
    assert summary["type"] is None
    assert summary["state"] == "CONTEXT"
    assert summary["created_at"] == NOW.isoformat()
    assert summary["updated_at"] == NOW.isoformat()


def test_view_detail_returns_markdown_via_injected_read_text():
    wi = _work_item(S.CONTEXT)
    wi.add_artifact("context", ContextArtifact("/tmp/ws", "branch", "/tmp/ws/context.md"))

    calls: list[str] = []

    def read_text(path: str) -> str:
        calls.append(path)
        return "# 简报\n内容"

    detail = view_detail(wi, read_text)

    assert calls == ["/tmp/ws/context.md"]
    assert detail["context"] == {"markdown": "# 简报\n内容", "context_file": "/tmp/ws/context.md"}
    assert detail["failure"] is None
    assert isinstance(detail["stages"], list)


def test_view_detail_context_none_when_no_artifact():
    wi = _work_item(S.TRIAGE)

    detail = view_detail(wi, lambda path: "unused")

    assert detail["context"] is None


def test_view_detail_read_failure_yields_empty_markdown():
    wi = _work_item(S.CONTEXT)
    wi.add_artifact("context", ContextArtifact("/tmp/ws", "branch", "/missing/context.md"))

    def read_text(path: str) -> str:
        raise OSError("no such file")

    detail = view_detail(wi, read_text)

    assert detail["context"] == {"markdown": "", "context_file": "/missing/context.md"}


def test_view_detail_failure_reason_when_failed():
    wi = _work_item(S.FAILED)

    detail = view_detail(wi, lambda path: "unused")

    assert detail["failure"] == {"reason": "failed: boom"}
    assert detail["state"] == "FAILED"


def test_view_project_fields():
    project = Project.create(ProjectId("p1"), "demo", "worktree:/tmp/demo", "", NOW)
    project.mark_prepared("main", NOW)

    view = view_project(project, workitem_count=3)

    assert view == {
        "id": "p1",
        "name": "demo",
        "repo_source": "worktree:/tmp/demo",
        "branch": "main",
        "workitem_count": 3,
        "created_at": NOW.isoformat(),
    }


def test_view_project_created_at_none_when_missing():
    project = Project(id=ProjectId("p2"), name="demo", repo_source="url")

    view = view_project(project, workitem_count=0)

    assert view["created_at"] is None
    assert view["branch"] == ""


def test_view_project_detail_includes_workitem_summaries():
    project = Project.create(ProjectId("p1"), "demo", "worktree:/tmp/demo", "", NOW)
    project.mark_prepared("main", NOW)
    wi = _work_item(S.CONTEXT)

    detail = view_project_detail(project, [wi])

    assert detail["id"] == "p1"
    assert detail["workitem_count"] == 1
    assert detail["workitems"] == [view_summary(wi)]


def test_view_project_detail_empty_workitems():
    project = Project.create(ProjectId("p1"), "demo", "url", "", NOW)

    detail = view_project_detail(project, [])

    assert detail["workitem_count"] == 0
    assert detail["workitems"] == []
