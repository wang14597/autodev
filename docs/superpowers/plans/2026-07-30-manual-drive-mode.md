# 手动挡（单步推进）+ 阶段能力单一真源 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让任何"可推进但无人触发"的工作项都有一个人可点的入口，并把"平台能执行哪些阶段"收敛为单一真源，使驱动边界扩容后搁浅工作项自动解除。

**Architecture:** 新增 `webapp/drive.py` 承载三件事——阶段能力集合（唯一真源）、停因分类纯函数、两个驱动入口（自动循环 / 单步）。`autonomy_enabled` 泛化为节奏总开关（开=自动挡，关=手动挡）。视图层删除手抄的"未实现阶段"清单，改为消费同一集合，并投影单一字段 `next_action` 驱动前端四态。领域状态机与 `WAIT_HUMAN` / `GatePoint` 语义零改动，历史数据零迁移。

**Tech Stack:** Python 3.11+ / FastAPI / pytest；前端 Vite + React + TypeScript + TanStack Query + vitest。

## Global Constraints

- **铁律 1 核心域纯净**：DriveStop / `classify` / 能力集合 / `COLLECT_STAGES` 全部落在 `src/autodev/webapp/`，**禁止**放入 `src/autodev/domain/`，且 `domain/` 不得 import 它们。
- **铁律 5 人审是一等状态**：`WAIT_HUMAN` 与 `GatePoint` 的语义、`resume_target` 查表、三键面板**一律不改**。手动挡的"停"不进 `WAIT_HUMAN`，不获得拒绝语义。
- **铁律 7 失败收敛**：不新增失败路径，阶段异常沿用既有 `StageOutcome` / 重试 / 回退。
- **阶段耗时假设**：单个阶段可能跑数分钟（Claude Code 子进程）。因此**校验同步、执行异步**——HTTP 请求内只做合法性判定并立即返回，真正推进交 `Executor` 后台执行，前端靠轮询取新状态。这与既有 `decide_workitem` 的模式一致。
- **不做**：并发双击的后端强防护（乐观锁/领取锁）、阶段级细粒度配置、`AutonomyDial` 逐阶段决策。
- **测试命令**：`pytest -q`；lint/格式/类型 `ruff check . && ruff format --check . && mypy src`；前端 `cd frontend && npm run typecheck && npm run lint && npm run test`。
- **CHANGELOG 必需**：本计划改动 `src/**`，`CHANGELOG.md` 必须加条目（Task 7）。
- **文档一致性**：正文行内反引号不得引用 `src/**` 中不存在的符号；新符号只写在围栏代码块内。注意 `` `None` `` 也会被判伪造（匹配 CamelCase 规则）。

### 相对 spec 的一处细化（需评审确认）

Spec 第 3 节写"能力集合定义在 `service.py`，`views.py` 从它导入"。本计划改为**新建 `webapp/drive.py`**：`service.py` 已 345 行且含两个服务类，而能力集合 + 停因 + 驱动入口是一个内聚单元；更重要的是可避免 `views.py` → `service.py` 的反向耦合（视图不该依赖服务编排模块）。仍是**一处定义、三处消费**，完全满足 spec 的单一真源意图。

---

## File Structure

| 文件 | 责任 |
|------|------|
| **新建** `src/autodev/webapp/drive.py` | 阶段能力集合（唯一真源）、`COLLECT_STAGES`、停因枚举与 `classify`、`auto_drive` / `step` |
| **新建** `tests/webapp/test_drive.py` | `classify` 组合表 + 两个驱动入口行为 |
| 改 `src/autodev/webapp/service.py` | 删 `RUN`/`FULL_DRIVE`/`_bounded_drive`，改从 `drive.py` 导入；新增 `advance_workitem`；`decide` 按模式分流 |
| 改 `src/autodev/webapp/views.py` | 删 `_UNIMPLEMENTED`；`stage_views`/`view_detail` 接收能力集合；投影 `next_action` / `next_stage` |
| 改 `src/autodev/webapp/app.py` | `ConsoleService` 协议加 2 项；新增 `POST /api/workitems/{id}/advance`（409）；`view_detail` 传能力集合 |
| 改 `src/autodev/webapp/demo_config.py` | `FULL_DRIVE` → `ALL_STAGES`，参数改名 |
| 改 `tests/webapp/test_demo_app.py` | 扩既有安全守卫为**防漂移守卫** |
| 改 `tests/webapp/test_service.py` / `test_demo_service.py` / `test_views.py` | 跟随改名与新签名 |
| **新建** `frontend/src/components/AdvancePanel.tsx` + `.module.css` + `.test.tsx` | 按 `next_action` 渲染四态 |
| **新建** `frontend/src/hooks/useAdvanceWorkItem.ts` | 单步推进 mutation |
| 改 `frontend/src/api/types.ts` / `client.ts` | `next_action`/`next_stage` 类型 + `advanceWorkItem` |
| 改 `frontend/src/pages/WorkItemDetailPage.tsx` | 挂入 `AdvancePanel` |
| 改 `frontend/src/components/NewWorkItemForm.tsx` | 复选框文案改节奏语义 |
| 改 `CHANGELOG.md` | 条目 + 行为变更说明 |

---

## Task 1: 阶段能力单一真源 + 停因分类

先写防漂移守卫（spec 第 11 节指定的"最脆弱处"），再写 `classify`。

**Files:**
- Create: `src/autodev/webapp/drive.py`
- Create: `tests/webapp/test_drive.py`
- Modify: `tests/webapp/test_demo_app.py`（扩既有守卫，约第 92-110 行）

**Interfaces:**
- Produces: `IMPLEMENTED_STAGES: frozenset[WorkflowState]`、`ALL_STAGES: frozenset[WorkflowState]`、`COLLECT_STAGES: frozenset[WorkflowState]`、DriveStop（枚举，成员 `TERMINAL` / `WAIT_HUMAN` / `NOT_IMPLEMENTED` / `MANUAL_HOLD`）、`classify(wi: WorkItem, implemented: frozenset[WorkflowState]) -> DriveStop | None`（返回 `None` 表示可继续自动推进）。

- [ ] **Step 1: 写防漂移守卫测试（追加到既有安全守卫文件末尾）**

追加到 `tests/webapp/test_demo_app.py`：

```python
def test_implemented_stages_matches_real_ports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """防漂移守卫：能力集合必须与生产组合根里"端口是否为桩"逐阶段一致。

    这是本次设计要消灭的根因——同一事实多处手抄。谁加了真适配器却忘了更新集合，
    这里就红。局限：下面的 stage→port 映射本身仍是手工维护的，但它住在测试里，
    漂移的后果是测试大声失败，而不是线上静默错标「待建设」。
    """
    monkeypatch.setenv("AUTODEV_HOME", str(tmp_path))
    from autodev.domain.enums import WorkflowState as S
    from autodev.webapp.config import build_env_service
    from autodev.webapp.drive import IMPLEMENTED_STAGES
    from autodev.webapp.stubs import UnavailableStage

    # INTAKE / ACCEPT 的处理器是纯函数（不碰端口），不参与本断言。
    stage_port = {
        S.TRIAGE: "triage",
        S.CONTEXT: "gatherer",
        S.DESIGN: "designer",
        S.REVIEW: "reviewer",
        S.IMPL: "executor",
        S.VERIFY: "verifier",
        S.SUBMIT_MR: "delivery",
    }
    ctx = build_env_service()._engine.ctx
    for stage, port_name in stage_port.items():
        port_is_real = not isinstance(getattr(ctx, port_name), UnavailableStage)
        assert (stage in IMPLEMENTED_STAGES) == port_is_real, (
            f"{stage.name}: 能力集合认为 {stage in IMPLEMENTED_STAGES}，"
            f"而端口 ctx.{port_name} 实况为 {'真实' if port_is_real else '桩'}"
        )
```

- [ ] **Step 2: 跑它，确认因 `drive.py` 不存在而失败**

Run: `pytest tests/webapp/test_demo_app.py::test_implemented_stages_matches_real_ports -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'autodev.webapp.drive'`

- [ ] **Step 3: 建 `drive.py`，先只放能力集合**

创建 `src/autodev/webapp/drive.py`：

```python
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
```

- [ ] **Step 4: 跑守卫，确认通过**

Run: `pytest tests/webapp/test_demo_app.py::test_implemented_stages_matches_real_ports -q`
Expected: PASS

- [ ] **Step 5: 写 `classify` 组合表测试**

创建 `tests/webapp/test_drive.py`：

```python
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


def _wi(state: S, *, autonomy: bool) -> WorkItem:
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("demo"),
        Requirement("加限流", "demo", (), "加限流"),
        AutonomyDial.all_human(),
        NOW,
        autonomy_enabled=autonomy,
    )
    if state is not S.INTAKE:
        wi.state = state
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
    """挂在门上的工作项即使当前阶段不在能力集合内，也应报 WAIT_HUMAN（须走 /decide）。"""
    wi = _wi(S.WAIT_HUMAN, autonomy=False)
    wi.pending_gate = GatePoint.CONTEXT_GATE
    assert classify(wi, IMPLEMENTED_STAGES) is DriveStop.WAIT_HUMAN
```

- [ ] **Step 6: 跑它，确认因 `classify` 未定义而失败**

Run: `pytest tests/webapp/test_drive.py -q`
Expected: FAIL — `ImportError: cannot import name 'DriveStop'`

- [ ] **Step 7: 实现 DriveStop 与 `classify`**

追加到 `src/autodev/webapp/drive.py`：

```python
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
```

- [ ] **Step 8: 跑测试确认通过**

Run: `pytest tests/webapp/test_drive.py tests/webapp/test_demo_app.py -q`
Expected: PASS（`test_drive.py` 14 项参数化 + 1 项优先级 + demo_app 既有项）

- [ ] **Step 9: 提交**

```bash
git add src/autodev/webapp/drive.py tests/webapp/test_drive.py tests/webapp/test_demo_app.py
git commit -m "feat(drive): 阶段能力单一真源 + 停因分类 + 防漂移守卫"
```

---

## Task 2: 两个驱动入口（自动循环 / 单步）

**Files:**
- Modify: `src/autodev/webapp/drive.py`
- Modify: `tests/webapp/test_drive.py`

**Interfaces:**
- Consumes: Task 1 的 `classify` / DriveStop / `IMPLEMENTED_STAGES` / `COLLECT_STAGES`。
- Produces:
  - `auto_drive(repo: WorkItemRepository, engine: Engine, work_item_id: WorkItemId, implemented: frozenset[WorkflowState] = IMPLEMENTED_STAGES) -> DriveStop | None` —— 循环推进直到出现停因并返回它；工作项不存在时返回 `None`。
  - `step(repo, engine, work_item_id, implemented=IMPLEMENTED_STAGES) -> DriveStop | None` —— 只推进一个阶段并返回推进后的停因；非法态抛 `InvariantError`。

- [ ] **Step 1: 写两个入口的测试**

追加到 `tests/webapp/test_drive.py`（顶部 import 增加下列名字）：

```python
from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.domain.errors import InvariantError
from autodev.webapp.drive import auto_drive, step
from tests.fakes import build_engine_with_fakes
```

```python
def test_auto_drive_runs_continuously_to_capability_edge() -> None:
    """自动挡：连续跑过 DESIGN，停在 REVIEW（不在能力集合内），且不调用 review 桩。"""
    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)
    wi = _wi(S.INTAKE, autonomy=True)
    repo.save(wi)

    stop = auto_drive(repo, engine, wi.id, IMPLEMENTED_STAGES)

    assert stop is DriveStop.NOT_IMPLEMENTED
    assert repo.get(wi.id).state is S.REVIEW
    assert "design" in repo.get(wi.id).artifacts


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
    """单步：手动挡停在 DESIGN 时，step 跑完 DESIGN 就停，不继续。"""
    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)
    wi = _wi(S.DESIGN, autonomy=False)
    repo.save(wi)

    stop = step(repo, engine, wi.id, IMPLEMENTED_STAGES)

    assert repo.get(wi.id).state is S.REVIEW
    assert stop is DriveStop.NOT_IMPLEMENTED


def test_step_ignores_manual_hold_but_refuses_other_stops() -> None:
    """step 无视 MANUAL_HOLD（人已授权），但拒绝终态/门禁/未实现。"""
    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)

    done = _wi(S.DONE, autonomy=False)
    repo.save(done)
    with pytest.raises(InvariantError):
        step(repo, engine, done.id, IMPLEMENTED_STAGES)

    blocked = _wi(S.REVIEW, autonomy=True)
    repo.save(blocked)
    with pytest.raises(InvariantError):
        step(repo, engine, blocked.id, IMPLEMENTED_STAGES)


def test_step_recovers_stranded_work_item() -> None:
    """回归本次问题现场：自动挡工作项搁浅在 DESIGN（当年 DESIGN 不在能力集合内），
    如今 DESIGN 已实现——单步推进应能直接把它救活，无需任何数据迁移。"""
    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)
    stranded = _wi(S.DESIGN, autonomy=True)
    repo.save(stranded)

    assert classify(stranded, IMPLEMENTED_STAGES) is None  # 可推进 → 按钮该亮
    step(repo, engine, stranded.id, IMPLEMENTED_STAGES)

    assert "design" in repo.get(stranded.id).artifacts
```

- [ ] **Step 2: 新增 `build_engine_with_fakes` 助手到 `tests/fakes.py`**

已确认该助手**当前不存在**（`tests/fakes.py` 只有 `FakeWorkspace`/`FakeContext`/`FakeDesign`/… 与 `RecordingPublisher`）。`FakeTriage` 已在该文件顶部从 `autodev.adapters.demo` re-export，可直接用；`TriageIntent` 需新增导入。

在 `tests/fakes.py` 顶部的 `from autodev.domain.enums import WorkspaceMode` 改为：

```python
from autodev.domain.enums import TriageIntent, WorkspaceMode
```

并在文件末尾追加：

```python
def build_engine_with_fakes(repo, *, designer=None):
    """组装一个全假件 Engine，供驱动层测试使用（reviewer 及之后仍为抛错桩）。

    triage 固定为 ACTIONABLE 意图，避免启发式对短 goal 判成 CONSULTATION 而提前 finish。
    """
    from datetime import UTC, datetime

    from autodev.adapters.event_bus import InMemoryEventBus
    from autodev.application.context import StageContext
    from autodev.application.engine import Engine
    from autodev.domain.policies import GatePolicy
    from autodev.webapp.stubs import UnavailableStage

    stub = UnavailableStage()
    ctx = StageContext(
        FakeWorkspace(),
        FakeContext(),
        designer or FakeDesign(),
        stub,
        stub,
        stub,
        stub,
        FakeTriage(intent=TriageIntent.ACTIONABLE),
        GatePolicy(),
    )
    return Engine(repo, InMemoryEventBus(), ctx, clock=lambda: datetime.now(UTC))
```

注意 `FakeTriage` 的启发式对**短 goal + 空 acceptance_hints** 可能判成低置信，从而在上下文后决策处挂起。若 Task 2 的自动挡测试没跑到 REVIEW，把 `_wi` 里的 `Requirement` 换成完整英文短句 + 非空 `acceptance_hints`（`tests/webapp/test_service.py:178` 的注释已记录过这个坑）。

- [ ] **Step 3: 跑测试，确认失败**

Run: `pytest tests/webapp/test_drive.py -q`
Expected: FAIL — `ImportError: cannot import name 'auto_drive'`

- [ ] **Step 4: 实现两个入口**

追加到 `src/autodev/webapp/drive.py`（同时在文件顶部补 import）：

```python
from autodev.application.engine import Engine
from autodev.domain.errors import InvariantError
from autodev.domain.ids import WorkItemId
from autodev.domain.ports import WorkItemRepository
```

```python
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


def step(
    repo: WorkItemRepository,
    engine: Engine,
    work_item_id: WorkItemId,
    implemented: frozenset[S] = IMPLEMENTED_STAGES,
) -> DriveStop | None:
    """人工单步推进一个阶段，返回推进后的停因。

    无视 `MANUAL_HOLD`——手动挡下"等人点"正是本函数存在的理由，人点了就是授权。
    其余停因（终态 / 门禁 / 未实现）一律拒绝并抛 `InvariantError`，由路由映射 409；
    绝不静默无操作（静默正是原缺陷的形态）。
    """
    wi = repo.get(work_item_id)
    stop = classify(wi, implemented)
    if stop is not None and stop is not DriveStop.MANUAL_HOLD:
        raise InvariantError(f"cannot advance work item stopped by {stop.name}")
    engine.advance(wi)
    return classify(repo.get(work_item_id), implemented)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/webapp/test_drive.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/autodev/webapp/drive.py tests/webapp/test_drive.py tests/fakes.py
git commit -m "feat(drive): 自动驱动与单步推进两个入口(停因显式返回)"
```

---

## Task 3: 服务层接线

**Files:**
- Modify: `src/autodev/webapp/service.py`（删第 27-42 行常量与第 60-79 行 `_bounded_drive`；改 `__init__` 参数名；改 `decide_workitem`；加 `advance_workitem`）
- Modify: `src/autodev/webapp/demo_config.py:35,71`
- Modify: `tests/webapp/test_service.py:16,196,199`
- Modify: `tests/webapp/test_demo_service.py:30,61`

**Interfaces:**
- Consumes: Task 2 的 `auto_drive` / `step`，Task 1 的 `classify` / DriveStop / `IMPLEMENTED_STAGES` / `ALL_STAGES`。
- Produces:
  - `ProjectConsoleService.advance_workitem(work_item_id: str) -> WorkItem | None` —— 校验同步（非法抛 `InvariantError`）、执行异步；工作项不存在返回 `None`。
  - `ProjectConsoleService.implemented_stages` —— 只读 property，返回本组合根的能力集合，供路由投影使用。
  - 构造参数 `run_states` **改名** `implemented_stages`。

- [ ] **Step 1: 写服务层测试**

追加到 `tests/webapp/test_service.py`：

```python
def test_advance_workitem_steps_one_stage_and_exposes_capability() -> None:
    """手动挡搁浅在 DESIGN 的工作项：advance 推进一个阶段。"""
    from autodev.domain.errors import InvariantError
    from autodev.webapp.drive import IMPLEMENTED_STAGES

    svc, repo = _project_service_with_fakes()  # 见 Step 2
    wid = _seed_workitem(repo, state=S.DESIGN, autonomy=False)

    assert svc.implemented_stages == IMPLEMENTED_STAGES
    svc.advance_workitem(wid.value)

    assert "design" in repo.get(wid).artifacts


def test_advance_workitem_rejects_illegal_state() -> None:
    """终态/未实现阶段：advance 抛 InvariantError（路由映射 409）。"""
    from autodev.domain.errors import InvariantError

    svc, repo = _project_service_with_fakes()
    wid = _seed_workitem(repo, state=S.DONE, autonomy=False)

    with pytest.raises(InvariantError):
        svc.advance_workitem(wid.value)


def test_advance_workitem_missing_returns_none() -> None:
    svc, _ = _project_service_with_fakes()
    assert svc.advance_workitem("does-not-exist") is None
```

- [ ] **Step 2: 按该文件既有风格补两个测试助手**

先读 `tests/webapp/test_service.py` 现有构造方式（第 156-200 行 `test_drive_reaches_review_and_stops_without_calling_review_stub` 已完整演示如何拼 `StageContext` + `Engine`），照它补：

```python
def _project_service_with_fakes():
    """返回 (ProjectConsoleService, work_repo)，执行器用 SyncExecutor 便于同步断言。"""
    from autodev.adapters.project_repository import InMemoryProjectRepository
    from autodev.webapp.projects import ProjectRegistry

    repo = InMemoryWorkItemRepository()
    engine = build_engine_with_fakes(repo)
    svc = ProjectConsoleService(
        InMemoryProjectRepository(),
        repo,
        FakeWorkspace(),
        engine,
        SyncExecutor(),
        ProjectRegistry({}, None),
    )
    return svc, repo


def _seed_workitem(repo, *, state: S, autonomy: bool) -> WorkItemId:
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("demo"),
        Requirement("加限流", "demo", (), "加限流"),
        AutonomyDial.all_human(),
        NOW,
        autonomy_enabled=autonomy,
    )
    if state is not S.INTAKE:
        wi.state = state
    repo.save(wi)
    return wi.id
```

签名已核对：`InMemoryProjectRepository()` 无参；`ProjectRegistry(repo_map, persist_path=None, ...)` 故 `ProjectRegistry({})` 合法。`ProjectConsoleService` 的前 6 个位置参数顺序为 `(project_repo, work_repo, workspace, engine, executor, registry)`，与 `tests/webapp/test_project_service.py:62-70` 一致。

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/webapp/test_service.py -q`
Expected: FAIL — `AttributeError: 'ProjectConsoleService' object has no attribute 'implemented_stages'`

- [ ] **Step 4: 删掉 service.py 里的旧常量与旧驱动函数**

删除 `src/autodev/webapp/service.py` 第 27-42 行（`RUN` 与 `FULL_DRIVE` 两个常量及其注释）与第 60-79 行（`_bounded_drive` 整个函数），改为从 `drive.py` 导入：

```python
from autodev.webapp.drive import (
    ALL_STAGES,
    IMPLEMENTED_STAGES,
    DriveStop,
    auto_drive,
    classify,
    step,
)
```

`ALL_STAGES` 在本模块虽不直接使用，但为保持 `demo_config.py` 的既有导入路径（它从 `service` 导入 `FULL_DRIVE`）可一并 re-export；若 lint 报未使用，则改为让 `demo_config.py` 直接从 `drive.py` 导入并去掉此行。**推荐后者**（依赖指向更直接）。

- [ ] **Step 5: 把 `WorkItemConsoleService._drive` 切到 `auto_drive`**

`src/autodev/webapp/service.py` 第 133-134 行：

```python
    def _drive(self, work_item_id: WorkItemId) -> None:
        auto_drive(self._repo, self._engine, work_item_id)
```

- [ ] **Step 6: `ProjectConsoleService` 参数改名 + 暴露能力集合**

第 155 行参数、第 167-169 行赋值改为：

```python
        implemented_stages: frozenset[S] = IMPLEMENTED_STAGES,
```

```python
        # dial_factory：按运行时 repo 名构造 AutonomyDial（生产默认全人审；演示传放行工厂）。
        # implemented_stages：本组合根下平台能执行的阶段集合（唯一真源，见 drive.py）。
        # 三处消费：自动驱动边界、视图「待建设」标记、「推进」按钮可用性。
        self._dial_factory = dial_factory
        self._implemented_stages = implemented_stages

    @property
    def implemented_stages(self) -> frozenset[S]:
        """供路由投影使用——视图层据此标注「待建设」并计算 next_action。"""
        return self._implemented_stages
```

- [ ] **Step 7: 建工作项处改用 `auto_drive`**

第 309-311 行：

```python
        self._executor.submit(
            lambda: auto_drive(self._work_repo, self._engine, work_item_id, self._implemented_stages)
        )
```

- [ ] **Step 8: `decide_workitem` 按模式分流**

替换 `decide_workitem` 中 `if decision == "proceed":` 那一段：

```python
        if decision == "proceed":
            # 手动挡下，门禁的「继续」即视为"授权走这一步"——跑一个阶段就交还控制权，
            # 免得为同一个意图点两下（先点「继续」再点「推进」）。自动挡照旧连续跑。
            wi = self._work_repo.get(wid)
            runner = auto_drive if wi.autonomy_enabled else step
            self._executor.submit(
                lambda: runner(self._work_repo, self._engine, wid, self._implemented_stages)
            )
```

- [ ] **Step 9: 新增 `advance_workitem`**

加在 `decide_workitem` 之后：

```python
    def advance_workitem(self, work_item_id: str) -> WorkItem | None:
        """人工单步推进一个阶段。

        **校验同步、执行异步**：单个阶段可能跑数分钟（Claude Code 子进程），因此这里
        只同步判定合法性（非法立即抛 `InvariantError` → 路由 409），真正推进交后台，
        前端靠轮询取新状态。与 `decide_workitem` 同一模式。
        """
        wid = WorkItemId(work_item_id)
        try:
            wi = self._work_repo.get(wid)
        except KeyError:
            return None
        stop = classify(wi, self._implemented_stages)
        if stop is not None and stop is not DriveStop.MANUAL_HOLD:
            raise InvariantError(f"cannot advance work item stopped by {stop.name}")
        self._executor.submit(
            lambda: step(self._work_repo, self._engine, wid, self._implemented_stages)
        )
        return self.get_workitem(work_item_id)
```

在 service.py 顶部补 `from autodev.domain.errors import InvariantError`（该文件已导入 `StageError`，同模块）。

- [ ] **Step 10: 跟随改名，修好既有测试与演示组合根**

- `src/autodev/webapp/demo_config.py`：第 35 行改为 `from autodev.webapp.drive import ALL_STAGES`（`service` 的导入只留 `ProjectConsoleService, SyncExecutor`）；第 71 行改为 `implemented_stages=ALL_STAGES,`。
- `tests/webapp/test_demo_service.py`：第 30 行同样拆分导入，第 61 行改 `implemented_stages=ALL_STAGES,`。
- `tests/webapp/test_service.py`：第 16 行改为 `from autodev.webapp.service import SyncExecutor, WorkItemConsoleService` 并新增 `from autodev.webapp.drive import IMPLEMENTED_STAGES, auto_drive`；第 196 行改 `auto_drive(repo, engine, wid, IMPLEMENTED_STAGES)`；第 199 行注释里的 `∉RUN` 改为 `∉IMPLEMENTED_STAGES`。

- [ ] **Step 11: 跑全量确认绿**

Run: `pytest -q && ruff check . && ruff format --check . && mypy src`
Expected: 全部通过（测试数应比基线 298 多出 Task 1-3 新增项）

- [ ] **Step 12: 提交**

```bash
git add src/autodev/webapp/service.py src/autodev/webapp/demo_config.py tests/webapp/test_service.py tests/webapp/test_demo_service.py
git commit -m "feat(service): 单步推进接线 + 能力集合改名并对外暴露"
```

---

## Task 4: 视图投影（删手抄清单 + `next_action`）

**Files:**
- Modify: `src/autodev/webapp/views.py`（删第 41-44 行 `_UNIMPLEMENTED`；改 `stage_views` / `view_detail` 签名；加投影）
- Modify: `tests/webapp/test_views.py`

**Interfaces:**
- Consumes: Task 1 的 `IMPLEMENTED_STAGES` / `classify` / DriveStop。
- Produces: `stage_views(wi, implemented=IMPLEMENTED_STAGES)`、`view_detail(wi, read_text, implemented=IMPLEMENTED_STAGES)`；detail 新增两键 —— `next_action ∈ {"advance","decide","blocked","none"}`、`next_stage: str | None`（即将执行或被阻塞的阶段中文名）。

- [ ] **Step 1: 写投影测试（含本次 bug 的回归断言）**

追加到 `tests/webapp/test_views.py`：

```python
def test_design_no_longer_marked_blocked() -> None:
    """回归：DESIGN 已实现并进入能力集合，停在 CONTEXT 的工作项不应再把「方案」标为待建设。

    这正是本次发现的线上 bug——views 手抄了一份"未实现阶段"清单并漂移。
    """
    wi = _work_item(S.CONTEXT)
    by_key = {v["key"]: v for v in stage_views(wi)}

    assert by_key["DESIGN"]["status"] == "pending"  # 曾错为 "blocked"
    assert by_key["REVIEW"]["status"] == "blocked"  # REVIEW 确实还没建


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
    wi = _work_item(S.REVIEW)
    wi.autonomy_enabled = True
    detail = view_detail(wi, lambda _p: "")

    assert detail["next_action"] == "blocked"
    assert detail["next_stage"] == "评审"


def test_next_action_decide_when_waiting_human() -> None:
    wi = _work_item(S.WAIT_HUMAN)
    assert view_detail(wi, lambda _p: "")["next_action"] == "decide"


def test_next_action_none_when_terminal() -> None:
    wi = _work_item(S.DONE)
    assert view_detail(wi, lambda _p: "")["next_action"] == "none"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/webapp/test_views.py -q`
Expected: FAIL — `KeyError: 'next_action'`，以及 `test_design_no_longer_marked_blocked` 断言失败（当前确实是 `blocked`）

- [ ] **Step 3: 改 views.py —— 删手抄清单，接入能力集合**

删除第 41-44 行（`_UNIMPLEMENTED` 及其注释），在 import 区加：

```python
from autodev.webapp.drive import IMPLEMENTED_STAGES, DriveStop, classify
```

`stage_views` 改为：

```python
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
```

注意 `S.DONE` 从不属于能力集合（它不是可执行阶段，是终点），故显式排除，否则「完成」会被误标「待建设」。

- [ ] **Step 4: 加 `next_action` / `next_stage` 投影**

在 `_LABELS` 之后加映射表：

```python
# 停因 → 前端交互形态。None（可继续推进）与 MANUAL_HOLD 都给「推进」按钮：
# 前者是搁浅项（历史数据/驱动进程中断），后者是手动挡正常等待，二者都需要人点一下。
_NEXT_ACTION: dict[DriveStop | None, str] = {
    None: "advance",
    DriveStop.MANUAL_HOLD: "advance",
    DriveStop.WAIT_HUMAN: "decide",
    DriveStop.NOT_IMPLEMENTED: "blocked",
    DriveStop.TERMINAL: "none",
}
```

`view_detail` 签名与尾部改为：

```python
def view_detail(
    wi: WorkItem,
    read_text: Callable[[str], str],
    implemented: frozenset[S] = IMPLEMENTED_STAGES,
) -> dict[str, object]:
```

```python
    detail: dict[str, object] = dict(view_summary(wi))
    detail["stages"] = stage_views(wi, implemented)
```

并在 `collect_only` 之后追加：

```python
    # 单一投影字段驱动前端四态，前端不重复判断停因逻辑。
    detail["next_action"] = _NEXT_ACTION[classify(wi, implemented)]
    # 即将执行（或被阻塞）的阶段名——引擎推进的是**当前状态**对应的处理器。
    detail["next_stage"] = _LABELS.get(wi.state)
    return detail
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/webapp/test_views.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/autodev/webapp/views.py tests/webapp/test_views.py
git commit -m "fix(views): 删除手抄的未实现阶段清单 + 投影 next_action"
```

---

## Task 5: 路由 `POST /api/workitems/{id}/advance`

**Files:**
- Modify: `src/autodev/webapp/app.py`（`ConsoleService` 协议约第 49-55 行；`view_detail` 三处调用；新增路由）
- Modify: `tests/webapp/test_app.py`

**Interfaces:**
- Consumes: Task 3 的 `advance_workitem` / `implemented_stages`，Task 4 的 `view_detail(wi, read_text, implemented)`。
- Produces: HTTP `POST /api/workitems/{id}/advance` → 200 返回 detail；404 工作项不存在；409 非法态。

- [ ] **Step 1: 先给 `FakeProjectConsoleService` 补两个成员**

`tests/webapp/test_app.py` 的假 service 是类 `FakeProjectConsoleService`（第 43 行），配套助手是 `_client(service)`（第 144 行）。在其 `decide_workitem`（第 140-141 行）之后追加：

```python
    def advance_workitem(self, work_item_id: str) -> WorkItem | None:
        if self.advance_raises and work_item_id in self._workitems:
            from autodev.domain.errors import InvariantError

            raise InvariantError("cannot advance work item stopped by TERMINAL")
        return self._workitems.get(work_item_id)

    @property
    def implemented_stages(self) -> frozenset[S]:
        from autodev.webapp.drive import IMPLEMENTED_STAGES

        return IMPLEMENTED_STAGES
```

并在 `__init__` 签名末尾加 `advance_raises: bool = False,`，方法体内加 `self.advance_raises = advance_raises`。

- [ ] **Step 2: 写路由测试**

追加到 `tests/webapp/test_app.py`：

```python
def test_advance_endpoint_returns_detail() -> None:
    project = _project()
    wi = _work_item(project, state=S.DESIGN)
    client = _client(FakeProjectConsoleService([project], [wi]))

    response = client.post(f"/api/workitems/{wi.id.value}/advance")

    assert response.status_code == 200
    assert response.json()["next_action"] in {"advance", "decide", "blocked", "none"}


def test_advance_endpoint_404_when_missing() -> None:
    client = _client(FakeProjectConsoleService())
    assert client.post("/api/workitems/nope/advance").status_code == 404


def test_advance_endpoint_409_when_illegal_state() -> None:
    """非法态（终态 / 待门禁 / 未建设）→ 409，而非 400/500，也绝不静默 200。"""
    project = _project()
    wi = _work_item(project, state=S.DONE)
    client = _client(FakeProjectConsoleService([project], [wi], advance_raises=True))

    assert client.post(f"/api/workitems/{wi.id.value}/advance").status_code == 409
```

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/webapp/test_app.py -q`
Expected: FAIL — 404（路由未注册）

- [ ] **Step 4: 扩 `ConsoleService` 协议**

在 `app.py` 的 `ConsoleService` 里补两项（紧跟 `decide_workitem` 之后）：

```python
    def advance_workitem(self, work_item_id: str) -> WorkItem | None: ...

    @property
    def implemented_stages(self) -> frozenset[S]: ...
```

顶部补 `from autodev.domain.enums import WorkflowState as S`。

- [ ] **Step 5: 三处 `view_detail` 调用传能力集合**

`get_workitem`、`approve_workitem`、`decide_workitem` 三个路由里的 `view_detail(wi, _read_text)` 全部改为：

```python
        return view_detail(wi, _read_text, service.implemented_stages)
```

- [ ] **Step 6: 注册 advance 路由**

加在 `decide_workitem` 路由之后：

```python
    @app.post("/api/workitems/{work_item_id}/advance")
    def advance_workitem(work_item_id: str) -> dict[str, object]:
        """人工单步推进一个阶段。

        非法态（终态 / 待门禁 / 阶段未建设）→ 409 Conflict：请求本身合法，是资源
        当前状态不允许。区别于 /decide 的 400（决策参数非法）。
        """
        try:
            wi = service.advance_workitem(work_item_id)
        except InvariantError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        if wi is None:
            raise HTTPException(status_code=404, detail="work item not found")
        return view_detail(wi, _read_text, service.implemented_stages)
```

顶部补 `from autodev.domain.errors import InvariantError`。

- [ ] **Step 7: 跑测试确认通过**

Run: `pytest tests/webapp/test_app.py -q && pytest -q`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add src/autodev/webapp/app.py tests/webapp/test_app.py
git commit -m "feat(api): POST /api/workitems/{id}/advance 单步推进(409 非法态)"
```

---

## Task 6: 前端「推进」面板

**Files:**
- Create: `frontend/src/components/AdvancePanel.tsx` / `AdvancePanel.module.css` / `AdvancePanel.test.tsx`
- Create: `frontend/src/hooks/useAdvanceWorkItem.ts`
- Modify: `frontend/src/api/types.ts:52-62`、`frontend/src/api/client.ts`（末尾）
- Modify: `frontend/src/pages/WorkItemDetailPage.tsx`
- Modify: `frontend/src/components/NewWorkItemForm.tsx:50`

**Interfaces:**
- Consumes: Task 4/5 的 `next_action` / `next_stage` 与 advance 端点。
- Produces: `AdvancePanel({ nextAction, nextStage, onAdvance, isPending })`；`useAdvanceWorkItem(id)`；`advanceWorkItem(id)`。

- [ ] **Step 1: 加类型**

`frontend/src/api/types.ts` 的 `WorkItemDetail` 接口内追加两行，并在其上方加类型别名：

```ts
export type NextAction = 'advance' | 'decide' | 'blocked' | 'none'
```

```ts
  next_action: NextAction
  next_stage: string | null
```

- [ ] **Step 2: 加 API 函数**

`frontend/src/api/client.ts` 末尾追加：

```ts
export function advanceWorkItem(id: string): Promise<WorkItemDetail> {
  return request<WorkItemDetail>(`/api/workitems/${encodeURIComponent(id)}/advance`, {
    method: 'POST',
  })
}
```

- [ ] **Step 3: 加 hook**

创建 `frontend/src/hooks/useAdvanceWorkItem.ts`：

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { advanceWorkItem } from '../api/client'

export function useAdvanceWorkItem(id: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => advanceWorkItem(id as string),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['workitem', id] })
    },
  })
}
```

- [ ] **Step 4: 写组件测试**

创建 `frontend/src/components/AdvancePanel.test.tsx`（照 `StatusBadge.test.tsx` 的既有风格）：

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AdvancePanel } from './AdvancePanel'

describe('AdvancePanel', () => {
  it('advance 态渲染可点按钮并显示下一阶段', async () => {
    const onAdvance = vi.fn()
    render(
      <AdvancePanel nextAction="advance" nextStage="方案" onAdvance={onAdvance} isPending={false} />,
    )

    const button = screen.getByTestId('advance-button')
    expect(button).toBeEnabled()
    expect(screen.getByText(/方案/)).toBeInTheDocument()

    await userEvent.click(button)
    expect(onAdvance).toHaveBeenCalledOnce()
  })

  it('blocked 态按钮禁用并说明尚未建设', () => {
    render(
      <AdvancePanel nextAction="blocked" nextStage="评审" onAdvance={vi.fn()} isPending={false} />,
    )

    expect(screen.getByTestId('advance-button')).toBeDisabled()
    expect(screen.getByText(/尚未建设/)).toBeInTheDocument()
  })

  it('isPending 时按钮禁用', () => {
    render(
      <AdvancePanel nextAction="advance" nextStage="方案" onAdvance={vi.fn()} isPending={true} />,
    )
    expect(screen.getByTestId('advance-button')).toBeDisabled()
  })

  it('decide / none 态不渲染任何东西（交给人审面板或无操作）', () => {
    const { container: a } = render(
      <AdvancePanel nextAction="decide" nextStage={null} onAdvance={vi.fn()} isPending={false} />,
    )
    expect(a).toBeEmptyDOMElement()

    const { container: b } = render(
      <AdvancePanel nextAction="none" nextStage={null} onAdvance={vi.fn()} isPending={false} />,
    )
    expect(b).toBeEmptyDOMElement()
  })
})
```

- [ ] **Step 5: 跑测试确认失败**

Run: `cd frontend && npm run test -- AdvancePanel`
Expected: FAIL — 无法解析 `./AdvancePanel`

- [ ] **Step 6: 实现组件**

创建 `frontend/src/components/AdvancePanel.tsx`：

```tsx
import type { NextAction } from '../api/types'
import styles from './AdvancePanel.module.css'

interface AdvancePanelProps {
  nextAction: NextAction
  nextStage: string | null
  onAdvance: () => void
  isPending: boolean
}

export function AdvancePanel({ nextAction, nextStage, onAdvance, isPending }: AdvancePanelProps) {
  // decide 交人审面板处理；none 是终态，无操作可做。
  if (nextAction === 'decide' || nextAction === 'none') {
    return null
  }

  const blocked = nextAction === 'blocked'
  const stage = nextStage ?? '下一阶段'

  return (
    <section className={styles.panel} data-testid="advance-panel">
      <p className={styles.title}>推进</p>
      <p className={styles.hint}>
        {blocked ? `「${stage}」阶段尚未建设，暂时无法继续。` : `下一步将执行「${stage}」阶段。`}
      </p>
      <button
        type="button"
        className={styles.button}
        data-testid="advance-button"
        disabled={blocked || isPending}
        onClick={onAdvance}
      >
        {isPending ? '推进中…' : '推进下一步 →'}
      </button>
    </section>
  )
}
```

创建 `frontend/src/components/AdvancePanel.module.css`。令牌名已按 `frontend/src/styles/tokens.css` 核对（可用的是 `--surface` / `--line` / `--radius` / `--muted` / `--ink-soft` / `--done` / `--space-*`，**没有** `--color-*` 或 `--radius-lg` 之类），面板与按钮样式对齐 `WorkItemDetailPage.module.css` 的 `.section` / `.approveBtn`：

```css
.panel {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  padding: var(--space-4) var(--space-5);
}

.title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: var(--space-3);
}

.hint {
  font-size: 0.85rem;
  color: var(--ink-soft);
  margin-bottom: var(--space-3);
}

.button {
  font-size: 0.85rem;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius);
  border: 1px solid var(--done);
  background: var(--done);
  color: #fff;
  cursor: pointer;
}

.button:disabled {
  opacity: 0.5;
  cursor: default;
}
```

- [ ] **Step 7: 跑测试确认通过**

Run: `cd frontend && npm run test -- AdvancePanel`
Expected: PASS（4 项）

- [ ] **Step 8: 挂进详情页**

`frontend/src/pages/WorkItemDetailPage.tsx`：加 import

```tsx
import { AdvancePanel } from '../components/AdvancePanel'
import { useAdvanceWorkItem } from '../hooks/useAdvanceWorkItem'
```

在 `const decide = useDecideWorkItem(id)` 之后加：

```tsx
  const advance = useAdvanceWorkItem(id)
```

在「生命周期」那个 `<section>` **之后**插入：

```tsx
      <AdvancePanel
        nextAction={detail.next_action}
        nextStage={detail.next_stage}
        onAdvance={() => advance.mutate()}
        isPending={advance.isPending}
      />
```

- [ ] **Step 9: 改建项复选框文案为节奏语义**

`frontend/src/components/NewWorkItemForm.tsx` 第 50 行：

```tsx
        <span>自动挡：AI 连续推进后续阶段（不勾选＝手动挡，收集完上下文后每一步由你点「推进」）</span>
```

- [ ] **Step 10: 前端全量门禁**

Run: `cd frontend && npm run typecheck && npm run lint && npm run test && npm run format:check && npm run build`
Expected: 全部通过

- [ ] **Step 11: 提交**

```bash
git add frontend/src
git commit -m "feat(frontend): 「推进」面板(按 next_action 四态) + 复选框改节奏语义"
```

---

## Task 7: 文档收尾

**Files:**
- Modify: `CHANGELOG.md`（`[Unreleased]` 段）
- Modify: `tests/e2e/browser_e2e.sh:98`（注释里的 `FULL_DRIVE` 措辞）

- [ ] **Step 1: 加 CHANGELOG 条目**

在 `CHANGELOG.md` 的 `[Unreleased]` → `### Added` 顶部插入：

```markdown
- **手动挡(单步推进) + 阶段能力单一真源**：`WorkItem.autonomy_enabled` 从"只管上下文后决策"泛化为**节奏总开关**——开＝自动挡(AI 连续推进)，关＝手动挡(收集段仍自动跑完,之后每一步由人点「推进」)。新增 `src/autodev/webapp/drive.py` 承载三件事:阶段能力集合(**唯一真源**,替代原先 service 与 views 各存一份的手抄清单)、停因分类纯函数(终态/门禁/未建设/手动等待四态,判定顺序即优先级)、两个驱动入口(自动循环 / 单步——后者无视"手动等待"因为人已授权,其余停因抛 `InvariantError`)。新增 `POST /api/workitems/{id}/advance`(校验同步→非法态 409、执行异步→阶段可能跑数分钟);`view_detail` 新增单一投影字段 `next_action`(advance/decide/blocked/none)+ `next_stage`,前端不重复判断停因;新增 `AdvancePanel` 按四态渲染。修掉**搁浅工作项无任何恢复入口**的结构性缺陷:原有界驱动对"合法地停"(终态/挂起)与"平台还做不了该阶段"都是同一个静默 return,后者没有状态、没有入口、UI 上却与进行中无异——驱动边界每扩一次就制造一批永久失联的工作项。收敛真源后,扩容即自动解除搁浅,历史数据零迁移。`WAIT_HUMAN` 与 `GatePoint` 语义、领域状态机**均零改动**(铁律 5)。规划见 `docs/superpowers/specs/2026-07-30-manual-drive-mode-design.md` 与 `docs/superpowers/plans/2026-07-30-manual-drive-mode.md`。
```

在 `### Fixed` 段顶部插入：

```markdown
- **「方案」阶段在 UI 上被误标「待建设」**：`views.py` 手抄了一份"未实现阶段"清单，与驱动用的那份是同一事实的第二份副本且已漂移——DESIGN 早已实现并进入驱动集合，停在上下文阶段的工作项却仍把「方案」显示为「待建设」。已删除该副本，改为消费单一真源；并加防漂移守卫测试(断言能力集合与生产组合根里"端口是否为桩"逐阶段一致)，下次谁加了真适配器忘改集合即测试失败。
```

在 `### Changed` 段追加：

```markdown
- **行为变更**：`autonomy_enabled` 为关的工作项，行为从"过了 CONTEXT_GATE 便连续跑"变为"每步等人点「推进」"。这是节奏开关泛化的直接后果(见上)；自动挡行为不变。
```

- [ ] **Step 2: 修 e2e 脚本注释里的旧常量名**

`tests/e2e/browser_e2e.sh` 第 98 行注释中的 `FULL_DRIVE` 改为 `ALL_STAGES`（仅注释，无行为影响）。

- [ ] **Step 3: 跑文档一致性检查**

Run: `pytest -q tests/docs`
Expected: PASS（11 项）。若报伪造符号，检查是否在正文行内反引号里写了 `src/**` 中不存在的名字。

- [ ] **Step 4: 全量验收**

Run: `pytest -q && ruff check . && ruff format --check . && mypy src && cd frontend && npm run typecheck && npm run lint && npm run test && npm run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add CHANGELOG.md tests/e2e/browser_e2e.sh
git commit -m "docs: CHANGELOG 对齐手动挡 + 阶段能力单一真源"
```

---

## 手工验收（实现完成后）

对着本次问题的原始现场跑一遍：

1. 重启控制台服务，打开那个停在「方案」的历史工作项（voice-agent 项目）。
2. 确认「方案」不再是死局——页面出现「推进」面板，提示"下一步将执行「方案」阶段"。
3. 点「推进下一步」，确认真的跑起 DESIGN 阶段并产出方案文档面板。
4. 确认「评审」行仍显示「待建设」，且推进到 REVIEW 后按钮变灰并给出"「评审」阶段尚未建设"。
5. 新建一个**手动挡**工作项：确认建完即自动跑到上下文（能看到分诊 + 简报），并挂在 CONTEXT_GATE 三键面板；点「继续后续流程」后**只跑一个阶段**（方案）就停住等你再点。
6. 新建一个**自动挡**工作项：确认行为与本次改动前一致（连续跑到能力边界）。
