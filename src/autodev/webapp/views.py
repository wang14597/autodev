# src/autodev/webapp/views.py
"""WorkItem → 前端 DTO 投影。避免把领域对象直接序列化给前端。"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from autodev.domain.artifacts import ContextArtifact, TriageArtifact
from autodev.domain.enums import WorkflowState as S
from autodev.domain.project import Project
from autodev.domain.work_item import WorkItem

# 线性主链: INTAKE..DONE。WAIT_HUMAN/FAILED 是覆盖态，不出现在这条链里。
_CHAIN: tuple[S, ...] = (
    S.INTAKE,
    S.TRIAGE,
    S.CONTEXT,
    S.DESIGN,
    S.REVIEW,
    S.IMPL,
    S.ACCEPT,
    S.VERIFY,
    S.SUBMIT_MR,
    S.DONE,
)

_LABELS: dict[S, str] = {
    S.INTAKE: "需求录入",
    S.TRIAGE: "分诊",
    S.CONTEXT: "上下文",
    S.DESIGN: "方案",
    S.REVIEW: "评审",
    S.IMPL: "开发",
    S.ACCEPT: "验收",
    S.VERIFY: "测试",
    S.SUBMIT_MR: "提交MR",
    S.DONE: "完成",
}

# CONTEXT 之后的阶段平台尚未实现，一律标记为 "待建设"。
_UNIMPLEMENTED: frozenset[S] = frozenset(
    {S.DESIGN, S.REVIEW, S.IMPL, S.ACCEPT, S.VERIFY, S.SUBMIT_MR, S.DONE}
)


def stage_views(wi: WorkItem) -> list[dict[str, str]]:
    passed_through: set[S] = set()
    for transition in wi.history:
        passed_through.add(transition.from_state)
        passed_through.add(transition.to_state)

    views: list[dict[str, str]] = []
    for stage in _CHAIN:
        if stage is wi.state:
            status = "current"
        elif stage in passed_through:
            status = "done"
        elif stage in _UNIMPLEMENTED:
            status = "blocked"
        else:
            status = "pending"
        views.append({"key": stage.name, "label": _LABELS[stage], "status": status})
    return views


def view_summary(wi: WorkItem) -> dict[str, object]:
    return {
        "id": wi.id.value,
        "goal": wi.requirement.goal,
        "repo": wi.repo_ref.name,
        "type": wi.type.name if wi.type is not None else None,
        "state": wi.state.name,
        "created_at": wi.created_at.isoformat() if wi.created_at else None,
        "updated_at": wi.updated_at.isoformat() if wi.updated_at else None,
    }


def view_detail(wi: WorkItem, read_text: Callable[[str], str]) -> dict[str, object]:
    context: dict[str, str] | None = None
    if "context" in wi.artifacts:
        artifact = cast(ContextArtifact, wi.artifacts["context"])
        try:
            markdown = read_text(artifact.context_file)
        except OSError:
            markdown = ""
        context = {"markdown": markdown, "context_file": artifact.context_file}

    failure: dict[str, str] | None = None
    if wi.state is S.FAILED:
        failure = {"reason": wi.history[-1].reason if wi.history else ""}

    triage: dict[str, object] | None = None
    if "triage" in wi.artifacts:
        t = cast(TriageArtifact, wi.artifacts["triage"])
        triage = {
            "level": t.level.name,
            "confidence": t.confidence,
            "risk": t.risk.name,
            "signals": list(t.signals),
        }

    detail: dict[str, object] = dict(view_summary(wi))
    detail["stages"] = stage_views(wi)
    detail["context"] = context
    detail["failure"] = failure
    detail["triage"] = triage
    return detail


def view_project(project: Project, workitem_count: int) -> dict[str, object]:
    return {
        "id": project.id.value,
        "name": project.name,
        "repo_source": project.repo_source,
        "branch": project.branch,
        "workitem_count": workitem_count,
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }


def view_project_detail(project: Project, workitems: list[WorkItem]) -> dict[str, object]:
    detail = view_project(project, workitem_count=len(workitems))
    detail["workitems"] = [view_summary(wi) for wi in workitems]
    return detail
