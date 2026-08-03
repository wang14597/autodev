# src/autodev/webapp/views.py
"""WorkItem → 前端 DTO 投影。避免把领域对象直接序列化给前端。"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from autodev.domain.artifacts import (
    ContextArtifact,
    DesignArtifact,
    ReviewArtifact,
    TriageArtifact,
)
from autodev.domain.enums import WorkflowState as S
from autodev.domain.project import Project
from autodev.domain.work_item import WorkItem
from autodev.webapp.drive import IMPLEMENTED_STAGES, DriveStop, classify

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

# 停因 → 前端交互形态。None（可继续推进）与 MANUAL_HOLD 都给「推进」按钮：
# 前者是搁浅项（历史数据/驱动进程中断），后者是手动挡正常等待，二者都需要人点一下。
_NEXT_ACTION: dict[DriveStop | None, str] = {
    None: "advance",
    DriveStop.MANUAL_HOLD: "advance",
    DriveStop.WAIT_HUMAN: "decide",
    DriveStop.NOT_IMPLEMENTED: "blocked",
    DriveStop.TERMINAL: "none",
}


def stage_views(
    wi: WorkItem, implemented: frozenset[S] = IMPLEMENTED_STAGES
) -> list[dict[str, str]]:
    """投影生命周期主链。「待建设」由传入的能力集合判定——不在此处另存一份清单。"""
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
        elif stage not in implemented and stage is not S.DONE:
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
        "autonomy_enabled": wi.autonomy_enabled,
        "created_at": wi.created_at.isoformat() if wi.created_at else None,
        "updated_at": wi.updated_at.isoformat() if wi.updated_at else None,
    }


def view_detail(
    wi: WorkItem,
    read_text: Callable[[str], str],
    implemented: frozenset[S] = IMPLEMENTED_STAGES,
) -> dict[str, object]:
    context: dict[str, str] | None = None
    if "context" in wi.artifacts:
        artifact = cast(ContextArtifact, wi.artifacts["context"])
        try:
            markdown = read_text(artifact.context_file)
        except OSError:
            markdown = ""
        context = {"markdown": markdown, "context_file": artifact.context_file}

    design: dict[str, str] | None = None
    if "design" in wi.artifacts:
        d_art = cast(DesignArtifact, wi.artifacts["design"])
        try:
            d_md = read_text(d_art.design_file)
        except OSError:
            d_md = ""
        design = {"markdown": d_md, "design_file": d_art.design_file}

    review: dict[str, object] | None = None
    if "review" in wi.artifacts:
        r_art = cast(ReviewArtifact, wi.artifacts["review"])
        try:
            r_md = read_text(r_art.final_plan_file) if r_art.final_plan_file else ""
        except OSError:
            r_md = ""
        review = {
            "markdown": r_md,
            "final_plan_file": r_art.final_plan_file,
            "approved": r_art.approved,
            "comments": list(r_art.comments),
        }

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
            "intent": t.intent.name,
        }

    detail: dict[str, object] = dict(view_summary(wi))
    detail["stages"] = stage_views(wi, implemented)
    detail["context"] = context
    detail["design"] = design
    detail["review"] = review
    detail["failure"] = failure
    detail["triage"] = triage
    detail["pending_gate"] = wi.pending_gate.name if wi.pending_gate else None
    # 仅收集完成：到 DONE 但无 delivery 产物（未走 DESIGN..SUBMIT_MR）。
    detail["collect_only"] = wi.state is S.DONE and "delivery" not in wi.artifacts
    # 单一投影字段驱动前端四态，前端不重复判断停因逻辑。
    stop = classify(wi, implemented)
    detail["next_action"] = _NEXT_ACTION[stop]
    # 即将执行（或被阻塞）的阶段名——引擎推进的是**当前状态**对应的处理器。
    # 终态没有"下一阶段"。注意 S.DONE 在 _LABELS 里（流水线要显示「完成」这一行），
    # 但它不是一个待执行阶段，所以不能直接 _LABELS.get(wi.state)。
    detail["next_stage"] = None if stop is DriveStop.TERMINAL else _LABELS.get(wi.state)
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
