# src/autodev/webapp/drive.py
"""驱动层：阶段能力单一真源 + 停因分类 + 两个驱动入口（自动 / 单步）。

「这个组合根下平台能执行哪些阶段」这个事实**只在本模块定义一次**，由三个消费者共用：
  1. 自动驱动的推进边界（本模块 `auto_drive`）
  2. 视图投影的「待建设」标记（`views.py`）
  3. 「推进」按钮可用性（`views.py` 投影的 next_action）

历史教训：该事实曾在 service 与 views 各存一份并漂移——DESIGN 已实现且已进驱动集合，
UI 却仍标「待建设」。收敛为一处后，驱动边界扩容的同时，搁浅工作项的按钮自动变亮。
"""

from __future__ import annotations

from enum import Enum, auto

from autodev.application.engine import Engine
from autodev.domain.enums import WorkflowState as S
from autodev.domain.errors import InvariantError
from autodev.domain.ids import WorkItemId
from autodev.domain.ports import WorkItemRepository
from autodev.domain.work_item import WorkItem

# 生产：平台已有真实适配器的阶段。新增真实适配器时改这里，
# 由 tests/webapp/test_demo_app.py 的防漂移守卫锁死。
IMPLEMENTED_STAGES: frozenset[S] = frozenset({S.INTAKE, S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW})

# 演示组合根：下游为确定性演示适配器，全生命周期可跑。
ALL_STAGES: frozenset[S] = frozenset(
    {
        S.INTAKE,
        S.TRIAGE,
        S.CONTEXT,
        S.DESIGN,
        S.REVIEW,
        S.IMPL,
        S.ACCEPT,
        S.VERIFY,
        S.SUBMIT_MR,
    }
)

# 只读收集段：手动挡下这几个阶段仍连续自动跑，保留「建完工作项即可见分诊与简报」的体验。
COLLECT_STAGES: frozenset[S] = frozenset({S.INTAKE, S.TRIAGE, S.CONTEXT})


class DriveStop(Enum):
    """工作项为何停下。四个成员对应前端四种交互形态（见 views.py 的 next_action）。"""

    TERMINAL = auto()  # DONE / FAILED
    WAIT_HUMAN = auto()  # 门禁挂起，须走 /decide
    NOT_IMPLEMENTED = auto()  # 平台尚无该阶段实现
    MANUAL_HOLD = auto()  # 手动挡，等人点「推进」


def classify(wi: WorkItem, implemented: frozenset[S]) -> DriveStop | None:
    """判定停因；返回 None 表示"可继续自动推进"。纯函数，无副作用。

    停因是**推导**而非持久化的：输入只有持久化字段（state / autonomy_enabled）与
    组合根常量（implemented），因此进程重启后结果一致。判定顺序即优先级——
    终态 > 门禁 > 能力 > 节奏。
    """
    if wi.state in (S.DONE, S.FAILED):
        return DriveStop.TERMINAL
    if wi.state is S.WAIT_HUMAN:
        return DriveStop.WAIT_HUMAN
    if wi.state not in implemented:
        return DriveStop.NOT_IMPLEMENTED
    if not wi.autonomy_enabled and wi.state not in COLLECT_STAGES:
        return DriveStop.MANUAL_HOLD
    return None


def auto_drive(
    repo: WorkItemRepository,
    engine: Engine,
    work_item_id: WorkItemId,
    implemented: frozenset[S] = IMPLEMENTED_STAGES,
) -> DriveStop | None:
    """自动驱动循环：无停因就推进，一有停因立即停并返回它。

    取代原 `_bounded_drive`。相对它的关键改进是**返回停因**——原实现对"合法地停"
    与"搁浅"都是同一个静默 return，这正是搁浅工作项没有任何痕迹与入口的根源。
    工作项不存在（已删除）时返回 None。
    """
    while True:
        try:
            wi = repo.get(work_item_id)
        except KeyError:
            return None
        stop = classify(wi, implemented)
        if stop is not None:
            return stop
        engine.advance(wi)


def ensure_advanceable(wi: WorkItem, implemented: frozenset[S]) -> None:
    """人工推进的准入校验：不合法就抛 `InvariantError`（路由映射 409）。

    无视 `MANUAL_HOLD`——手动挡下"等人点"正是「推进」存在的理由，人点了就是授权。
    其余停因（终态 / 门禁 / 未建设）一律拒绝；绝不静默无操作（静默正是原缺陷的形态）。

    服务层与 `step` 共用本函数：前者在 HTTP 请求内同步校验以立刻回 409，后者在后台
    线程真正推进前**再校验一次**（期间状态可能已变）。两处调用是有意的纵深防御，
    但判定规则只有这一处定义。
    """
    stop = classify(wi, implemented)
    if stop is not None and stop is not DriveStop.MANUAL_HOLD:
        raise InvariantError(f"cannot advance work item stopped by {stop.name}")


def step(
    repo: WorkItemRepository,
    engine: Engine,
    work_item_id: WorkItemId,
    implemented: frozenset[S] = IMPLEMENTED_STAGES,
) -> DriveStop | None:
    """人工单步推进一个阶段，返回推进后的停因。"""
    wi = repo.get(work_item_id)
    ensure_advanceable(wi, implemented)
    engine.advance(wi)
    return classify(repo.get(work_item_id), implemented)
