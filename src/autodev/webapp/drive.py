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

from autodev.domain.enums import WorkflowState as S
from autodev.domain.work_item import WorkItem

# 生产：平台已有真实适配器的阶段。新增真实适配器时改这里，
# 由 tests/webapp/test_demo_app.py 的防漂移守卫锁死。
IMPLEMENTED_STAGES: frozenset[S] = frozenset({S.INTAKE, S.TRIAGE, S.CONTEXT, S.DESIGN})

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
