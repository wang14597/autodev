# tests/webapp/test_drive.py
from __future__ import annotations

from datetime import datetime

import pytest

from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.domain.enums import GatePoint, TaskType
from autodev.domain.enums import WorkflowState as S
from autodev.domain.errors import InvariantError
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem
from autodev.webapp.drive import (
    ALL_STAGES,
    IMPLEMENTED_STAGES,
    DriveStop,
    auto_drive,
    classify,
    step,
)
from tests.fakes import build_engine_with_fakes

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
# 本次问题发生时的能力集合（DESIGN 尚未实现）。用它驱动可得到带 triage/context
# 产物的真实搁浅态，避免手工摆状态导致 handle_design 读不到 context 产物而 KeyError。
_OLD_CAPABILITY: frozenset[S] = frozenset({S.INTAKE, S.TRIAGE, S.CONTEXT})

_PATH: dict[S, tuple[S, ...]] = {
    S.INTAKE: (),
    S.TRIAGE: (S.TRIAGE,),
    S.CONTEXT: (S.TRIAGE, S.CONTEXT),
    S.DESIGN: (S.TRIAGE, S.CONTEXT, S.DESIGN),
    S.REVIEW: (S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW),
    S.IMPL: (S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW, S.IMPL),
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
        (S.IMPL, True, DriveStop.NOT_IMPLEMENTED),
        (S.IMPL, False, DriveStop.NOT_IMPLEMENTED),
        # 自动挡且能力内 → 可继续推进
        (S.INTAKE, True, None),
        (S.CONTEXT, True, None),
        (S.DESIGN, True, None),
        (S.REVIEW, True, None),
        # 手动挡：收集段照旧连续跑
        (S.INTAKE, False, None),
        (S.TRIAGE, False, None),
        (S.CONTEXT, False, None),
        # 手动挡：离开收集段即等人点
        (S.DESIGN, False, DriveStop.MANUAL_HOLD),
        (S.REVIEW, False, DriveStop.MANUAL_HOLD),
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


def test_auto_drive_runs_continuously_to_capability_edge() -> None:
    """自动挡：连续跑过 DESIGN/REVIEW，止于 REVIEW_GATE 人审（REVIEW 已实现，
    不再是能力边界；`_wi` 用的 `AutonomyDial.all_human()` 使该门总要人审）。"""
    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)
    wi = _wi(S.INTAKE, autonomy=True)
    repo.save(wi)

    stop = auto_drive(repo, engine, wi.id, IMPLEMENTED_STAGES)

    assert stop is DriveStop.WAIT_HUMAN
    got = repo.get(wi.id)
    assert got.state is S.WAIT_HUMAN and got.pending_gate is GatePoint.REVIEW_GATE
    assert "design" in got.artifacts
    assert "review" in got.artifacts


def test_manual_mode_auto_drive_stops_after_collect_stages() -> None:
    """手动挡：收集段连续跑完后停住，绝不自行进入 DESIGN。"""
    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)
    wi = _wi(S.INTAKE, autonomy=False)
    repo.save(wi)

    stop = auto_drive(repo, engine, wi.id, IMPLEMENTED_STAGES)

    assert stop is DriveStop.WAIT_HUMAN  # CONTEXT_GATE 挂起（既有行为）
    assert "design" not in repo.get(wi.id).artifacts


def test_step_advances_exactly_one_stage() -> None:
    """单步：手动挡停在 DESIGN 时，step 跑完 DESIGN 就停，不继续。

    注意工作项必须**驱动**到 DESIGN 而不是手工摆到 DESIGN——`handle_design` 会读
    `work_item.artifacts["context"]`，手工构造的工作项没有该产物会直接 KeyError。
    这里用"当年的能力集合"（不含 DESIGN）驱动，天然得到带 triage/context 产物的搁浅态。
    """
    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)
    wi = _wi(S.INTAKE, autonomy=True)
    repo.save(wi)
    auto_drive(repo, engine, wi.id, _OLD_CAPABILITY)

    # 切到手动挡：停因应为"等人点"
    parked = repo.get(wi.id)
    assert parked.state is S.DESIGN
    parked.autonomy_enabled = False
    repo.save(parked)
    assert classify(repo.get(wi.id), IMPLEMENTED_STAGES) is DriveStop.MANUAL_HOLD

    stop = step(repo, engine, wi.id, IMPLEMENTED_STAGES)

    assert repo.get(wi.id).state is S.REVIEW  # 只走了一步
    assert stop is DriveStop.MANUAL_HOLD  # REVIEW 已实现；手动挡下等人再点一次


def test_step_ignores_manual_hold_but_refuses_other_stops() -> None:
    """step 无视 MANUAL_HOLD（人已授权），但拒绝终态/门禁/未实现。

    这三条断言是铁律 5（人审是一等状态）在驱动层的具体化：`waiting`
    (WAIT_HUMAN) 一条尤其关键——若有人把 `ensure_advanceable` 的豁免从
    "仅 MANUAL_HOLD" 悄悄放宽到也豁免 WAIT_HUMAN，整套测试仍会全绿，但
    「推进」就能悄悄跨过一个开着的风险门禁执行下一阶段。
    """
    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)

    done = _wi(S.DONE, autonomy=False)
    repo.save(done)
    with pytest.raises(InvariantError):
        step(repo, engine, done.id, IMPLEMENTED_STAGES)

    blocked = _wi(S.IMPL, autonomy=True)  # IMPL 是当前能力边界（REVIEW 已实现）
    repo.save(blocked)
    with pytest.raises(InvariantError):
        step(repo, engine, blocked.id, IMPLEMENTED_STAGES)

    waiting = _wi(S.WAIT_HUMAN, autonomy=False)
    repo.save(waiting)
    with pytest.raises(InvariantError):
        step(repo, engine, waiting.id, IMPLEMENTED_STAGES)


def test_step_recovers_stranded_work_item() -> None:
    """回归本次问题现场（voice-agent 那个停在「方案」三天不动的工作项）。

    工作项在"DESIGN 尚未实现"的年代被驱动到 DESIGN 就搁浅了：可推进、却没有任何
    东西会再触发它。如今 DESIGN 已进能力集合——单步推进应能直接救活，零数据迁移。
    """
    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)
    wi = _wi(S.INTAKE, autonomy=True)
    repo.save(wi)

    # 当年：能力集合不含 DESIGN → 驱动跑到 DESIGN 就静默停住（搁浅）
    assert auto_drive(repo, engine, wi.id, _OLD_CAPABILITY) is DriveStop.NOT_IMPLEMENTED
    assert repo.get(wi.id).state is S.DESIGN
    assert "design" not in repo.get(wi.id).artifacts

    # 如今：DESIGN 已进能力集合 → classify 判定可推进，单步即救活
    assert classify(repo.get(wi.id), IMPLEMENTED_STAGES) is None
    step(repo, engine, wi.id, IMPLEMENTED_STAGES)

    assert "design" in repo.get(wi.id).artifacts


def test_step_stops_exactly_at_review_even_though_classify_still_says_continue() -> None:
    """判别性回归：唯一能证伪「step 其实是循环、只是把 MANUAL_HOLD 当继续」的用例。

    `test_step_advances_exactly_one_stage` / `test_step_recovers_stranded_work_item`
    都在 `IMPLEMENTED_STAGES` 下验证——但那里 REVIEW 本身不在能力集合内，落地 REVIEW
    后 classify 立刻判 NOT_IMPLEMENTED。一个错误实现「auto_drive 但把 MANUAL_HOLD
    当继续」在那两个用例下会被 NOT_IMPLEMENTED 挡住，产出与正确实现完全相同的可观测
    结果——测不出区别。

    这里改用 `ALL_STAGES`（REVIEW 在能力集合内）+ 下游端口用真正工作的假件
    （`build_engine_with_fakes(..., full_fakes=True)`，而非抛错桩）+ 自定义
    `AutonomyDial` 在 REVIEW_GATE 开放自动放行。落地 REVIEW 后 classify 仍判「可
    继续」（None，因为 REVIEW ∈ ALL_STAGES 且 autonomy_enabled=True）。于是：
    - 正确实现（`step` 只调用一次 `engine.advance`）必须恰好停在 REVIEW；
    - 错误实现（循环直到停因非 MANUAL_HOLD）会继续跑过 REVIEW_GATE 进入 IMPL 及之后。
    """
    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo, full_fakes=True)

    # 只放开 REVIEW_GATE；MERGE_GATE 仍需人审——不需要跑穿全生命周期，
    # 只需证明"多跑了至少一阶段"即可与正确实现区分。
    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "demo", GatePoint.REVIEW_GATE)}))
    wi = WorkItem.create(
        WorkItemId.new(), RepoRef("demo"), _REQUIREMENT, dial, NOW, autonomy_enabled=True
    )
    repo.save(wi)

    # 驱动到 DESIGN 但不跑 DESIGN 本身：复用 _OLD_CAPABILITY 的手法，得到带真实
    # triage/context 产物的工作项，避免手工摆状态导致 handle_design 读不到 context
    # 产物而 KeyError。
    auto_drive(repo, engine, wi.id, _OLD_CAPABILITY)
    parked = repo.get(wi.id)
    assert parked.state is S.DESIGN
    assert classify(parked, ALL_STAGES) is None  # 判别性前提：DESIGN 本身可继续

    stop = step(repo, engine, wi.id, ALL_STAGES)

    landed = repo.get(wi.id)
    assert landed.state is S.REVIEW  # 正确实现：只推进了 DESIGN 这一阶段
    assert landed.state not in (
        S.IMPL,
        S.ACCEPT,
        S.VERIFY,
        S.SUBMIT_MR,
        S.DONE,
        S.WAIT_HUMAN,
    )  # 错误实现会落在这些"更靠后"的状态之一，而非 REVIEW
    assert stop is None  # REVIEW ∈ ALL_STAGES 且 autonomy_enabled=True → 仍可继续
