# tests/webapp/test_drive.py
from __future__ import annotations

from datetime import datetime

import pytest

from autodev.domain.enums import GatePoint
from autodev.domain.enums import WorkflowState as S
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem
from autodev.webapp.drive import IMPLEMENTED_STAGES, DriveStop, classify

NOW = datetime(2026, 7, 30, 9, 0, 0)

# goal 必须是完整英文短句 + 非空 acceptance_hints：FakeTriage 的启发式对短/未识别目标
# 扣置信分，置信 <0.5 会触发 AutonomyPolicy 规则 1 强制人审（与 autonomy_enabled 无关），
# 那样自动挡用例就验不到"连续跑完 DESIGN"。短中文目标"加限流"实测置信 0.45——
# 详见 tests/webapp/test_service.py:177 已记录过的同一个坑。
_GOAL = "add rate limiting for the api gateway"
_REQUIREMENT = Requirement(
    _GOAL, "demo", ("no regression in throughput",), f"{_GOAL} to protect it from abuse"
)

# 只走合法转移（与 tests/webapp/test_views.py 的 _work_item 同风格）。直接赋值 wi.state
# 会绕过状态机不变式，且留下空 history——后者会让 stage_views 的 passed_through 失真。
_PATH: dict[S, tuple[S, ...]] = {
    S.INTAKE: (),
    S.TRIAGE: (S.TRIAGE,),
    S.CONTEXT: (S.TRIAGE, S.CONTEXT),
    S.DESIGN: (S.TRIAGE, S.CONTEXT, S.DESIGN),
    S.REVIEW: (S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW),
    S.DONE: (S.TRIAGE, S.CONTEXT, S.DONE),  # CONTEXT→DONE 是"仅收集完成"的合法边
    S.FAILED: (S.TRIAGE, S.FAILED),
}


def _wi(state: S, *, autonomy: bool) -> WorkItem:
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("demo"),
        _REQUIREMENT,
        AutonomyDial.all_human(),
        NOW,
        autonomy_enabled=autonomy,
    )
    if state is S.WAIT_HUMAN:
        for s in (S.TRIAGE, S.CONTEXT):
            wi.transition_to(s, "stage ok", NOW)
        wi.suspend(GatePoint.CONTEXT_GATE, "context", NOW)
        return wi
    for s in _PATH[state]:
        wi.transition_to(s, "stage ok", NOW)
    return wi


@pytest.mark.parametrize(
    ("state", "autonomy", "expected"),
    [
        # 终态：与模式无关
        (S.DONE, True, DriveStop.TERMINAL),
        (S.DONE, False, DriveStop.TERMINAL),
        (S.FAILED, False, DriveStop.TERMINAL),
        # 门禁挂起：优先于模式判断
        (S.WAIT_HUMAN, True, DriveStop.WAIT_HUMAN),
        (S.WAIT_HUMAN, False, DriveStop.WAIT_HUMAN),
        # 平台还做不了：优先于手动挡判断
        (S.REVIEW, True, DriveStop.NOT_IMPLEMENTED),
        (S.REVIEW, False, DriveStop.NOT_IMPLEMENTED),
        # 自动挡且能力内 → 可继续推进
        (S.INTAKE, True, None),
        (S.CONTEXT, True, None),
        (S.DESIGN, True, None),
        # 手动挡：收集段照旧连续跑
        (S.INTAKE, False, None),
        (S.TRIAGE, False, None),
        (S.CONTEXT, False, None),
        # 手动挡：离开收集段即等人点
        (S.DESIGN, False, DriveStop.MANUAL_HOLD),
    ],
)
def test_classify_table(state: S, autonomy: bool, expected: DriveStop | None) -> None:
    assert classify(_wi(state, autonomy=autonomy), IMPLEMENTED_STAGES) == expected


def test_wait_human_wins_over_not_implemented() -> None:
    """挂在门上的工作项：WAIT_HUMAN 本身不在能力集合内，但应报 WAIT_HUMAN 而非
    NOT_IMPLEMENTED——判定顺序即优先级，须走 /decide 而不是「推进」。"""
    wi = _wi(S.WAIT_HUMAN, autonomy=False)

    assert wi.pending_gate is GatePoint.CONTEXT_GATE  # 由 _wi 的 suspend legitimately 建立
    assert classify(wi, IMPLEMENTED_STAGES) is DriveStop.WAIT_HUMAN
