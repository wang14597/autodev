# LLM 分诊 + AI 自主开关 + 仅收集停靠 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 WorkItem 支持「仅收集需求即停」的业务场景——分诊改为 LLM(经 TriagePort 直连 API),新增 `autonomy_enabled` 开关:关则收集上下文后挂起交用户决定,开则由 AI 意图(咨询/落地)驱动是否继续;下游仍走既有风险门禁。

**Architecture:** 六边形 + 轻量状态机。LLM 只在 `adapters/`(铁律 1)。分诊经新出站端口 `TriagePort`;上下文后新增一等人审点 `CONTEXT_GATE`。分两个子迭代:**A = 确定性闭环**(开关/门/策略/迁移/前端/E2E,`FakeTriage`,无网络);**B = 真实 `LlmTriageAdapter`**(直连 API,`@live` 门控)。

**Tech Stack:** Python 3.11 / dataclasses / FastAPI / SQLite;前端 Vite+React+TS+TanStack Query;测试 pytest + vitest + agent-browser。

## Global Constraints

- 核心域 `src/autodev/domain` 不得 import 外部 SDK,也不得 import `application`/`adapters`(铁律 1)。
- 外部交互只经 `ports.py` 端口,实现放 `adapters/`(铁律 2);外部异常在 ACL 边界翻译为领域 `StageError`(铁律 3)。
- 产物 `add_artifact` 只追加(铁律 4);人审为一等 `WAIT_HUMAN` 状态(铁律 5);所有失败有界收敛(铁律 7)。
- TDD:先写失败测试再实现。Conventional Commits;提交在非默认分支(当前 `feat/slice2.1-triage-trust-gate` 之上继续)。
- 改 `src/**` 需在 `CHANGELOG.md` 加条目;文档反引号不得引用代码中不存在的符号(前端组件名入 `docs/.doc-allowlist.txt`)。
- 命令:`. venv/bin/activate`;`pytest -q`;`ruff check . && ruff format --check . && mypy src`;前端 `cd frontend && npm run typecheck && npm run lint && npm run test && npm run build`。

---

# 子迭代 A —— 确定性闭环(无网络,可 agent-browser E2E)

### Task A1: 领域枚举与产物字段

**Files:**
- Modify: `src/autodev/domain/enums.py`
- Modify: `src/autodev/domain/artifacts.py`
- Test: `tests/domain/test_artifacts_intent.py`

**Interfaces:**
- Produces: `TriageIntent(Enum){ACTIONABLE, CONSULTATION}`;`GatePoint.CONTEXT_GATE`;`TriageArtifact` 新字段 `intent: TriageIntent = TriageIntent.ACTIONABLE`。

- [ ] **Step 1: 写失败测试**

```python
# tests/domain/test_artifacts_intent.py
from autodev.domain.artifacts import TriageArtifact
from autodev.domain.enums import GatePoint, RiskLevel, TaskType, TriageIntent, WorkspaceMode


def test_triage_artifact_defaults_intent_actionable():
    art = TriageArtifact(TaskType.SMALL_CHANGE, 0.9, WorkspaceMode.REUSE)
    assert art.intent is TriageIntent.ACTIONABLE


def test_triage_artifact_carries_consultation_intent():
    art = TriageArtifact(
        TaskType.SMALL_CHANGE, 0.9, WorkspaceMode.REUSE, RiskLevel.LOW, ("x",),
        TriageIntent.CONSULTATION,
    )
    assert art.intent is TriageIntent.CONSULTATION


def test_context_gate_exists():
    assert GatePoint.CONTEXT_GATE
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/domain/test_artifacts_intent.py -q`
Expected: FAIL(`ImportError: cannot import name 'TriageIntent'`)

- [ ] **Step 3: 实现**

`enums.py` 增:
```python
class TriageIntent(Enum):
    ACTIONABLE = auto()
    CONSULTATION = auto()
```
`GatePoint` 增成员 `CONTEXT_GATE = auto()`。
`artifacts.py` 的 `TriageArtifact` 尾部加字段(在 `signals` 之后):
```python
from autodev.domain.enums import RiskLevel, TaskType, TriageIntent, WorkspaceMode
# ...
    intent: TriageIntent = TriageIntent.ACTIONABLE
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/domain/test_artifacts_intent.py -q`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add src/autodev/domain/enums.py src/autodev/domain/artifacts.py tests/domain/test_artifacts_intent.py
git commit -m "feat(domain): add TriageIntent, CONTEXT_GATE, TriageArtifact.intent"
```

---

### Task A2: WorkItem 开关字段 + 状态机新转移

**Files:**
- Modify: `src/autodev/domain/work_item.py`
- Test: `tests/domain/test_work_item_autonomy.py`

**Interfaces:**
- Produces: `WorkItem.autonomy_enabled: bool = False`;`WorkItem.create(..., autonomy_enabled=False)`;合法转移 `CONTEXT→WAIT_HUMAN`、`CONTEXT→DONE`、`WAIT_HUMAN→DESIGN`。

- [ ] **Step 1: 写失败测试**

```python
# tests/domain/test_work_item_autonomy.py
from datetime import datetime
from autodev.domain.enums import WorkflowState as S
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem

NOW = datetime(2026, 7, 27)


def _wi(enabled=False):
    return WorkItem.create(
        WorkItemId.new(), RepoRef("r"), Requirement("g", "r", (), "g"),
        AutonomyDial.all_human(), NOW, autonomy_enabled=enabled,
    )


def test_autonomy_enabled_defaults_false():
    assert _wi().autonomy_enabled is False


def test_autonomy_enabled_settable():
    assert _wi(True).autonomy_enabled is True


def test_context_can_suspend_and_finish_and_resume_to_design():
    wi = _wi()
    wi.transition_to(S.TRIAGE, "", NOW)
    wi.transition_to(S.CONTEXT, "", NOW)
    # CONTEXT → WAIT_HUMAN 合法
    wi.transition_to(S.WAIT_HUMAN, "gate", NOW)
    # WAIT_HUMAN → DESIGN 合法
    wi.transition_to(S.DESIGN, "proceed", NOW)


def test_context_can_go_done_directly():
    wi = _wi()
    wi.transition_to(S.TRIAGE, "", NOW)
    wi.transition_to(S.CONTEXT, "", NOW)
    wi.transition_to(S.DONE, "collect-only", NOW)  # 合法
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/domain/test_work_item_autonomy.py -q`
Expected: FAIL(`TypeError: create() got unexpected keyword 'autonomy_enabled'`)

- [ ] **Step 3: 实现**

`work_item.py`:
- dataclass 加字段 `autonomy_enabled: bool = False`(放在 `base_branch` 附近)。
- `create(...)` 增形参 `autonomy_enabled: bool = False` 并传入构造。
- `_build_allowed()` 内在「回退/人审挂起」段后补:
```python
    allowed[S.CONTEXT].add(S.WAIT_HUMAN)   # CONTEXT_GATE 挂起
    allowed[S.CONTEXT].add(S.DONE)         # 仅收集完成
    allowed[S.WAIT_HUMAN].add(S.DESIGN)    # 人工/自动选择继续
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/domain/test_work_item_autonomy.py -q`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add src/autodev/domain/work_item.py tests/domain/test_work_item_autonomy.py
git commit -m "feat(domain): WorkItem.autonomy_enabled + CONTEXT gate/finish transitions"
```

---

### Task A3: SQLite 序列化 autonomy_enabled + intent(B1)

**Files:**
- Modify: `src/autodev/adapters/sqlite_repository.py`
- Test: `tests/adapters/test_sqlite_repository.py`(追加)

**Interfaces:**
- Consumes: A1 的 `TriageArtifact.intent`、A2 的 `WorkItem.autonomy_enabled`。
- Produces: 存取后二者不丢;旧行兜底(intent→ACTIONABLE, autonomy_enabled→False)。

- [ ] **Step 1: 写失败测试(追加到文件末尾)**

```python
def test_autonomy_enabled_roundtrips(tmp_path):
    from autodev.domain.enums import WorkflowState as S
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    wi = WorkItem.create(
        WorkItemId.new(), RepoRef("r"), Requirement("g", "r", (), "g"),
        AutonomyDial.all_human(), NOW, autonomy_enabled=True,
    )
    repo.save(wi)
    assert repo.get(wi.id).autonomy_enabled is True


def test_triage_intent_roundtrips(tmp_path):
    from autodev.domain.enums import RiskLevel, TriageIntent
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    wi = WorkItem.create(
        WorkItemId.new(), RepoRef("r"), Requirement("g", "r", (), "g"),
        AutonomyDial.all_human(), NOW,
    )
    wi.add_artifact("triage", TriageArtifact(
        TaskType.SMALL_CHANGE, 0.9, WorkspaceMode.REUSE, RiskLevel.LOW, (), TriageIntent.CONSULTATION))
    wi.transition_to(S.TRIAGE, "ok", NOW)
    repo.save(wi)
    assert repo.get(wi.id).artifacts["triage"].intent is TriageIntent.CONSULTATION


def test_legacy_row_defaults(tmp_path):
    from autodev.adapters.sqlite_repository import _artifact_from_dict
    from autodev.domain.enums import TriageIntent
    art = _artifact_from_dict({"__t": "TriageArtifact", "level": "SMALL_CHANGE",
        "confidence": 0.9, "workspace_mode": "REUSE"})
    assert art.intent is TriageIntent.ACTIONABLE
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/adapters/test_sqlite_repository.py -k "autonomy or intent or legacy" -q`
Expected: FAIL(autonomy_enabled 恒 False / intent 恒 ACTIONABLE 丢值)

- [ ] **Step 3: 实现**

`sqlite_repository.py`:
- `import` 增 `TriageIntent`。
- `_to_dict(wi)` 的 dict 增 `"autonomy_enabled": wi.autonomy_enabled`。
- `_from_dict(d)` 构造 WorkItem 时传 `autonomy_enabled=d.get("autonomy_enabled", False)`。
- `_artifact_to_dict` 的 TriageArtifact 分支增 `"intent": a.intent.name`。
- `_artifact_from_dict` 的 TriageArtifact 分支尾参增 `TriageIntent[d.get("intent", "ACTIONABLE")]`。

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/adapters/test_sqlite_repository.py -q`
Expected: PASS(全部)

- [ ] **Step 5: 提交**

```bash
git add src/autodev/adapters/sqlite_repository.py tests/adapters/test_sqlite_repository.py
git commit -m "fix(persistence): serialize autonomy_enabled + TriageArtifact.intent"
```

---

### Task A4: StageOutcome.finish + 引擎 _on_finish + advance 分发(B5)

**Files:**
- Modify: `src/autodev/domain/outcome.py`
- Modify: `src/autodev/application/engine.py`
- Test: `tests/application/test_engine_finish.py`

**Interfaces:**
- Produces: `StageOutcome.finish(artifact_key, artifact)`(kind="finish");引擎遇 finish → 存产物 → 当前态转 DONE → `_finalize_done` → 发 `WorkItemCompleted`。

- [ ] **Step 1: 写失败测试**

```python
# tests/application/test_engine_finish.py
from datetime import datetime
from autodev.application.engine import Engine
from autodev.application.context import StageContext
from autodev.domain.enums import WorkflowState as S
from autodev.domain.ids import WorkItemId
from autodev.domain.outcome import StageOutcome
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem
from autodev.domain.events import WorkItemCompleted
from tests.fakes import (FakeWorkspace, FakeContext, FakeDesign, FakeReview,
    FakeExecution, FakeVerification, FakeDelivery, RecordingPublisher)
from autodev.domain.policies import GatePolicy

NOW = datetime(2026, 7, 27)


def test_finish_outcome_transitions_current_state_to_done():
    from autodev.adapters.memory_repository import InMemoryWorkItemRepository
    repo = InMemoryWorkItemRepository()
    bus = RecordingPublisher()
    # 一个最小 ctx；triage_policy 位后续 Task 换 triage，此处用占位 FakeTriage
    from tests.fakes import FakeTriage  # A9 会新增；本测试依赖它
    ctx = StageContext(FakeWorkspace(local=True), FakeContext(), FakeDesign(), FakeReview(),
        FakeExecution(), FakeVerification(), FakeDelivery(), FakeTriage(), GatePolicy())
    eng = Engine(repo, bus, ctx, clock=lambda: NOW)
    wi = WorkItem.create(WorkItemId.new(), RepoRef("r"), Requirement("g", "r", (), "g"),
        AutonomyDial.all_human(), NOW)
    wi.transition_to(S.TRIAGE, "", NOW)
    wi.transition_to(S.CONTEXT, "", NOW)
    repo.save(wi)
    # 直接驱动 _on_finish 语义：模拟 handler 返回 finish
    eng._on_finish(wi, StageOutcome.finish("context", object()), NOW)
    assert wi.state is S.DONE
    assert any(isinstance(e, WorkItemCompleted) for e in bus.events)
```

> 注:此测试依赖 A9 的 `FakeTriage`。若按序执行,A4 先加 `StageOutcome.finish` 与 `_on_finish`,该测试待 A9 后转绿;或本步先用现有 `tests.fakes` 里任一 triage 占位。执行者按 subagent-driven 顺序处理依赖。

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/application/test_engine_finish.py -q`
Expected: FAIL(`AttributeError: 'StageOutcome' has no attribute 'finish'`)

- [ ] **Step 3: 实现**

`outcome.py` 增:
```python
    @classmethod
    def finish(cls, artifact_key=None, artifact=None):
        return cls("finish", artifact_key=artifact_key, artifact=artifact)
```
`engine.py`:
- `advance` 分发增分支(在 suspend 与 else 之间):
```python
        elif outcome.kind == "finish":
            self._on_finish(work_item, outcome, now)
```
- 新增方法:
```python
    def _on_finish(self, wi, outcome, now):
        if outcome.artifact_key:
            wi.add_artifact(outcome.artifact_key, outcome.artifact)
        wi.transition_to(S.DONE, "collect-only complete", now)
        self._finalize_done(wi)
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/application/test_engine_finish.py -q`(A9 完成后)
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/autodev/domain/outcome.py src/autodev/application/engine.py tests/application/test_engine_finish.py
git commit -m "feat(engine): StageOutcome.finish + _on_finish (collect-only DONE)"
```

---

### Task A5: TriagePort 端口 + TriageSignal + 移除 TriagePolicy + workspace_mode_for

**Files:**
- Modify: `src/autodev/domain/ports.py`
- Modify: `src/autodev/domain/value_objects.py`
- Modify: `src/autodev/domain/policies.py`(移除 `TriagePolicy` 类,新增 `workspace_mode_for`)
- Test: `tests/domain/test_workspace_mode.py`

**Interfaces:**
- Produces:
  - `TriageSignal`(frozen):`level: TaskType`、`confidence: float`、`risk: RiskLevel`、`intent: TriageIntent`、`signals: tuple[str, ...]`。
  - `TriagePort(Protocol)`:`classify(requirement: Requirement) -> TriageSignal`。
  - `workspace_mode_for(status: RepoStatus) -> WorkspaceMode`。
- Removes: 领域 `TriagePolicy` 类(后续由 `TriagePort` 适配器替代)。

- [ ] **Step 1: 写失败测试**

```python
# tests/domain/test_workspace_mode.py
from autodev.domain.enums import WorkspaceMode
from autodev.domain.policies import workspace_mode_for
from autodev.domain.value_objects import RepoStatus


def test_workspace_mode_for():
    assert workspace_mode_for(RepoStatus(True, True)) is WorkspaceMode.REUSE
    assert workspace_mode_for(RepoStatus(False, True)) is WorkspaceMode.FETCH
    assert workspace_mode_for(RepoStatus(False, False)) is WorkspaceMode.CREATE
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/domain/test_workspace_mode.py -q`
Expected: FAIL(`ImportError: cannot import name 'workspace_mode_for'`)

- [ ] **Step 3: 实现**

`value_objects.py` 增:
```python
@dataclass(frozen=True)
class TriageSignal:
    level: TaskType
    confidence: float
    risk: RiskLevel
    intent: TriageIntent
    signals: tuple[str, ...] = ()
```
(import `RiskLevel, TaskType, TriageIntent`。)
`ports.py` 增:
```python
class TriagePort(Protocol):
    def classify(self, requirement: Requirement) -> TriageSignal: ...
```
(import `TriageSignal`。)
`policies.py`:删除 `class TriagePolicy` 及其关键词表(迁到 A9 的 FakeTriage);新增:
```python
def workspace_mode_for(status: RepoStatus) -> WorkspaceMode:
    if status.exists_local:
        return WorkspaceMode.REUSE
    if status.exists_remote:
        return WorkspaceMode.FETCH
    return WorkspaceMode.CREATE
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/domain/test_workspace_mode.py -q`
Expected: PASS。(注:此步会使引用 `TriagePolicy` 的旧测试/装配暂时红——A6/A7 修复。)

- [ ] **Step 5: 提交**

```bash
git add src/autodev/domain/ports.py src/autodev/domain/value_objects.py src/autodev/domain/policies.py tests/domain/test_workspace_mode.py
git commit -m "feat(domain): TriagePort + TriageSignal + workspace_mode_for; remove heuristic TriagePolicy"
```

---

### Task A6: AutonomyPolicy 上下文后决策

**Files:**
- Modify: `src/autodev/domain/policies.py`
- Test: `tests/domain/test_autonomy_policy.py`

**Interfaces:**
- Consumes: `WorkItem.autonomy_enabled`、`TriageArtifact(risk/confidence/intent/signals)`、`GatePolicy.CONFIDENCE_GATE_THRESHOLD`。
- Produces: `AutonomyPolicy().decide_after_context(work_item) -> str`(返回 `"suspend"|"proceed"|"finish"`)。

- [ ] **Step 1: 写失败测试**

```python
# tests/domain/test_autonomy_policy.py
from datetime import datetime
from autodev.domain.artifacts import TriageArtifact
from autodev.domain.enums import RiskLevel, TaskType, TriageIntent, WorkspaceMode
from autodev.domain.ids import WorkItemId
from autodev.domain.policies import AutonomyPolicy
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem

NOW = datetime(2026, 7, 27)


def _wi(enabled, *, risk=RiskLevel.LOW, conf=0.9, intent=TriageIntent.ACTIONABLE,
        signals=(), with_triage=True):
    wi = WorkItem.create(WorkItemId.new(), RepoRef("r"), Requirement("g", "r", (), "g"),
        AutonomyDial.all_human(), NOW, autonomy_enabled=enabled)
    if with_triage:
        wi.add_artifact("triage", TriageArtifact(TaskType.SMALL_CHANGE, conf,
            WorkspaceMode.REUSE, risk, signals, intent))
    return wi


def test_disabled_suspends():
    assert AutonomyPolicy().decide_after_context(_wi(False)) == "suspend"


def test_enabled_consultation_finishes():
    assert AutonomyPolicy().decide_after_context(
        _wi(True, intent=TriageIntent.CONSULTATION)) == "finish"


def test_enabled_actionable_proceeds():
    assert AutonomyPolicy().decide_after_context(
        _wi(True, intent=TriageIntent.ACTIONABLE)) == "proceed"


def test_low_confidence_suspends_even_when_enabled():
    assert AutonomyPolicy().decide_after_context(
        _wi(True, conf=0.3, intent=TriageIntent.ACTIONABLE)) == "suspend"


def test_triage_unavailable_suspends_even_when_enabled_consultation():
    # 兜底优先：unavailable 信号 → suspend，即便开启且意图=咨询
    assert AutonomyPolicy().decide_after_context(
        _wi(True, conf=0.0, signals=("triage-unavailable",),
            intent=TriageIntent.CONSULTATION)) == "suspend"


def test_no_triage_suspends():
    assert AutonomyPolicy().decide_after_context(_wi(True, with_triage=False)) == "suspend"
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/domain/test_autonomy_policy.py -q`
Expected: FAIL(`ImportError: cannot import name 'AutonomyPolicy'`)

- [ ] **Step 3: 实现**

`policies.py` 增(复用 `GatePolicy.CONFIDENCE_GATE_THRESHOLD` 单一真源):
```python
class AutonomyPolicy:
    def decide_after_context(self, work_item: WorkItem) -> str:
        triage = work_item.artifacts.get("triage")
        # 规则 1（安全兜底，先于开关/意图）：无分诊 / 不可用 / 低置信 → 人审
        if triage is None:
            return "suspend"
        t = cast(TriageArtifact, triage)
        if "triage-unavailable" in t.signals or t.confidence < GatePolicy.CONFIDENCE_GATE_THRESHOLD:
            return "suspend"
        # 规则 2：开关关 → 用户决定
        if not work_item.autonomy_enabled:
            return "suspend"
        # 规则 3：咨询类 → 仅收集完成
        if t.intent is TriageIntent.CONSULTATION:
            return "finish"
        # 规则 4：其余 → 继续
        return "proceed"
```
(import `TriageIntent`、`TriageArtifact`;`cast` 已在文件中。)

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/domain/test_autonomy_policy.py -q`
Expected: PASS(6 passed)

- [ ] **Step 5: 提交**

```bash
git add src/autodev/domain/policies.py tests/domain/test_autonomy_policy.py
git commit -m "feat(domain): AutonomyPolicy.decide_after_context (safety-first suspend)"
```

---

### Task A7: handlers 接 TriagePort + AutonomyPolicy + 降级

**Files:**
- Modify: `src/autodev/application/context.py`(StageContext 字段 `triage_policy`→`triage: TriagePort`)
- Modify: `src/autodev/application/handlers.py`
- Test: `tests/application/test_handlers_front.py`(改造相关用例)

**Interfaces:**
- Consumes: `TriagePort.classify`、`workspace_mode_for`、`AutonomyPolicy`、`StageOutcome.finish`。
- Produces: `handle_triage` 组装 `TriageArtifact`(含 intent),`StageError` 时产降级产物;`handle_context` 按 `AutonomyPolicy` 返回 suspend/finish/ok。

- [ ] **Step 1: 写失败测试**

```python
# 追加/改造 tests/application/test_handlers_front.py
def test_handle_triage_uses_port_and_workspace_mode():
    from autodev.application.handlers import handle_triage
    from autodev.application.context import StageContext
    from autodev.domain.enums import TriageIntent, RiskLevel
    from tests.fakes import FakeWorkspace, FakeTriage
    from autodev.domain.policies import GatePolicy
    # FakeTriage 返回 CONSULTATION/LOW/0.9（见 A9）
    ctx = StageContext(FakeWorkspace(local=True), None, None, None, None, None, None,
        FakeTriage(intent=TriageIntent.CONSULTATION), GatePolicy())
    wi = _make_context_ready_workitem()  # 已在 INTAKE→TRIAGE 前
    out = handle_triage(wi, ctx, NOW)
    assert out.kind == "success"
    art = out.artifact
    assert art.intent is TriageIntent.CONSULTATION


def test_handle_triage_degrades_on_stage_error():
    from autodev.application.handlers import handle_triage
    from autodev.domain.errors import StageError
    from autodev.domain.enums import FailureKind, RiskLevel
    class BoomTriage:
        def classify(self, req): raise StageError(FailureKind.TRANSIENT, "api down")
    ctx = _ctx_with_triage(BoomTriage())
    out = handle_triage(_triage_ready_wi(), ctx, NOW)
    assert out.kind == "success"
    assert out.artifact.risk is RiskLevel.HIGH
    assert "triage-unavailable" in out.artifact.signals


def test_handle_context_suspends_when_disabled():
    out = _run_handle_context(autonomy_enabled=False)
    assert out.kind == "suspend"
    assert out.gate_point.name == "CONTEXT_GATE"


def test_handle_context_finishes_on_enabled_consultation():
    out = _run_handle_context(autonomy_enabled=True, intent="CONSULTATION")
    assert out.kind == "finish"
```

（执行者:补齐上面 `_make_*`/`_ctx_with_triage`/`_run_handle_context` 小工厂,风格仿本文件既有夹具。）

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/application/test_handlers_front.py -q`
Expected: FAIL(`handle_triage` 仍调 `ctx.triage_policy`;`handle_context` 恒 success)

- [ ] **Step 3: 实现**

`context.py`:字段 `triage_policy: TriagePolicy` → `triage: TriagePort`(import 改 `TriagePort`)。
`handlers.py`:
```python
def handle_triage(work_item, ctx, now):
    status = ctx.workspace.repo_status(work_item.repo_ref)
    mode = workspace_mode_for(status)
    try:
        sig = ctx.triage.classify(work_item.requirement)
        art = TriageArtifact(sig.level, sig.confidence, mode, sig.risk, sig.signals, sig.intent)
    except StageError:
        # 基础设施失败 → 降级产物（低置信/unavailable → AutonomyPolicy 后续导向人审）
        art = TriageArtifact(TaskType.SMALL_CHANGE, 0.0, mode, RiskLevel.HIGH,
            ("triage-unavailable",), TriageIntent.ACTIONABLE)
    work_item.type = art.level
    return StageOutcome.ok("triage", art)


def handle_context(work_item, ctx, now):
    triage = cast(TriageArtifact, work_item.artifacts["triage"])
    handle = ctx.workspace.provision(work_item.id, work_item.repo_ref,
        triage.workspace_mode, branch_for(work_item), base_branch=work_item.base_branch)
    artifact = ctx.gatherer.gather(work_item.requirement, handle)
    decision = AutonomyPolicy().decide_after_context(_with_ctx_artifact(work_item, artifact))
    if decision == "suspend":
        return StageOutcome.suspend(GatePoint.CONTEXT_GATE, "context", artifact)
    if decision == "finish":
        return StageOutcome.finish("context", artifact)
    return StageOutcome.ok("context", artifact)
```
注:`decide_after_context` 读的是 `work_item.artifacts["triage"]`(已存在),不依赖 context 产物,故可直接 `AutonomyPolicy().decide_after_context(work_item)`——去掉 `_with_ctx_artifact` 包装,直接传 `work_item`。import 增 `workspace_mode_for, AutonomyPolicy, StageError, RiskLevel, TaskType, TriageIntent, GatePoint`。

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/application/test_handlers_front.py tests/application/test_handlers_back.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/autodev/application/context.py src/autodev/application/handlers.py tests/application/test_handlers_front.py
git commit -m "feat(app): triage via TriagePort + post-context AutonomyPolicy decision"
```

---

### Task A8: entrypoints —— decide_work_item + resume_target + 薄壳(B4) + create 开关(B3)

**Files:**
- Modify: `src/autodev/application/entrypoints.py`
- Test: `tests/application/test_entrypoints.py`(追加)

**Interfaces:**
- Produces:
  - `resume_target(gate: GatePoint, decision: str) -> WorkflowState`。
  - `decide_work_item(work_item_id, decision: str, repo, engine, now)`(`"proceed"|"close"|"reject"`)。
  - `resume_work_item(work_item_id, approved: bool, repo, engine, now)` 保签名,内部委托(True→proceed, False→reject)。
  - `create_work_item(..., autonomy_enabled: bool = False)`。

- [ ] **Step 1: 写失败测试**

```python
def test_resume_target_context_gate():
    from autodev.application.entrypoints import resume_target
    from autodev.domain.enums import GatePoint as G, WorkflowState as S
    assert resume_target(G.CONTEXT_GATE, "proceed") is S.DESIGN
    assert resume_target(G.CONTEXT_GATE, "close") is S.DONE
    assert resume_target(G.CONTEXT_GATE, "reject") is S.FAILED
    assert resume_target(G.REVIEW_GATE, "proceed") is S.IMPL
    assert resume_target(G.MERGE_GATE, "proceed") is S.DONE


def test_decide_close_context_gate_completes(tmp_path, make_engine):
    # 建工作项 → 驱动到 CONTEXT_GATE（开关关）→ decide close → DONE
    ...  # 仿 test_walking_skeleton 装配，断言 close→DONE、proceed→DESIGN

def test_resume_work_item_bool_shell_still_works(tmp_path, make_engine):
    # approved=True 恢复 REVIEW_GATE → IMPL（旧行为不破）
    ...
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/application/test_entrypoints.py -k "resume_target or decide or shell" -q`
Expected: FAIL(`ImportError: resume_target`)

- [ ] **Step 3: 实现**

`entrypoints.py`:
- 删除 `GATE_RESUME_TARGET` 字典,新增:
```python
def resume_target(gate: GatePoint, decision: str) -> S:
    table = {
        (GatePoint.CONTEXT_GATE, "proceed"): S.DESIGN,
        (GatePoint.CONTEXT_GATE, "close"): S.DONE,
        (GatePoint.REVIEW_GATE, "proceed"): S.IMPL,
        (GatePoint.MERGE_GATE, "proceed"): S.DONE,
    }
    if decision == "reject":
        return S.FAILED
    if (gate, decision) not in table:
        raise InvariantError(f"illegal decision {decision} at {gate.name}")
    return table[(gate, decision)]
```
- 新增 `decide_work_item(work_item_id, decision, repo, engine, now)`:取 wi(须 WAIT_HUMAN)→ `target = resume_target(wi.pending_gate, decision)` → `wi.resume_to(target, ...)` → `target is DONE` 时 `engine._finalize_done(wi)`;`decision=="reject"` 发 `WorkItemFailed`;`repo.save(wi)`。
- `resume_work_item(id, approved, repo, engine, now)` 改为:`decide_work_item(id, "proceed" if approved else "reject", repo, engine, now)`。
- `create_work_item(...)` 增 `autonomy_enabled: bool = False` 透传 `WorkItem.create`。

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/application/test_entrypoints.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/autodev/application/entrypoints.py tests/application/test_entrypoints.py
git commit -m "feat(app): decide_work_item + resume_target(CONTEXT_GATE); create_work_item autonomy_enabled"
```

---

### Task A9: FakeTriage 演示/假件适配器(迁移关键词逻辑 + 意图)

**Files:**
- Modify: `src/autodev/adapters/demo.py`
- Modify: `tests/fakes.py`(re-export 或直接放 FakeTriage,供单测注入)
- Test: `tests/adapters/test_fake_triage.py`

**Interfaces:**
- Produces: `FakeTriage(intent=None)` 实现 `TriagePort`:关键词启发式(迁自原 `TriagePolicy`)产 level/risk/confidence/signals;意图:命中咨询词→CONSULTATION,否则 ACTIONABLE;`intent` 显式传入时覆盖(便于测试)。

- [ ] **Step 1: 写失败测试**

```python
# tests/adapters/test_fake_triage.py
from autodev.adapters.demo import FakeTriage
from autodev.domain.enums import RiskLevel, TriageIntent
from autodev.domain.value_objects import Requirement


def _sig(goal):
    return FakeTriage().classify(Requirement(goal, "r", (), goal))


def test_high_risk_keyword():
    assert _sig("delete old credential tokens").risk is RiskLevel.HIGH


def test_consultation_intent_from_query_words():
    assert _sig("排查登录为什么偶发失败").intent is TriageIntent.CONSULTATION
    assert _sig("how does auth work, please explain").intent is TriageIntent.CONSULTATION


def test_actionable_intent_default():
    assert _sig("add a rate limiter to the api").intent is TriageIntent.ACTIONABLE


def test_explicit_intent_override():
    from autodev.domain.enums import TriageIntent as TI
    sig = FakeTriage(intent=TI.CONSULTATION).classify(Requirement("x", "r", (), "x"))
    assert sig.intent is TI.CONSULTATION
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/adapters/test_fake_triage.py -q`
Expected: FAIL(`ImportError: FakeTriage`)

- [ ] **Step 3: 实现**

`demo.py` 增 `FakeTriage`(把 A5 删掉的关键词表 `_HIGH_RISK_WORDS/_LOW_RISK_WORDS/_SCOPE_WORDS` 迁来 + 意图词 `_CONSULT_WORDS = ("query","question","investigate","explain","how","why","whether","如何","为什么","是否","查询","咨询","排查")`):`classify(requirement)` 依原逻辑算 level/risk/confidence/signals,再判 intent(命中咨询词→CONSULTATION),返回 `TriageSignal`。构造参数 `intent: TriageIntent | None = None` 覆盖。
`tests/fakes.py` 增 `from autodev.adapters.demo import FakeTriage` re-export(供 conftest/各测试统一注入)。

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/adapters/test_fake_triage.py -q`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add src/autodev/adapters/demo.py tests/fakes.py tests/adapters/test_fake_triage.py
git commit -m "feat(adapters): FakeTriage (keyword heuristic + intent) for tests/demo"
```

---

### Task A10: 全仓装配点迁移 —— triage_policy→triage(B6) + 受契约变更影响的测试(B2)

**Files:**
- Modify: `tests/conftest.py`、`tests/webapp/test_service.py`、`tests/webapp/test_project_service.py`、`tests/webapp/test_demo_service.py`、`tests/webapp/test_demo_app.py`、`tests/application/test_engine.py`、`tests/application/test_handlers_back.py`、`tests/application/test_entrypoints.py`、`tests/e2e/test_walking_skeleton.py`、`tests/domain/test_policies.py`、`tests/domain/test_triage_policy.py`(删除)

**Interfaces:**
- Consumes: A5 `TriagePort`/`FakeTriage`、A2 `autonomy_enabled`、A8 `create_work_item(autonomy_enabled=)`。

- [ ] **Step 1: 先跑全套看红点**

Run: `pytest -q 2>&1 | tail -30`
Expected: 一批红(triage_policy 关键字 TypeError、默认关导致 state 停 CONTEXT_GATE)

- [ ] **Step 2: 逐一改装配与断言**

- 所有 `StageContext(..., TriagePolicy(), GatePolicy())` → `FakeTriage()`;关键字 `triage_policy=TriagePolicy()` → `triage=FakeTriage()`。`conftest.py::make_engine` 同改。
- 「要验证下游门/DONE」的用例改为建项时 `autonomy_enabled=True`:
  - `test_project_service.py::test_create_workitem_drives_to_design_and_sets_project_id`
  - `test_demo_service.py`(低风险→DONE、高风险 pending_gate=REVIEW_GATE、approve 两门)
  - `test_demo_app.py`(三个 API 流程)
  - `test_walking_skeleton.py`(三例 `create_work_item(..., autonomy_enabled=True)`)
  - `test_handlers_front.py::test_context_provisions_workspace` → 断言按开关调整
- 删除 `tests/domain/test_triage_policy.py`(逻辑迁至 A9 `test_fake_triage.py`);`test_policies.py::test_triage_picks_workspace_mode` 改为调 `workspace_mode_for`(已在 A5 覆盖,可删此用例)。

- [ ] **Step 3: 跑全套验证绿**

Run: `pytest -q`
Expected: PASS(全绿)

- [ ] **Step 4: lint/type**

Run: `ruff check . && ruff format --check . && mypy src`
Expected: 全 OK(mypy 若报 `artifacts.get("triage")` 需 cast,补 `cast(TriageArtifact, ...)`)

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "refactor(tests): migrate StageContext.triage + autonomy_enabled across suite"
```

---

### Task A11: Web 服务 + API(开关 + /decide 端点)

**Files:**
- Modify: `src/autodev/webapp/service.py`(create_workitem 加 autonomy_enabled;decide_workitem 泛化)
- Modify: `src/autodev/webapp/app.py`(CreateWorkItemRequest.autonomy_enabled;POST /decide;保留 /approve)
- Modify: `src/autodev/webapp/config.py`、`src/autodev/webapp/demo_config.py`(StageContext 注入 triage)
- Modify: `src/autodev/webapp/views.py`(triage.intent 投影 + collect_only 标记)
- Test: `tests/webapp/test_demo_app.py`、`tests/webapp/test_views.py`(追加)

**Interfaces:**
- Produces:
  - `ProjectConsoleService.create_workitem(project_id, goal, autonomy_enabled=False)`。
  - `ProjectConsoleService.decide_workitem(work_item_id, decision) -> WorkItem | None`(委托 `decide_work_item` + 再驱动)。
  - `POST /api/workitems/{id}/decide` body `{action}`;`view_detail` 的 `triage` 含 `intent`;detail 增 `collect_only: bool`。

- [ ] **Step 1: 写失败测试**

```python
def test_disabled_workitem_stops_at_context_gate(client):
    pid = _create_project(client)
    wid = _create_workitem(client, pid, "fix typo in README")  # 默认关
    d = client.get(f"/api/workitems/{wid}").json()
    assert d["state"] == "WAIT_HUMAN"

def test_decide_proceed_then_flows(client):
    pid = _create_project(client)
    wid = _create_workitem(client, pid, "fix typo in README")
    client.post(f"/api/workitems/{wid}/decide", json={"action": "proceed"})
    # 低风险 + 后续放行 → DONE
    assert client.get(f"/api/workitems/{wid}").json()["state"] == "DONE"

def test_enabled_consultation_auto_collect_only(client):
    pid = _create_project(client)
    wid = _create_workitem_enabled(client, pid, "排查登录为什么偶发失败")
    assert client.get(f"/api/workitems/{wid}").json()["state"] == "DONE"
```

（`_create_workitem_enabled` = POST 带 `autonomy_enabled: true`。）

- [ ] **Step 2: 运行验证失败** — `pytest tests/webapp/test_demo_app.py -q` → FAIL。

- [ ] **Step 3: 实现**

- `service.py`:`create_workitem(project_id, goal, autonomy_enabled=False)` 透传 `WorkItem.create(..., autonomy_enabled=autonomy_enabled)`;新增 `decide_workitem(id, decision)` = `decide_work_item(...)` + 再 `_bounded_drive`(仅 proceed)。保留 `approve_workitem` 委托 `decide_workitem`(approved→proceed/reject)。
- `app.py`:`CreateWorkItemRequest` 加 `autonomy_enabled: bool = False`;`create_workitem` 路由透传;新增 `POST /decide`(body `{action}`,400 兜非法);`ConsoleService` Protocol 加 `create_workitem(..., autonomy_enabled)`、`decide_workitem`。
- `config.py`/`demo_config.py`:`StageContext` 的 triage 槽——生产接 `LlmTriageAdapter`(子迭代 B 前先临时接 `FakeTriage` 保证 A 可跑,B 再换)、演示接 `FakeTriage`。
- `views.py`:`view_detail` triage 投影加 `"intent": t.intent.name`;detail 加 `"collect_only": wi.state is S.DONE and "delivery" not in wi.artifacts`;**detail 加 `"pending_gate": wi.pending_gate.name if wi.pending_gate else None`**(供 A12 前端区分 CONTEXT_GATE 三键 vs REVIEW/MERGE 两键)。`view_summary` 加 `"autonomy_enabled": wi.autonomy_enabled`。同步 `frontend types.ts` 的 `WorkItemDetail.pending_gate: string | null`。

- [ ] **Step 4: 运行验证通过** — `pytest tests/webapp -q` → PASS。

- [ ] **Step 5: 提交**

```bash
git add src/autodev/webapp tests/webapp
git commit -m "feat(web): autonomy_enabled + POST /decide + triage.intent projection"
```

---

### Task A12: 前端 —— 开关 / 意图 / CONTEXT_GATE 三键面板

**Files:**
- Modify: `frontend/src/api/types.ts`(TriageView.intent;WorkItemDetail.autonomy_enabled/collect_only;WorkItemSummary.autonomy_enabled)
- Modify: `frontend/src/api/client.ts`(createWorkItem 加 autonomy_enabled;新增 decideWorkItem)
- Modify: `frontend/src/hooks/useCreateWorkItem.ts`、新增 `frontend/src/hooks/useDecideWorkItem.ts`
- Modify: `frontend/src/components/NewWorkItemForm.tsx`(复选框)、`frontend/src/components/TriageBadge.tsx`(意图)
- Modify: `frontend/src/pages/WorkItemDetailPage.tsx`(CONTEXT_GATE 三键)
- Test: `frontend/src/components/TriageBadge.test.tsx`、`NewWorkItemForm.test.tsx`(追加)

**Interfaces:**
- Consumes: A11 的 `/decide`、`autonomy_enabled`、`triage.intent`、`collect_only`。

- [ ] **Step 1: 写失败测试(vitest)**

```tsx
// TriageBadge.test.tsx 追加
it('shows the intent label', () => {
  render(<TriageBadge triage={{ level: 'SMALL_CHANGE', confidence: 0.9, risk: 'LOW',
    signals: [], intent: 'CONSULTATION' }} />)
  expect(screen.getByText(/查询咨询/)).toBeInTheDocument()
})
// NewWorkItemForm.test.tsx 追加：勾选后提交带 autonomy_enabled=true
```

- [ ] **Step 2: 运行验证失败** — `cd frontend && npx vitest run src/components/TriageBadge.test.tsx` → FAIL。

- [ ] **Step 3: 实现**

- `types.ts`:`TriageView` 加 `intent: 'ACTIONABLE' | 'CONSULTATION'`;`WorkItemDetail` 加 `autonomy_enabled: boolean`、`collect_only: boolean`。
- `client.ts`:`createWorkItem(projectId, goal, autonomyEnabled=false)` body 加字段;`decideWorkItem(id, action)` POST `/decide`。
- `useDecideWorkItem.ts`:mutation 调 decideWorkItem + invalidate `['workitem', id]`。
- `NewWorkItemForm.tsx`:加 `<input type="checkbox" id="autonomy-enabled">`「让 AI 自主判断是否继续后续流程」,默认不勾;提交透传。
- `TriageBadge.tsx`:加意图标签(ACTIONABLE→「需落地」,CONSULTATION→「查询咨询」),`data-testid="triage-intent"`。
- `WorkItemDetailPage.tsx`:当 `state==='WAIT_HUMAN'`,依 pending gate 决定按钮——但 detail 无 pending_gate 字段,故用 `collect_only`/上下文启发:CONTEXT_GATE(尚无 design 产物)显示三键「继续后续流程(proceed)/完成仅收集(close)/拒绝(reject)」,REVIEW/MERGE 显示「批准(proceed)/拒绝(reject)」。**为可靠区分,A11 的 view_detail 增 `pending_gate: string | null` 投影**(补到 A11 Step 3)。按钮调 `useDecideWorkItem`。

- [ ] **Step 4: 运行验证通过** — `npm run typecheck && npm run lint && npm run test` → PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src
git commit -m "feat(frontend): autonomy switch + triage intent + CONTEXT_GATE decide panel"
```

---

### Task A13: 文档 + agent-browser E2E + 全门禁

**Files:**
- Modify: `CHANGELOG.md`、`docs/.doc-allowlist.txt`(前端新组件名如需)、`ROADMAP.md`(标注)
- Modify: `tests/e2e/browser_e2e.sh`(新增场景)
- Add: 提交本计划对应的 spec(此时符号已存在,doc-CI 绿)

- [ ] **Step 1: CHANGELOG 加条目**（LLM 分诊子迭代 A:开关/CONTEXT_GATE/仅收集/端口化,列破坏性迁移）。
- [ ] **Step 2: 扩展 E2E 脚本** 三场景:①默认关→停 CONTEXT_GATE→点「继续」→流转/点「完成仅收集」→DONE;②开+咨询("排查…为什么…")→自动 DONE(collect-only,意图徽章=查询咨询);③开+落地高风险→续到 REVIEW 门 risk=HIGH 仍需人审。断言 state 徽章 + intent token + approval/decide 面板存在性,不断浮点/流水线中间态。
- [ ] **Step 3: 跑 E2E** `bash tests/e2e/browser_e2e.sh` → exit 0。
- [ ] **Step 4: 全门禁** 后端 `pytest -q && ruff check . && ruff format --check . && mypy src`;前端四件套;`pytest tests/docs -q`(spec 现在可提交)。
- [ ] **Step 5: 提交** spec + 文档 + E2E。

```bash
git add -A
git commit -m "docs+test(slice2): LLM-triage sub-iteration A spec, changelog, browser E2E"
```

---

# 子迭代 B —— 真实 LlmTriageAdapter(`@live` 门控)

### Task B1: LlmTriageAdapter(直连 API,tool_use 结构化输出,注入 httpx.Client)

**Files:**
- Create: `src/autodev/adapters/triage_llm.py`
- Test: `tests/adapters/test_triage_llm.py`

**Interfaces:**
- Produces: `LlmTriageAdapter(client: httpx.Client, model: str, api_key: str, base_url: str)` 实现 `TriagePort.classify`;非法/失败 → `StageError`。

- [ ] **Step 1: 先读 `claude-api` skill** 取当前最新模型 id、Messages API + tool_use(强制单工具)用法、鉴权头,再定 prompt/schema/max_tokens/超时。
- [ ] **Step 2: 写契约测试(注入假 httpx.Client)** —— 假 client 返回构造好的 tool_use 响应 → 断言解析成 `TriageSignal`(level/risk/intent/confidence/signals);另造 HTTP 500 / 超时 / 缺 tool_use / 非法枚举 → 断言抛 `StageError`。
- [ ] **Step 3: 运行验证失败**。
- [ ] **Step 4: 实现** POST Messages API(tools=[单工具 schema],tool_choice 强制),从 `tool_use` 块取结构化参数;所有异常边界翻译 `StageError`。model/api_key/base_url 由构造注入(默认从环境变量:`AUTODEV_TRIAGE_MODEL` 默认钉定最新 id、`AUTODEV_LLM_API_KEY`、`AUTODEV_LLM_BASE_URL`)。
- [ ] **Step 5: `@pytest.mark.live` 冒烟**(`AUTODEV_LIVE=1` 才跑,真打 API)。
- [ ] **Step 6: 运行验证通过 + 提交**。

### Task B2: 生产接线 + 启动警告

**Files:** Modify `src/autodev/webapp/config.py`

- [ ] `build_env_service` 用 `LlmTriageAdapter`(从环境变量装配 httpx.Client + model);缺 `AUTODEV_LLM_API_KEY` 仅 `warnings.warn`/log,不 fail-fast。
- [ ] 更新「生产端口桩化守卫」测试(triage 现在是 LlmTriageAdapter 而非 FakeTriage;Execution/Verification/Design 仍须为 UnavailableStage)。
- [ ] 提交。

### Task B3: 文档收尾

- [ ] CHANGELOG 加子迭代 B 条目;`docs/.doc-allowlist.txt` 如需;ROADMAP 标注 LLM 分诊落地。提交。

---

## Self-Review（对照 spec）

- **Spec 覆盖**:LLM 分诊(B1/B2)、TriagePort 端口化(A5)、autonomy_enabled(A2/A3/A8/A11/A12)、CONTEXT_GATE + 三态决策(A2/A4/A6/A7)、意图(A1/A9)、失败→挂起(A7)、下游风险门禁不变(未改 GatePolicy,A10 保留其测试)、序列化(A3)、resume 泛化(A8)、前端(A12)、E2E(A13)、A/B 拆分(整体结构)。均有任务对应。
- **Placeholder 扫描**:除 B1 明确「先读 claude-api skill 定稿」(受外部最新模型/API 约束的必要延迟)外,A 段各步含真实代码/命令。
- **类型一致**:`TriageSignal`(level/confidence/risk/intent/signals)、`decide_after_context→str`、`resume_target(gate,decision)→WorkflowState`、`decide_work_item(id,decision,...)`、`FakeTriage(intent=None).classify`——跨任务签名一致。
- **已知依赖顺序**:A4 的 finish 测试依赖 A9 的 FakeTriage(已在任务内注明);A12 需 A11 补 `pending_gate` 投影(已回填到 A11 Step 3)。
