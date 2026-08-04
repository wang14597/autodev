# tests/webapp/test_views.py
from __future__ import annotations

from datetime import datetime

from autodev.domain.artifacts import ContextArtifact
from autodev.domain.enums import GatePoint
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
    if state not in (S.INTAKE, S.TRIAGE, S.CONTEXT, S.WAIT_HUMAN, S.DONE):
        wi.transition_to(S.DESIGN, "stage ok", NOW)
    if state in (S.REVIEW, S.IMPL):
        wi.transition_to(S.REVIEW, "stage ok", NOW)
    if state is S.IMPL:
        wi.transition_to(S.IMPL, "stage ok", NOW)
    if state is S.WAIT_HUMAN:
        wi.suspend(GatePoint.CONTEXT_GATE, "context", NOW)
    if state is S.DONE:
        wi.transition_to(S.DONE, "collect only", NOW)
    if state is S.FAILED and wi.state is not S.FAILED:
        wi.transition_to(S.FAILED, "failed: boom", NOW)
    return wi


def _status_by_key(views: list[dict[str, str]]) -> dict[str, str]:
    return {v["key"]: v["status"] for v in views}


def test_stage_views_context_state_marks_done_current_pending_blocked():
    wi = _work_item(S.CONTEXT)
    statuses = _status_by_key(stage_views(wi))

    assert statuses["INTAKE"] == "done"
    assert statuses["TRIAGE"] == "done"
    assert statuses["CONTEXT"] == "current"
    assert statuses["DESIGN"] == "pending"  # DESIGN 已实现，不再是 "blocked"
    assert statuses["REVIEW"] == "pending"  # REVIEW 已实现（Task 4），不再是 "blocked"
    for blocked_key in ("IMPL", "ACCEPT", "VERIFY", "SUBMIT_MR"):
        assert statuses[blocked_key] == "blocked"
    assert statuses["DONE"] == "pending"  # DONE 是终点标记，永不属于能力集合，显式排除


def test_stage_views_intake_state_marks_rest_pending_or_blocked():
    wi = _work_item(S.INTAKE)
    statuses = _status_by_key(stage_views(wi))

    assert statuses["INTAKE"] == "current"
    assert statuses["TRIAGE"] == "pending"
    assert statuses["CONTEXT"] == "pending"
    assert statuses["DESIGN"] == "pending"  # DESIGN 已实现，不再是 "blocked"
    assert statuses["REVIEW"] == "pending"  # REVIEW 已实现（Task 4），不再是 "blocked"
    assert statuses["IMPL"] == "blocked"


def test_stage_views_design_state_marks_earlier_stages_done():
    wi = _work_item(S.DESIGN)
    statuses = _status_by_key(stage_views(wi))

    assert statuses["INTAKE"] == "done"
    assert statuses["TRIAGE"] == "done"
    assert statuses["CONTEXT"] == "done"
    assert statuses["DESIGN"] == "current"
    assert statuses["REVIEW"] == "pending"  # REVIEW 已实现（Task 4），不再是 "blocked"
    assert statuses["IMPL"] == "blocked"


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


# --- 切片 2.1：view_detail 暴露 triage 字段 ---


def test_view_detail_projects_triage_when_present() -> None:
    from autodev.domain.artifacts import TriageArtifact
    from autodev.domain.enums import RiskLevel, TaskType, WorkspaceMode

    wi = _work_item(S.CONTEXT)
    wi.add_artifact(
        "triage",
        TriageArtifact(
            TaskType.SMALL_CHANGE, 0.7, WorkspaceMode.REUSE, RiskLevel.HIGH, ("keyword:delete",)
        ),
    )
    detail = view_detail(wi, lambda _p: "")
    triage = detail["triage"]
    assert triage is not None
    assert triage["risk"] == "HIGH"
    assert triage["level"] == "SMALL_CHANGE"
    assert triage["confidence"] == 0.7
    assert triage["signals"] == ["keyword:delete"]


def test_view_detail_triage_none_when_absent() -> None:
    wi = _work_item(S.INTAKE)
    assert view_detail(wi, lambda _p: "")["triage"] is None


# --- Task 4：view_detail 暴露 design 字段（镜像 context）---


def test_view_detail_projects_design_brief():
    from autodev.domain.artifacts import DesignArtifact

    wi = _work_item(S.DESIGN)
    wi.add_artifact("design", DesignArtifact(design_file="/x/design.md"))

    detail = view_detail(wi, read_text=lambda p: "## 方案概述\n改 app.py\n")

    assert detail["design"] == {
        "markdown": "## 方案概述\n改 app.py\n",
        "design_file": "/x/design.md",
    }


def test_view_detail_design_none_when_absent():
    wi = _work_item(S.CONTEXT)

    detail = view_detail(wi, read_text=lambda p: "")

    assert detail["design"] is None


# --- Task 4：删除手抄的 _UNIMPLEMENTED，改用 drive.IMPLEMENTED_STAGES + next_action 投影 ---


def test_design_no_longer_marked_blocked() -> None:
    """回归：DESIGN/REVIEW 已实现并进入能力集合，停在 CONTEXT 的工作项不应再把
    「方案」「评审」标为待建设。

    这正是本次发现的线上 bug——views 手抄了一份"未实现阶段"清单并漂移。
    """
    wi = _work_item(S.CONTEXT)
    by_key = {v["key"]: v for v in stage_views(wi)}

    assert by_key["DESIGN"]["status"] == "pending"  # 曾错为 "blocked"
    assert by_key["REVIEW"]["status"] == "pending"  # REVIEW 已实现（Task 4），曾错为 "blocked"
    assert by_key["IMPL"]["status"] == "blocked"  # IMPL 确实还没建


def test_stage_views_blocked_follows_injected_capability() -> None:
    """「待建设」由注入的能力集合决定，而非模块内硬编码——演示组合根因此不再误标。"""
    from autodev.webapp.drive import ALL_STAGES

    wi = _work_item(S.CONTEXT)
    statuses = {v["key"]: v["status"] for v in stage_views(wi, ALL_STAGES)}

    assert "blocked" not in statuses.values()


def test_next_action_advance_for_stranded_item() -> None:
    """搁浅在 DESIGN 的自动挡工作项 → 可推进，前端该给「推进」按钮。"""
    wi = _work_item(S.DESIGN)
    wi.autonomy_enabled = True
    detail = view_detail(wi, lambda _p: "")

    assert detail["next_action"] == "advance"
    assert detail["next_stage"] == "方案"


def test_next_action_advance_for_manual_hold() -> None:
    wi = _work_item(S.DESIGN)
    wi.autonomy_enabled = False
    assert view_detail(wi, lambda _p: "")["next_action"] == "advance"


def test_next_action_advance_during_collect_stage_is_intentional() -> None:
    """spec §5.2：手动挡工作项短暂停在收集段时也给「推进」按钮——这是刻意的。

    若改成"收集段不给按钮"，驱动进程在收集途中被杀的工作项就会永久搁浅、没有任何
    恢复入口，正是本次要消灭的缺陷形态。保留按钮＝守住"可推进 ⇔ 有入口"这条不变式。
    """
    wi = _work_item(S.TRIAGE)
    wi.autonomy_enabled = False
    assert view_detail(wi, lambda _p: "")["next_action"] == "advance"


def test_next_action_blocked_for_unimplemented_stage() -> None:
    wi = _work_item(S.IMPL)  # IMPL 是当前能力边界（REVIEW 已实现，见 Task 4）
    wi.autonomy_enabled = True
    detail = view_detail(wi, lambda _p: "")

    assert detail["next_action"] == "blocked"
    assert detail["next_stage"] == "开发"


def test_next_action_decide_when_waiting_human() -> None:
    wi = _work_item(S.WAIT_HUMAN)
    assert view_detail(wi, lambda _p: "")["next_action"] == "decide"


def test_next_action_none_when_terminal() -> None:
    wi = _work_item(S.DONE)
    assert view_detail(wi, lambda _p: "")["next_action"] == "none"


# --- Fix round 1: next_stage 在终态必须是 None（S.DONE 在 _LABELS 里但不是待执行阶段）---


def test_next_stage_none_when_done() -> None:
    """DONE 是终态,虽然 _LABELS 里有「完成」这一行(供 stage_views 显示),
    但 next_stage 不能投影出它——没有"下一阶段"可跑了。"""
    wi = _work_item(S.DONE)
    detail = view_detail(wi, lambda _p: "")

    assert detail["next_action"] == "none"
    assert detail["next_stage"] is None


def test_next_stage_none_when_failed() -> None:
    wi = _work_item(S.FAILED)
    detail = view_detail(wi, lambda _p: "")

    assert detail["next_action"] == "none"
    assert detail["next_stage"] is None


def test_next_stage_still_projects_label_for_live_stage() -> None:
    """非终态的正常路径回归：next_stage 仍应给出当前阶段的中文标签。"""
    wi = _work_item(S.DESIGN)
    detail = view_detail(wi, lambda _p: "")

    assert detail["next_stage"] == "方案"


# --- Task 5：view_detail 暴露 review 字段（final_plan_file + comments）---


def test_view_detail_projects_review_final_plan():
    from autodev.domain.artifacts import ReviewArtifact

    wi = _work_item(S.REVIEW)
    wi.add_artifact(
        "review",
        ReviewArtifact(True, ("- suggestion: 补个测试",), final_plan_file="/x/final-plan-r1.md"),
    )
    detail = view_detail(wi, lambda p: "## 方案概述\n\n最终方案")
    review = detail["review"]
    assert review["final_plan_file"] == "/x/final-plan-r1.md"
    assert review["approved"] is True
    assert review["comments"] == ["- suggestion: 补个测试"]
    assert "最终方案" in review["markdown"]


def test_view_detail_review_markdown_empty_when_file_unreadable():
    from autodev.domain.artifacts import ReviewArtifact

    def boom(path: str) -> str:
        raise OSError("EPERM")

    wi = _work_item(S.REVIEW)
    wi.add_artifact("review", ReviewArtifact(True, (), final_plan_file="/x/f.md"))
    assert view_detail(wi, boom)["review"]["markdown"] == ""


def test_view_detail_review_is_none_without_artifact():
    assert view_detail(_work_item(S.CONTEXT), lambda p: "")["review"] is None
