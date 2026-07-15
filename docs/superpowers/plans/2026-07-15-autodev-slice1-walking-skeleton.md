# AutoDev 切片 1 · 行走骨架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用纯领域模型 + 状态机引擎 + 九阶段应用服务 + SQLite 仓储 + 假适配器，打通一个 SmallChange 类型 WorkItem 从创建到 DONE 的完整生命周期，全部领域逻辑有测试覆盖。

**Architecture:** 六边形架构（Ports & Adapters）。核心域（`domain/`）零外部依赖，持有 WorkItem 聚合、领域服务/策略、端口协议、领域事件。应用层（`application/`）用领域服务推进聚合并协调出站端口。本计划的端口用**假适配器**实现（真实 ACL 见计划 2），另加一个真实的 SQLite 仓储适配器。

**Tech Stack:** Python 3.11+，标准库 `dataclasses` / `typing.Protocol` / `enum` / `uuid` / `datetime` / `sqlite3`，测试用 `pytest`。

## Global Constraints

- Python 版本 ≥ 3.11（用到 `Self`、`X | None` 语法）。
- `src/autodev/domain/` 内**不得** import 任何外部系统 SDK 或 `application`/`adapters` 包；只依赖标准库。（职责铁律 1/2）
- 所有出站交互通过 `domain/ports.py` 的 Protocol 端口；实现放 `adapters/` 或测试 `fakes`。
- WorkItem 是唯一聚合根；产物**只进不改**（重复写同一 stage key 抛 `InvariantError`）。
- 状态转移必须合法（非法转移抛 `InvariantError`）；一切重试/回退有硬上限，越界转 `FAILED`。
- 人审 = 挂起为 `WAIT_HUMAN`，经审批事件唤醒。
- 统一语言：WorkItem / Requirement / Triage / Artifact / Gate / AutonomyDial / StageOutcome / FailureKind（禁止同义词）。
- 每个任务结束必须 `pytest` 全绿并 commit。

## File Structure

```
autodev/
  pyproject.toml
  src/autodev/
    __init__.py
    domain/
      __init__.py
      ids.py            # WorkItemId
      enums.py          # TaskType, WorkflowState, WorkspaceMode, GatePoint, FailureKind
      errors.py         # DomainError, InvariantError, StageError
      value_objects.py  # RepoRef, Requirement, Verdict, GateDecision, AutonomyDial, Cost, RetryLedger, RepoStatus, WorkspaceHandle
      artifacts.py      # TriageArtifact..DeliveryArtifact
      outcome.py        # StageOutcome
      events.py         # DomainEvent + 4 具体事件
      work_item.py      # WorkItem 聚合 + StateTransition
      policies.py       # TriagePolicy, GatePolicy, TransitionRules, RetryPolicy, RetryDecision
      ports.py          # Protocol 端口
    application/
      __init__.py
      context.py        # StageContext（聚合所有端口 + 策略）
      handlers.py       # 九阶段处理器 + HANDLERS 注册表
      engine.py         # Engine.advance + run_until_quiescent
      entrypoints.py    # create_work_item / advance_work_item / resume_work_item
    adapters/
      __init__.py
      event_bus.py      # InMemoryEventBus
      memory_repository.py  # InMemoryWorkItemRepository
      sqlite_repository.py  # SqliteWorkItemRepository
  tests/
    __init__.py
    conftest.py
    fakes.py            # 假出站适配器
    domain/ ...
    application/ ...
    adapters/ ...
    e2e/test_walking_skeleton.py
```

---

### Task 1: 项目脚手架

**Files:**
- Create: `autodev/pyproject.toml`
- Create: `autodev/.gitignore`
- Create: `autodev/src/autodev/__init__.py`
- Create: `autodev/tests/__init__.py`
- Test: `autodev/tests/test_sanity.py`

**Interfaces:**
- Produces: 可运行的 `pytest`，包 `autodev` 可 import。

- [ ] **Step 1: 写 pyproject.toml**

```toml
[project]
name = "autodev"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: 建空包文件 + .gitignore**

`src/autodev/__init__.py` 与 `tests/__init__.py` 均为空文件。

`.gitignore`：
```gitignore
venv/
__pycache__/
*.pyc
.pytest_cache/
*.sqlite
*.egg-info/
```
（`*.egg-info/` 是 `pip install -e` 生成的构建元数据，不入库。）

- [ ] **Step 3: 写 sanity 测试**

```python
# tests/test_sanity.py
def test_package_importable():
    import autodev
    assert autodev is not None
```

- [ ] **Step 4: 建 venv 装依赖并跑测试**

Run:
```bash
cd autodev && python3 -m venv venv && . venv/bin/activate && pip install -e '.[dev]' && pytest -q
```
Expected: `1 passed`。

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore src tests && git commit -m "chore: 项目脚手架 + pytest"
```

---

### Task 2: 枚举与标识

**Files:**
- Create: `src/autodev/domain/__init__.py`（空）
- Create: `src/autodev/domain/ids.py`
- Create: `src/autodev/domain/enums.py`
- Test: `tests/domain/test_enums.py`

**Interfaces:**
- Produces:
  - `WorkItemId` 值对象：`WorkItemId.new() -> WorkItemId`；属性 `.value: str`；frozen、可哈希。
  - 枚举 `TaskType{SMALL_CHANGE, MEDIUM_FEATURE, COMPLEX_FEATURE}`
  - `WorkflowState{INTAKE, TRIAGE, CONTEXT, DESIGN, REVIEW, IMPL, ACCEPT, VERIFY, SUBMIT_MR, DONE, WAIT_HUMAN, FAILED}`
  - `WorkspaceMode{WORKTREE, CLONE, CREATE}`
  - `GatePoint{REVIEW_GATE, MERGE_GATE}`
  - `FailureKind{TRANSIENT, LOGIC, FATAL}`

- [ ] **Step 1: 写失败测试**

```python
# tests/domain/__init__.py 也要建为空文件
# tests/domain/test_enums.py
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import (
    TaskType, WorkflowState, WorkspaceMode, GatePoint, FailureKind,
)

def test_work_item_id_is_unique_and_hashable():
    a, b = WorkItemId.new(), WorkItemId.new()
    assert a != b
    assert isinstance(a.value, str) and len(a.value) > 0
    assert len({a, b}) == 2

def test_enum_members_present():
    assert {e.name for e in WorkflowState} >= {
        "INTAKE", "TRIAGE", "CONTEXT", "DESIGN", "REVIEW", "IMPL",
        "ACCEPT", "VERIFY", "SUBMIT_MR", "DONE", "WAIT_HUMAN", "FAILED",
    }
    assert TaskType.SMALL_CHANGE and WorkspaceMode.WORKTREE
    assert GatePoint.REVIEW_GATE and FailureKind.TRANSIENT
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/domain/test_enums.py -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现**

```python
# src/autodev/domain/ids.py
from __future__ import annotations
import uuid
from dataclasses import dataclass

@dataclass(frozen=True)
class WorkItemId:
    value: str

    @classmethod
    def new(cls) -> "WorkItemId":
        return cls(uuid.uuid4().hex)
```

```python
# src/autodev/domain/enums.py
from enum import Enum, auto

class TaskType(Enum):
    SMALL_CHANGE = auto()
    MEDIUM_FEATURE = auto()
    COMPLEX_FEATURE = auto()

class WorkflowState(Enum):
    INTAKE = auto()
    TRIAGE = auto()
    CONTEXT = auto()
    DESIGN = auto()
    REVIEW = auto()
    IMPL = auto()
    ACCEPT = auto()
    VERIFY = auto()
    SUBMIT_MR = auto()
    DONE = auto()
    WAIT_HUMAN = auto()
    FAILED = auto()

class WorkspaceMode(Enum):
    WORKTREE = auto()
    CLONE = auto()
    CREATE = auto()

class GatePoint(Enum):
    REVIEW_GATE = auto()
    MERGE_GATE = auto()

class FailureKind(Enum):
    TRANSIENT = auto()
    LOGIC = auto()
    FATAL = auto()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/domain/test_enums.py -q`
Expected: `2 passed`。

- [ ] **Step 5: Commit**

```bash
git add src/autodev/domain tests/domain && git commit -m "feat(domain): 枚举与 WorkItemId"
```

---

### Task 3: 领域错误 + 值对象

**Files:**
- Create: `src/autodev/domain/errors.py`
- Create: `src/autodev/domain/value_objects.py`
- Test: `tests/domain/test_value_objects.py`

**Interfaces:**
- Consumes: `enums`（TaskType, GatePoint, FailureKind）。
- Produces:
  - `DomainError(Exception)`；`InvariantError(DomainError)`；`StageError(DomainError)` 带 `.failure_kind: FailureKind` 与 `.message: str`，构造 `StageError(FailureKind.LOGIC, "msg")`。
  - `RepoRef(name: str)` frozen。
  - `Requirement(goal: str, target_repo: str, acceptance_hints: tuple[str, ...], raw_text: str)` frozen；`.is_complete() -> bool`（goal 与 target_repo 均非空）。
  - `Verdict(passed: bool, reasons: tuple[str, ...])` frozen。
  - `GateDecision(needs_human: bool, reason: str)` frozen。
  - `RepoStatus(exists_local: bool, exists_remote: bool)` frozen。
  - `WorkspaceHandle(worktree_path: str, branch: str)` frozen。
  - `Cost(tokens: int)` frozen；`.plus(n: int) -> Cost`。
  - `RetryLedger(counts: frozenset[tuple[str, int]] = ...)`；`.count(key: str) -> int`；`.incremented(key: str) -> RetryLedger`（immutable）。默认空。
  - `AutonomyDial(auto_gates: frozenset[tuple[TaskType, str, GatePoint]])`；`.needs_human(task_type: TaskType, repo: str, gate: GatePoint) -> bool`（不在 auto_gates 则默认 True）；`AutonomyDial.all_human() -> AutonomyDial`。

- [ ] **Step 1: 写失败测试**

```python
# tests/domain/test_value_objects.py
import pytest
from autodev.domain.enums import TaskType, GatePoint, FailureKind
from autodev.domain.errors import DomainError, InvariantError, StageError
from autodev.domain.value_objects import (
    RepoRef, Requirement, Verdict, GateDecision, RepoStatus,
    WorkspaceHandle, Cost, RetryLedger, AutonomyDial,
)

def test_stage_error_carries_kind():
    e = StageError(FailureKind.LOGIC, "boom")
    assert e.failure_kind is FailureKind.LOGIC and e.message == "boom"
    assert isinstance(e, DomainError)

def test_requirement_completeness():
    assert Requirement("fix typo", "repo-a", (), "raw").is_complete()
    assert not Requirement("", "repo-a", (), "raw").is_complete()
    assert not Requirement("goal", "", (), "raw").is_complete()

def test_cost_and_retry_ledger_are_immutable():
    c = Cost(0).plus(10).plus(5)
    assert c.tokens == 15
    led = RetryLedger().incremented("k").incremented("k")
    assert led.count("k") == 2 and led.count("other") == 0

def test_autonomy_dial_defaults_to_human():
    dial = AutonomyDial.all_human()
    assert dial.needs_human(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)
    auto = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    assert not auto.needs_human(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)
    assert auto.needs_human(TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/domain/test_value_objects.py -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现**

```python
# src/autodev/domain/errors.py
from __future__ import annotations
from autodev.domain.enums import FailureKind

class DomainError(Exception):
    pass

class InvariantError(DomainError):
    pass

class StageError(DomainError):
    def __init__(self, failure_kind: FailureKind, message: str) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind
        self.message = message
```

```python
# src/autodev/domain/value_objects.py
from __future__ import annotations
from dataclasses import dataclass, field
from autodev.domain.enums import TaskType, GatePoint

@dataclass(frozen=True)
class RepoRef:
    name: str

@dataclass(frozen=True)
class Requirement:
    goal: str
    target_repo: str
    acceptance_hints: tuple[str, ...]
    raw_text: str

    def is_complete(self) -> bool:
        return bool(self.goal) and bool(self.target_repo)

@dataclass(frozen=True)
class Verdict:
    passed: bool
    reasons: tuple[str, ...]

@dataclass(frozen=True)
class GateDecision:
    needs_human: bool
    reason: str

@dataclass(frozen=True)
class RepoStatus:
    exists_local: bool
    exists_remote: bool

@dataclass(frozen=True)
class WorkspaceHandle:
    worktree_path: str
    branch: str

@dataclass(frozen=True)
class Cost:
    tokens: int = 0

    def plus(self, n: int) -> "Cost":
        return Cost(self.tokens + n)

@dataclass(frozen=True)
class RetryLedger:
    counts: frozenset[tuple[str, int]] = field(default_factory=frozenset)

    def _as_dict(self) -> dict[str, int]:
        return dict(self.counts)

    def count(self, key: str) -> int:
        return self._as_dict().get(key, 0)

    def incremented(self, key: str) -> "RetryLedger":
        d = self._as_dict()
        d[key] = d.get(key, 0) + 1
        return RetryLedger(frozenset(d.items()))

@dataclass(frozen=True)
class AutonomyDial:
    auto_gates: frozenset[tuple[TaskType, str, GatePoint]]

    @classmethod
    def all_human(cls) -> "AutonomyDial":
        return cls(frozenset())

    def needs_human(self, task_type: TaskType, repo: str, gate: GatePoint) -> bool:
        return (task_type, repo, gate) not in self.auto_gates
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/domain/test_value_objects.py -q`
Expected: `4 passed`。

- [ ] **Step 5: Commit**

```bash
git add src/autodev/domain tests/domain && git commit -m "feat(domain): 错误类型与值对象"
```

---

### Task 4: 产物 + StageOutcome + 领域事件

**Files:**
- Create: `src/autodev/domain/artifacts.py`
- Create: `src/autodev/domain/outcome.py`
- Create: `src/autodev/domain/events.py`
- Test: `tests/domain/test_outcome.py`

**Interfaces:**
- Consumes: `enums`（GatePoint, FailureKind, TaskType, WorkspaceMode）、`value_objects`（Verdict）、`ids`（WorkItemId）。
- Produces：
  - 产物 frozen dataclasses：
    - `TriageArtifact(level: TaskType, confidence: float, workspace_mode: WorkspaceMode)`
    - `ContextArtifact(worktree_path: str, branch: str, relevant_files: tuple[str, ...], summary: str)`
    - `DesignArtifact(change_summary: str, target_files: tuple[str, ...])`
    - `ReviewArtifact(approved: bool, comments: tuple[str, ...])`
    - `ImplArtifact(diff: str, test_passed: bool, summary: str)`
    - `AcceptanceArtifact(criteria: tuple[str, ...])`
    - `VerificationArtifact(verdict: Verdict, details: tuple[str, ...])`
    - `DeliveryArtifact(mr_url: str, branch: str)`
  - `StageOutcome`（frozen）：字段 `kind: str`（"success"|"suspend"|"failure"）、`artifact_key: str | None`、`artifact: object | None`、`gate_point: GatePoint | None`、`failure_kind: FailureKind | None`、`message: str`。类方法：
    - `StageOutcome.ok(artifact_key: str | None = None, artifact: object | None = None)`
    - `StageOutcome.suspend(gate_point: GatePoint, artifact_key: str | None = None, artifact: object | None = None)`
    - `StageOutcome.fail(failure_kind: FailureKind, message: str)`
  - 领域事件：`DomainEvent(work_item_id: WorkItemId)` 基类（frozen）；子类 `WorkItemCreated`、`HumanApprovalRequested(gate_point: GatePoint)`、`WorkItemCompleted(mr_url: str)`、`WorkItemFailed(state_name: str, reason: str)`。

- [ ] **Step 1: 写失败测试**

```python
# tests/domain/test_outcome.py
from autodev.domain.enums import GatePoint, FailureKind
from autodev.domain.outcome import StageOutcome
from autodev.domain.artifacts import DesignArtifact
from autodev.domain.events import WorkItemCreated, HumanApprovalRequested
from autodev.domain.ids import WorkItemId

def test_stage_outcome_variants():
    a = DesignArtifact("fix typo", ("a.py",))
    ok = StageOutcome.ok("design", a)
    assert ok.kind == "success" and ok.artifact_key == "design" and ok.artifact is a
    sus = StageOutcome.suspend(GatePoint.REVIEW_GATE, "review", a)
    assert sus.kind == "suspend" and sus.gate_point is GatePoint.REVIEW_GATE
    fail = StageOutcome.fail(FailureKind.LOGIC, "nope")
    assert fail.kind == "failure" and fail.failure_kind is FailureKind.LOGIC

def test_events_carry_work_item_id():
    wid = WorkItemId.new()
    assert WorkItemCreated(wid).work_item_id == wid
    assert HumanApprovalRequested(wid, GatePoint.MERGE_GATE).gate_point is GatePoint.MERGE_GATE
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/domain/test_outcome.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现**

```python
# src/autodev/domain/artifacts.py
from __future__ import annotations
from dataclasses import dataclass
from autodev.domain.enums import TaskType, WorkspaceMode
from autodev.domain.value_objects import Verdict

@dataclass(frozen=True)
class TriageArtifact:
    level: TaskType
    confidence: float
    workspace_mode: WorkspaceMode

@dataclass(frozen=True)
class ContextArtifact:
    worktree_path: str
    branch: str
    relevant_files: tuple[str, ...]
    summary: str

@dataclass(frozen=True)
class DesignArtifact:
    change_summary: str
    target_files: tuple[str, ...]

@dataclass(frozen=True)
class ReviewArtifact:
    approved: bool
    comments: tuple[str, ...]

@dataclass(frozen=True)
class ImplArtifact:
    diff: str
    test_passed: bool
    summary: str

@dataclass(frozen=True)
class AcceptanceArtifact:
    criteria: tuple[str, ...]

@dataclass(frozen=True)
class VerificationArtifact:
    verdict: Verdict
    details: tuple[str, ...]

@dataclass(frozen=True)
class DeliveryArtifact:
    mr_url: str
    branch: str
```

```python
# src/autodev/domain/outcome.py
from __future__ import annotations
from dataclasses import dataclass
from autodev.domain.enums import GatePoint, FailureKind

@dataclass(frozen=True)
class StageOutcome:
    kind: str
    artifact_key: str | None = None
    artifact: object | None = None
    gate_point: GatePoint | None = None
    failure_kind: FailureKind | None = None
    message: str = ""

    @classmethod
    def ok(cls, artifact_key: str | None = None, artifact: object | None = None) -> "StageOutcome":
        return cls("success", artifact_key=artifact_key, artifact=artifact)

    @classmethod
    def suspend(cls, gate_point: GatePoint, artifact_key: str | None = None,
                artifact: object | None = None) -> "StageOutcome":
        return cls("suspend", artifact_key=artifact_key, artifact=artifact, gate_point=gate_point)

    @classmethod
    def fail(cls, failure_kind: FailureKind, message: str) -> "StageOutcome":
        return cls("failure", failure_kind=failure_kind, message=message)
```

```python
# src/autodev/domain/events.py
from __future__ import annotations
from dataclasses import dataclass
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import GatePoint

@dataclass(frozen=True)
class DomainEvent:
    work_item_id: WorkItemId

@dataclass(frozen=True)
class WorkItemCreated(DomainEvent):
    pass

@dataclass(frozen=True)
class HumanApprovalRequested(DomainEvent):
    gate_point: GatePoint

@dataclass(frozen=True)
class WorkItemCompleted(DomainEvent):
    mr_url: str

@dataclass(frozen=True)
class WorkItemFailed(DomainEvent):
    state_name: str
    reason: str
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/domain/test_outcome.py -q`
Expected: `2 passed`。

- [ ] **Step 5: Commit**

```bash
git add src/autodev/domain tests/domain && git commit -m "feat(domain): 产物、StageOutcome、领域事件"
```

---

### Task 5: WorkItem 聚合

**Files:**
- Create: `src/autodev/domain/work_item.py`
- Test: `tests/domain/test_work_item.py`

**Interfaces:**
- Consumes: `ids`、`enums`、`errors`、`value_objects`、`artifacts`。
- Produces：
  - `StateTransition(from_state: WorkflowState, to_state: WorkflowState, reason: str, at: datetime)` frozen。
  - `WorkItem` 聚合（可变 dataclass），字段：`id: WorkItemId`、`repo_ref: RepoRef`、`requirement: Requirement`、`autonomy_dial: AutonomyDial`、`type: TaskType | None = None`、`state: WorkflowState = INTAKE`、`artifacts: dict[str, object]`、`history: list[StateTransition]`、`retry_ledger: RetryLedger`、`cost: Cost`、`pending_gate: GatePoint | None = None`、`created_at/updated_at: datetime`。
  - 类方法 `WorkItem.create(id, repo_ref, requirement, autonomy_dial, now) -> WorkItem`。
  - 方法：
    - `add_artifact(key: str, artifact: object) -> None`（重复 key 抛 `InvariantError`）
    - `transition_to(new_state: WorkflowState, reason: str, now: datetime) -> None`（非法转移抛 `InvariantError`）
    - `suspend(gate_point: GatePoint, reason: str, now: datetime) -> None`
    - `resume_to(target: WorkflowState, reason: str, now: datetime) -> None`（仅当 state==WAIT_HUMAN）
    - `record_retry(key: str) -> None`
    - `add_cost(tokens: int) -> None`
    - `is_runnable() -> bool`（state 不属于 {DONE, FAILED, WAIT_HUMAN}）
  - 类常量 `WorkItem.ALLOWED: dict[WorkflowState, frozenset[WorkflowState]]`。

- [ ] **Step 1: 写失败测试**

```python
# tests/domain/test_work_item.py
from datetime import datetime
import pytest
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState as S, GatePoint, TaskType
from autodev.domain.errors import InvariantError
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial
from autodev.domain.artifacts import DesignArtifact
from autodev.domain.work_item import WorkItem

NOW = datetime(2026, 7, 15, 12, 0, 0)

def _wi():
    return WorkItem.create(
        WorkItemId.new(), RepoRef("repo-a"),
        Requirement("fix typo", "repo-a", (), "raw"),
        AutonomyDial.all_human(), NOW,
    )

def test_starts_in_intake_and_runnable():
    wi = _wi()
    assert wi.state is S.INTAKE and wi.is_runnable()

def test_artifacts_are_append_only():
    wi = _wi()
    wi.add_artifact("design", DesignArtifact("x", ()))
    with pytest.raises(InvariantError):
        wi.add_artifact("design", DesignArtifact("y", ()))

def test_illegal_transition_rejected():
    wi = _wi()
    with pytest.raises(InvariantError):
        wi.transition_to(S.DONE, "skip", NOW)

def test_legal_linear_transition_records_history():
    wi = _wi()
    wi.transition_to(S.TRIAGE, "ok", NOW)
    assert wi.state is S.TRIAGE and wi.history[-1].to_state is S.TRIAGE

def test_suspend_and_resume():
    wi = _wi()
    for s in [S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW]:
        wi.transition_to(s, "ok", NOW)
    wi.suspend(GatePoint.REVIEW_GATE, "need human", NOW)
    assert wi.state is S.WAIT_HUMAN and wi.pending_gate is GatePoint.REVIEW_GATE
    assert not wi.is_runnable()
    wi.resume_to(S.IMPL, "approved", NOW)
    assert wi.state is S.IMPL and wi.pending_gate is None

def test_any_state_can_fail():
    wi = _wi()
    wi.transition_to(S.FAILED, "fatal", NOW)
    assert wi.state is S.FAILED and not wi.is_runnable()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/domain/test_work_item.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现**

```python
# src/autodev/domain/work_item.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState as S, WorkflowState, TaskType, GatePoint
from autodev.domain.errors import InvariantError
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial, RetryLedger, Cost

@dataclass(frozen=True)
class StateTransition:
    from_state: WorkflowState
    to_state: WorkflowState
    reason: str
    at: datetime

_TERMINAL = {S.DONE, S.FAILED}

def _build_allowed() -> dict[WorkflowState, frozenset[WorkflowState]]:
    linear = [S.INTAKE, S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW,
              S.IMPL, S.ACCEPT, S.VERIFY, S.SUBMIT_MR, S.DONE]
    allowed: dict[WorkflowState, set[WorkflowState]] = {s: set() for s in S}
    for a, b in zip(linear, linear[1:]):
        allowed[a].add(b)
    # 回退
    allowed[S.VERIFY].add(S.IMPL)
    allowed[S.REVIEW].add(S.DESIGN)
    # 人审挂起
    allowed[S.REVIEW].add(S.WAIT_HUMAN)
    allowed[S.SUBMIT_MR].add(S.WAIT_HUMAN)
    allowed[S.WAIT_HUMAN].update({S.IMPL, S.DONE})
    # 任意非终态可失败
    for s in S:
        if s not in _TERMINAL:
            allowed[s].add(S.FAILED)
    return {s: frozenset(v) for s, v in allowed.items()}

@dataclass
class WorkItem:
    id: WorkItemId
    repo_ref: RepoRef
    requirement: Requirement
    autonomy_dial: AutonomyDial
    type: TaskType | None = None
    state: WorkflowState = S.INTAKE
    artifacts: dict[str, object] = field(default_factory=dict)
    history: list[StateTransition] = field(default_factory=list)
    retry_ledger: RetryLedger = field(default_factory=RetryLedger)
    cost: Cost = field(default_factory=Cost)
    pending_gate: GatePoint | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    ALLOWED = _build_allowed()

    @classmethod
    def create(cls, id: WorkItemId, repo_ref: RepoRef, requirement: Requirement,
               autonomy_dial: AutonomyDial, now: datetime) -> "WorkItem":
        return cls(id=id, repo_ref=repo_ref, requirement=requirement,
                   autonomy_dial=autonomy_dial, created_at=now, updated_at=now)

    def is_runnable(self) -> bool:
        return self.state not in (S.DONE, S.FAILED, S.WAIT_HUMAN)

    def add_artifact(self, key: str, artifact: object) -> None:
        if key in self.artifacts:
            raise InvariantError(f"artifact '{key}' already exists (append-only)")
        self.artifacts[key] = artifact

    def transition_to(self, new_state: WorkflowState, reason: str, now: datetime) -> None:
        if new_state not in self.ALLOWED[self.state]:
            raise InvariantError(f"illegal transition {self.state.name} -> {new_state.name}")
        self.history.append(StateTransition(self.state, new_state, reason, now))
        self.state = new_state
        self.updated_at = now

    def suspend(self, gate_point: GatePoint, reason: str, now: datetime) -> None:
        self.transition_to(S.WAIT_HUMAN, reason, now)
        self.pending_gate = gate_point

    def resume_to(self, target: WorkflowState, reason: str, now: datetime) -> None:
        if self.state is not S.WAIT_HUMAN:
            raise InvariantError("resume requires WAIT_HUMAN state")
        self.transition_to(target, reason, now)
        self.pending_gate = None

    def record_retry(self, key: str) -> None:
        self.retry_ledger = self.retry_ledger.incremented(key)

    def add_cost(self, tokens: int) -> None:
        self.cost = self.cost.plus(tokens)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/domain/test_work_item.py -q`
Expected: `6 passed`。

- [ ] **Step 5: Commit**

```bash
git add src/autodev/domain tests/domain && git commit -m "feat(domain): WorkItem 聚合与不变式"
```

---

### Task 6: 领域策略

**Files:**
- Create: `src/autodev/domain/policies.py`
- Test: `tests/domain/test_policies.py`

**Interfaces:**
- Consumes: `enums`、`value_objects`、`artifacts`、`work_item`。
- Produces：
  - `TriagePolicy.triage(requirement: Requirement, status: RepoStatus) -> TriageArtifact`
    （切片 1：level 恒为 `SMALL_CHANGE`，confidence=0.9；mode：local→WORKTREE，else remote→CLONE，else CREATE）。
  - `GatePolicy.decide(work_item: WorkItem, gate: GatePoint) -> GateDecision`
    （用 `work_item.type` 与 `work_item.repo_ref.name` 查 `autonomy_dial`；`work_item.type` 为 None 视为需人审）。
  - `TransitionRules.next_state(state: WorkflowState) -> WorkflowState`（线性推进映射；终态无后继抛 `InvariantError`）。
  - `RetryDecision(action: str, target: WorkflowState | None, key: str)`；`action ∈ {"retry","rollback","fail"}`。
  - `RetryPolicy.decide(state: WorkflowState, failure_kind: FailureKind, ledger: RetryLedger) -> RetryDecision`。常量 `RetryPolicy.CAP = 3`，`RetryPolicy.ROLLBACK_TARGET = {VERIFY: IMPL, REVIEW: DESIGN}`。

- [ ] **Step 1: 写失败测试**

```python
# tests/domain/test_policies.py
from datetime import datetime
from autodev.domain.enums import WorkflowState as S, WorkspaceMode, TaskType, GatePoint, FailureKind
from autodev.domain.value_objects import (
    RepoRef, Requirement, RepoStatus, AutonomyDial, RetryLedger,
)
from autodev.domain.work_item import WorkItem
from autodev.domain.policies import TriagePolicy, GatePolicy, TransitionRules, RetryPolicy

NOW = datetime(2026, 7, 15)

def _wi(dial):
    wi = WorkItem.create(__import__("autodev.domain.ids", fromlist=["WorkItemId"]).WorkItemId.new(),
                         RepoRef("repo-a"), Requirement("g", "repo-a", (), "r"), dial, NOW)
    wi.type = TaskType.SMALL_CHANGE
    return wi

def test_triage_picks_workspace_mode():
    req = Requirement("g", "repo-a", (), "r")
    assert TriagePolicy().triage(req, RepoStatus(True, True)).workspace_mode is WorkspaceMode.WORKTREE
    assert TriagePolicy().triage(req, RepoStatus(False, True)).workspace_mode is WorkspaceMode.CLONE
    assert TriagePolicy().triage(req, RepoStatus(False, False)).workspace_mode is WorkspaceMode.CREATE
    assert TriagePolicy().triage(req, RepoStatus(True, True)).level is TaskType.SMALL_CHANGE

def test_gate_policy_reads_dial():
    human = GatePolicy().decide(_wi(AutonomyDial.all_human()), GatePoint.REVIEW_GATE)
    assert human.needs_human
    auto_dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    assert not GatePolicy().decide(_wi(auto_dial), GatePoint.REVIEW_GATE).needs_human

def test_transition_rules_linear():
    assert TransitionRules().next_state(S.INTAKE) is S.TRIAGE
    assert TransitionRules().next_state(S.SUBMIT_MR) is S.DONE

def test_retry_policy_transient_then_fail():
    p = RetryPolicy()
    led = RetryLedger()
    d = p.decide(S.CONTEXT, FailureKind.TRANSIENT, led)
    assert d.action == "retry" and d.target is S.CONTEXT
    led = led.incremented(d.key).incremented(d.key).incremented(d.key)
    assert p.decide(S.CONTEXT, FailureKind.TRANSIENT, led).action == "fail"

def test_retry_policy_logic_rollback_and_fatal():
    p = RetryPolicy()
    d = p.decide(S.VERIFY, FailureKind.LOGIC, RetryLedger())
    assert d.action == "rollback" and d.target is S.IMPL
    # 无回退目标的 logic 失败直接 fail
    assert p.decide(S.CONTEXT, FailureKind.LOGIC, RetryLedger()).action == "fail"
    assert p.decide(S.CONTEXT, FailureKind.FATAL, RetryLedger()).action == "fail"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/domain/test_policies.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现**

```python
# src/autodev/domain/policies.py
from __future__ import annotations
from dataclasses import dataclass
from autodev.domain.enums import (
    WorkflowState as S, WorkflowState, WorkspaceMode, TaskType, GatePoint, FailureKind,
)
from autodev.domain.errors import InvariantError
from autodev.domain.value_objects import Requirement, RepoStatus, RetryLedger, GateDecision
from autodev.domain.artifacts import TriageArtifact
from autodev.domain.work_item import WorkItem

class TriagePolicy:
    def triage(self, requirement: Requirement, status: RepoStatus) -> TriageArtifact:
        if status.exists_local:
            mode = WorkspaceMode.WORKTREE
        elif status.exists_remote:
            mode = WorkspaceMode.CLONE
        else:
            mode = WorkspaceMode.CREATE
        return TriageArtifact(level=TaskType.SMALL_CHANGE, confidence=0.9, workspace_mode=mode)

class GatePolicy:
    def decide(self, work_item: WorkItem, gate: GatePoint) -> GateDecision:
        if work_item.type is None:
            return GateDecision(True, "type unknown -> require human")
        needs = work_item.autonomy_dial.needs_human(work_item.type, work_item.repo_ref.name, gate)
        return GateDecision(needs, "per autonomy dial")

_NEXT = {
    S.INTAKE: S.TRIAGE, S.TRIAGE: S.CONTEXT, S.CONTEXT: S.DESIGN,
    S.DESIGN: S.REVIEW, S.REVIEW: S.IMPL, S.IMPL: S.ACCEPT,
    S.ACCEPT: S.VERIFY, S.VERIFY: S.SUBMIT_MR, S.SUBMIT_MR: S.DONE,
}

class TransitionRules:
    def next_state(self, state: WorkflowState) -> WorkflowState:
        if state not in _NEXT:
            raise InvariantError(f"no linear successor for {state.name}")
        return _NEXT[state]

@dataclass(frozen=True)
class RetryDecision:
    action: str  # "retry" | "rollback" | "fail"
    target: WorkflowState | None
    key: str

class RetryPolicy:
    CAP = 3
    ROLLBACK_TARGET = {S.VERIFY: S.IMPL, S.REVIEW: S.DESIGN}

    def decide(self, state: WorkflowState, failure_kind: FailureKind,
               ledger: RetryLedger) -> RetryDecision:
        if failure_kind is FailureKind.FATAL:
            return RetryDecision("fail", None, "")
        if failure_kind is FailureKind.TRANSIENT:
            key = f"{state.name}:transient"
            if ledger.count(key) >= self.CAP:
                return RetryDecision("fail", None, key)
            return RetryDecision("retry", state, key)
        # LOGIC
        target = self.ROLLBACK_TARGET.get(state)
        if target is None:
            return RetryDecision("fail", None, f"{state.name}:logic")
        key = f"{state.name}:logic"
        if ledger.count(key) >= self.CAP:
            return RetryDecision("fail", None, key)
        return RetryDecision("rollback", target, key)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/domain/test_policies.py -q`
Expected: `5 passed`。

- [ ] **Step 5: Commit**

```bash
git add src/autodev/domain tests/domain && git commit -m "feat(domain): 分诊/门禁/转移/重试策略"
```

---

### Task 7: 出站端口 + 假适配器

**Files:**
- Create: `src/autodev/domain/ports.py`
- Create: `tests/fakes.py`
- Test: `tests/test_fakes.py`

**Interfaces:**
- Consumes: `value_objects`、`artifacts`、`ids`、`enums`、`work_item`、`events`。
- Produces（Protocol，全部用领域语言）：
  - `WorkspacePort`：
    - `repo_status(repo: RepoRef) -> RepoStatus`
    - `provision(work_item_id: WorkItemId, repo: RepoRef, mode: WorkspaceMode, branch: str) -> WorkspaceHandle`
    - `cleanup(handle: WorkspaceHandle) -> None`
  - `ContextPort.gather(requirement: Requirement, handle: WorkspaceHandle) -> ContextArtifact`
  - `DesignPort.propose(requirement: Requirement, context: ContextArtifact) -> DesignArtifact`
  - `ReviewPort.review(design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact`
  - `ExecutionPort.implement(design: DesignArtifact, handle: WorkspaceHandle) -> ImplArtifact`
  - `VerificationPort.verify(criteria: AcceptanceArtifact, handle: WorkspaceHandle) -> VerificationArtifact`
  - `DeliveryPort.submit(requirement: Requirement, design: DesignArtifact, handle: WorkspaceHandle) -> DeliveryArtifact`
  - `WorkItemRepository`：`save(work_item: WorkItem) -> None`；`get(work_item_id: WorkItemId) -> WorkItem`；`claim_runnable() -> list[WorkItem]`
  - `EventPublisher.publish(event: DomainEvent) -> None`
- Produces（`tests/fakes.py`）：可配置的假实现 `FakeWorkspace`、`FakeContext`、`FakeDesign`、`FakeReview(approved=True)`、`FakeExecution(test_passed=True)`、`FakeVerification(passed=True)`、`FakeDelivery`、`RecordingPublisher(events: list)`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_fakes.py
from autodev.domain.value_objects import RepoRef, Requirement
from autodev.domain.enums import WorkspaceMode
from autodev.domain.ids import WorkItemId
from autodev.domain.artifacts import AcceptanceArtifact
from tests.fakes import (
    FakeWorkspace, FakeContext, FakeDesign, FakeReview,
    FakeExecution, FakeVerification, FakeDelivery, RecordingPublisher,
)

def test_fakes_satisfy_ports():
    ws = FakeWorkspace(local=True)
    st = ws.repo_status(RepoRef("repo-a"))
    assert st.exists_local
    h = ws.provision(WorkItemId.new(), RepoRef("repo-a"), WorkspaceMode.WORKTREE, "br")
    assert h.branch == "br"
    ctx = FakeContext().gather(Requirement("g", "repo-a", (), "r"), h)
    d = FakeDesign().propose(Requirement("g", "repo-a", (), "r"), ctx)
    assert FakeReview(approved=True).review(d, ctx).approved
    impl = FakeExecution(test_passed=True).implement(d, h)
    assert impl.test_passed
    ver = FakeVerification(passed=True).verify(AcceptanceArtifact(("c",)), h)
    assert ver.verdict.passed
    dv = FakeDelivery().submit(Requirement("g", "repo-a", (), "r"), d, h)
    assert dv.mr_url

def test_recording_publisher_collects():
    pub = RecordingPublisher()
    from autodev.domain.events import WorkItemCreated
    wid = WorkItemId.new()
    pub.publish(WorkItemCreated(wid))
    assert pub.events and pub.events[0].work_item_id == wid
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_fakes.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现端口**

```python
# src/autodev/domain/ports.py
from __future__ import annotations
from typing import Protocol
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkspaceMode
from autodev.domain.value_objects import (
    RepoRef, Requirement, RepoStatus, WorkspaceHandle,
)
from autodev.domain.artifacts import (
    ContextArtifact, DesignArtifact, ReviewArtifact, ImplArtifact,
    AcceptanceArtifact, VerificationArtifact, DeliveryArtifact,
)
from autodev.domain.events import DomainEvent
from autodev.domain.work_item import WorkItem

class WorkspacePort(Protocol):
    def repo_status(self, repo: RepoRef) -> RepoStatus: ...
    def provision(self, work_item_id: WorkItemId, repo: RepoRef,
                  mode: WorkspaceMode, branch: str) -> WorkspaceHandle: ...
    def cleanup(self, handle: WorkspaceHandle) -> None: ...

class ContextPort(Protocol):
    def gather(self, requirement: Requirement, handle: WorkspaceHandle) -> ContextArtifact: ...

class DesignPort(Protocol):
    def propose(self, requirement: Requirement, context: ContextArtifact) -> DesignArtifact: ...

class ReviewPort(Protocol):
    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact: ...

class ExecutionPort(Protocol):
    def implement(self, design: DesignArtifact, handle: WorkspaceHandle) -> ImplArtifact: ...

class VerificationPort(Protocol):
    def verify(self, criteria: AcceptanceArtifact, handle: WorkspaceHandle) -> VerificationArtifact: ...

class DeliveryPort(Protocol):
    def submit(self, requirement: Requirement, design: DesignArtifact,
               handle: WorkspaceHandle) -> DeliveryArtifact: ...

class WorkItemRepository(Protocol):
    def save(self, work_item: WorkItem) -> None: ...
    def get(self, work_item_id: WorkItemId) -> WorkItem: ...
    def claim_runnable(self) -> list[WorkItem]: ...

class EventPublisher(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
```

- [ ] **Step 4: 实现假适配器**

```python
# tests/fakes.py
from __future__ import annotations
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkspaceMode
from autodev.domain.value_objects import (
    RepoRef, Requirement, RepoStatus, WorkspaceHandle, Verdict,
)
from autodev.domain.artifacts import (
    ContextArtifact, DesignArtifact, ReviewArtifact, ImplArtifact,
    AcceptanceArtifact, VerificationArtifact, DeliveryArtifact,
)
from autodev.domain.events import DomainEvent

class FakeWorkspace:
    def __init__(self, local: bool = True, remote: bool = True):
        self.local, self.remote = local, remote
        self.cleaned: list[str] = []
    def repo_status(self, repo: RepoRef) -> RepoStatus:
        return RepoStatus(self.local, self.remote)
    def provision(self, work_item_id: WorkItemId, repo: RepoRef,
                  mode: WorkspaceMode, branch: str) -> WorkspaceHandle:
        return WorkspaceHandle(f"/tmp/{repo.name}/{work_item_id.value[:8]}", branch)
    def cleanup(self, handle: WorkspaceHandle) -> None:
        self.cleaned.append(handle.worktree_path)

class FakeContext:
    def gather(self, requirement: Requirement, handle: WorkspaceHandle) -> ContextArtifact:
        return ContextArtifact(handle.worktree_path, handle.branch, ("app.py",), "fake context")

class FakeDesign:
    def propose(self, requirement: Requirement, context: ContextArtifact) -> DesignArtifact:
        return DesignArtifact(f"do: {requirement.goal}", ("app.py",))

class FakeReview:
    def __init__(self, approved: bool = True):
        self.approved = approved
    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact:
        return ReviewArtifact(self.approved, () if self.approved else ("rejected",))

class FakeExecution:
    def __init__(self, test_passed: bool = True):
        self.test_passed = test_passed
        self.calls = 0
    def implement(self, design: DesignArtifact, handle: WorkspaceHandle) -> ImplArtifact:
        self.calls += 1
        return ImplArtifact("--- diff ---", self.test_passed, "fake impl")

class FakeVerification:
    def __init__(self, passed: bool = True):
        self.passed = passed
    def verify(self, criteria: AcceptanceArtifact, handle: WorkspaceHandle) -> VerificationArtifact:
        return VerificationArtifact(Verdict(self.passed, () if self.passed else ("tests failed",)),
                                    ("ran fake checks",))

class FakeDelivery:
    def submit(self, requirement: Requirement, design: DesignArtifact,
               handle: WorkspaceHandle) -> DeliveryArtifact:
        return DeliveryArtifact(f"https://gitlab.example/mr/{handle.branch}", handle.branch)

class RecordingPublisher:
    def __init__(self):
        self.events: list[DomainEvent] = []
    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)
```

- [ ] **Step 5: 跑测试确认通过并 commit**

Run: `pytest tests/test_fakes.py -q`
Expected: `2 passed`。
```bash
git add src/autodev/domain/ports.py tests/fakes.py tests/test_fakes.py && git commit -m "feat(domain): 出站端口 Protocol + 测试假适配器"
```

---

### Task 8: 阶段处理器（前段）INTAKE / TRIAGE / CONTEXT / DESIGN

**Files:**
- Create: `src/autodev/application/__init__.py`（空）
- Create: `src/autodev/application/context.py`
- Create: `src/autodev/application/handlers.py`
- Test: `tests/application/__init__.py`（空）、`tests/application/test_handlers_front.py`

**Interfaces:**
- Consumes: 全部 `domain`、`tests/fakes`。
- Produces：
  - `StageContext`（dataclass）字段：`workspace: WorkspacePort`、`gatherer: ContextPort`、`designer: DesignPort`、`reviewer: ReviewPort`、`executor: ExecutionPort`、`verifier: VerificationPort`、`delivery: DeliveryPort`、`triage_policy: TriagePolicy`、`gate_policy: GatePolicy`。
  - 处理器函数（签名统一 `(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome`）：`handle_intake`、`handle_triage`、`handle_context`、`handle_design`。
  - 约定 artifact key：`"triage"`、`"context"`、`"design"`（INTAKE 无产物）。
  - 分支命名：`branch_for(work_item) -> str` 返回 `f"autodev/{work_item.id.value[:8]}"`。

- [ ] **Step 1: 写失败测试**

```python
# tests/application/test_handlers_front.py
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import TaskType, WorkspaceMode, FailureKind
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial
from autodev.domain.work_item import WorkItem
from autodev.domain.policies import TriagePolicy, GatePolicy
from autodev.application.context import StageContext
from autodev.application.handlers import handle_intake, handle_triage, handle_context, handle_design
from tests.fakes import (FakeWorkspace, FakeContext, FakeDesign, FakeReview,
                         FakeExecution, FakeVerification, FakeDelivery)

NOW = datetime(2026, 7, 15)

def _ctx(ws=None):
    return StageContext(
        workspace=ws or FakeWorkspace(local=True),
        gatherer=FakeContext(), designer=FakeDesign(), reviewer=FakeReview(),
        executor=FakeExecution(), verifier=FakeVerification(), delivery=FakeDelivery(),
        triage_policy=TriagePolicy(), gate_policy=GatePolicy(),
    )

def _wi(goal="fix typo", repo="repo-a"):
    return WorkItem.create(WorkItemId.new(), RepoRef(repo),
                           Requirement(goal, repo, (), "raw"), AutonomyDial.all_human(), NOW)

def test_intake_ok_when_complete():
    assert handle_intake(_wi(), _ctx(), NOW).kind == "success"

def test_intake_fatal_when_incomplete():
    out = handle_intake(_wi(goal=""), _ctx(), NOW)
    assert out.kind == "failure" and out.failure_kind is FailureKind.FATAL

def test_triage_sets_type_and_mode():
    wi = _wi()
    out = handle_triage(wi, _ctx(FakeWorkspace(local=True)), NOW)
    assert out.kind == "success" and out.artifact_key == "triage"
    assert wi.type is TaskType.SMALL_CHANGE
    assert out.artifact.workspace_mode is WorkspaceMode.WORKTREE

def test_context_provisions_workspace():
    from autodev.domain.artifacts import TriageArtifact
    wi = _wi()
    wi.type = TaskType.SMALL_CHANGE
    wi.add_artifact("triage", TriageArtifact(TaskType.SMALL_CHANGE, 0.9, WorkspaceMode.WORKTREE))
    out = handle_context(wi, _ctx(), NOW)
    assert out.kind == "success" and out.artifact_key == "context"
    assert out.artifact.branch.startswith("autodev/")

def test_design_reads_context():
    wi = _wi()
    from autodev.domain.artifacts import ContextArtifact
    wi.add_artifact("context", ContextArtifact("/tmp/x", "autodev/abc", ("app.py",), "s"))
    out = handle_design(wi, _ctx(), NOW)
    assert out.kind == "success" and out.artifact_key == "design"
    assert "fix typo" in out.artifact.change_summary
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/application/test_handlers_front.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现**

```python
# src/autodev/application/context.py
from __future__ import annotations
from dataclasses import dataclass
from autodev.domain.ports import (
    WorkspacePort, ContextPort, DesignPort, ReviewPort,
    ExecutionPort, VerificationPort, DeliveryPort,
)
from autodev.domain.policies import TriagePolicy, GatePolicy

@dataclass
class StageContext:
    workspace: WorkspacePort
    gatherer: ContextPort
    designer: DesignPort
    reviewer: ReviewPort
    executor: ExecutionPort
    verifier: VerificationPort
    delivery: DeliveryPort
    triage_policy: TriagePolicy
    gate_policy: GatePolicy
```

```python
# src/autodev/application/handlers.py  (前段部分, 后段在 Task 9 追加)
from __future__ import annotations
from datetime import datetime
from autodev.domain.work_item import WorkItem
from autodev.domain.outcome import StageOutcome
from autodev.domain.enums import FailureKind
from autodev.application.context import StageContext

def branch_for(work_item: WorkItem) -> str:
    return f"autodev/{work_item.id.value[:8]}"

def handle_intake(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    if not work_item.requirement.is_complete():
        return StageOutcome.fail(FailureKind.FATAL, "requirement incomplete; needs human clarification")
    return StageOutcome.ok()

def handle_triage(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    status = ctx.workspace.repo_status(work_item.repo_ref)
    artifact = ctx.triage_policy.triage(work_item.requirement, status)
    work_item.type = artifact.level
    return StageOutcome.ok("triage", artifact)

def handle_context(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    triage = work_item.artifacts["triage"]
    handle = ctx.workspace.provision(
        work_item.id, work_item.repo_ref, triage.workspace_mode, branch_for(work_item),
    )
    artifact = ctx.gatherer.gather(work_item.requirement, handle)
    return StageOutcome.ok("context", artifact)

def handle_design(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    context = work_item.artifacts["context"]
    artifact = ctx.designer.propose(work_item.requirement, context)
    return StageOutcome.ok("design", artifact)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/application/test_handlers_front.py -q`
Expected: `5 passed`。

- [ ] **Step 5: Commit**

```bash
git add src/autodev/application tests/application && git commit -m "feat(app): 前段处理器 INTAKE/TRIAGE/CONTEXT/DESIGN"
```

---

### Task 9: 阶段处理器（后段）REVIEW / IMPL / ACCEPT / VERIFY / SUBMIT_MR

**Files:**
- Modify: `src/autodev/application/handlers.py`（追加函数与 `HANDLERS` 注册表）
- Test: `tests/application/test_handlers_back.py`

**Interfaces:**
- Consumes: Task 8 的 `StageContext`、`branch_for`；`domain` 全量。
- Produces（追加处理器，签名同前）：`handle_review`、`handle_impl`、`handle_accept`、`handle_verify`、`handle_submit_mr`；以及注册表 `HANDLERS: dict[WorkflowState, Callable]`。
  - artifact key：`"review"`、`"impl"`、`"accept"`、`"verify"`、`"delivery"`。
  - REVIEW：审不过 → `fail(LOGIC, ...)`；审过且门禁需人 → `suspend(REVIEW_GATE, "review", 产物)`；否则 `ok("review", 产物)`。
  - VERIFY：verdict 不过 → `fail(LOGIC, ...)`；过 → `ok("verify", 产物)`。
  - ACCEPT：确定性生成 `AcceptanceArtifact`，条目 = `("relevant tests pass", "build succeeds") + requirement.acceptance_hints`。
  - SUBMIT_MR：`delivery.submit(...)` → 门禁 MERGE_GATE 需人 → `suspend(MERGE_GATE, "delivery", 产物)`；否则 `ok("delivery", 产物)`。

- [ ] **Step 1: 写失败测试**

```python
# tests/application/test_handlers_back.py
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import TaskType, GatePoint, FailureKind, WorkflowState as S
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial
from autodev.domain.artifacts import (DesignArtifact, ContextArtifact,
                                       AcceptanceArtifact, ImplArtifact)
from autodev.domain.work_item import WorkItem
from autodev.domain.policies import TriagePolicy, GatePolicy
from autodev.application.context import StageContext
from autodev.application.handlers import (
    handle_review, handle_impl, handle_accept, handle_verify, handle_submit_mr, HANDLERS,
)
from tests.fakes import (FakeWorkspace, FakeContext, FakeDesign, FakeReview,
                         FakeExecution, FakeVerification, FakeDelivery)

NOW = datetime(2026, 7, 15)

def _ctx(review_ok=True, verify_ok=True, dial=None):
    return StageContext(
        workspace=FakeWorkspace(), gatherer=FakeContext(), designer=FakeDesign(),
        reviewer=FakeReview(approved=review_ok), executor=FakeExecution(),
        verifier=FakeVerification(passed=verify_ok), delivery=FakeDelivery(),
        triage_policy=TriagePolicy(), gate_policy=GatePolicy(),
    ), (dial or AutonomyDial.all_human())

def _wi(dial):
    wi = WorkItem.create(WorkItemId.new(), RepoRef("repo-a"),
                         Requirement("fix typo", "repo-a", ("msg correct",), "raw"), dial, NOW)
    wi.type = TaskType.SMALL_CHANGE
    wi.add_artifact("context", ContextArtifact("/tmp/x", "autodev/abc", ("app.py",), "s"))
    wi.add_artifact("design", DesignArtifact("do: fix typo", ("app.py",)))
    return wi

def test_review_suspends_when_human_required():
    ctx, dial = _ctx(review_ok=True)
    out = handle_review(_wi(dial), ctx, NOW)
    assert out.kind == "suspend" and out.gate_point is GatePoint.REVIEW_GATE
    assert out.artifact_key == "review"

def test_review_ok_when_auto():
    auto = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    ctx, _ = _ctx(review_ok=True, dial=auto)
    out = handle_review(_wi(auto), ctx, NOW)
    assert out.kind == "success" and out.artifact_key == "review"

def test_review_rejected_is_logic_failure():
    ctx, dial = _ctx(review_ok=False)
    out = handle_review(_wi(dial), ctx, NOW)
    assert out.kind == "failure" and out.failure_kind is FailureKind.LOGIC

def test_impl_and_accept():
    ctx, dial = _ctx()
    wi = _wi(dial)
    out_impl = handle_impl(wi, ctx, NOW)
    assert out_impl.kind == "success" and out_impl.artifact_key == "impl"
    wi.add_artifact("impl", out_impl.artifact)
    out_acc = handle_accept(wi, ctx, NOW)
    assert out_acc.kind == "success"
    assert "msg correct" in out_acc.artifact.criteria

def test_verify_pass_and_fail():
    ctx_ok, dial = _ctx(verify_ok=True)
    wi = _wi(dial)
    wi.add_artifact("accept", AcceptanceArtifact(("relevant tests pass",)))
    assert handle_verify(wi, ctx_ok, NOW).kind == "success"
    ctx_bad, dial2 = _ctx(verify_ok=False)
    wi2 = _wi(dial2)
    wi2.add_artifact("accept", AcceptanceArtifact(("relevant tests pass",)))
    out = handle_verify(wi2, ctx_bad, NOW)
    assert out.kind == "failure" and out.failure_kind is FailureKind.LOGIC

def test_submit_mr_suspends_at_merge_gate():
    ctx, dial = _ctx()
    out = handle_submit_mr(_wi(dial), ctx, NOW)
    assert out.kind == "suspend" and out.gate_point is GatePoint.MERGE_GATE
    assert out.artifact.mr_url

def test_handlers_registry_covers_all_active_states():
    assert set(HANDLERS.keys()) == {
        S.INTAKE, S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW,
        S.IMPL, S.ACCEPT, S.VERIFY, S.SUBMIT_MR,
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/application/test_handlers_back.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现（追加到 handlers.py 末尾）**

```python
# 追加到 src/autodev/application/handlers.py
from typing import Callable
from autodev.domain.enums import GatePoint, WorkflowState
from autodev.domain.artifacts import AcceptanceArtifact

def handle_review(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    context = work_item.artifacts["context"]
    design = work_item.artifacts["design"]
    review = ctx.reviewer.review(design, context)
    if not review.approved:
        return StageOutcome.fail(FailureKind.LOGIC, f"review rejected: {review.comments}")
    decision = ctx.gate_policy.decide(work_item, GatePoint.REVIEW_GATE)
    if decision.needs_human:
        return StageOutcome.suspend(GatePoint.REVIEW_GATE, "review", review)
    return StageOutcome.ok("review", review)

def handle_impl(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    design = work_item.artifacts["design"]
    context = work_item.artifacts["context"]
    handle = _handle_from_context(context)
    impl = ctx.executor.implement(design, handle)
    return StageOutcome.ok("impl", impl)

def handle_accept(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    criteria = ("relevant tests pass", "build succeeds") + tuple(work_item.requirement.acceptance_hints)
    return StageOutcome.ok("accept", AcceptanceArtifact(criteria))

def handle_verify(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    criteria = work_item.artifacts["accept"]
    context = work_item.artifacts["context"]
    handle = _handle_from_context(context)
    ver = ctx.verifier.verify(criteria, handle)
    if not ver.verdict.passed:
        return StageOutcome.fail(FailureKind.LOGIC, f"verification failed: {ver.verdict.reasons}")
    return StageOutcome.ok("verify", ver)

def handle_submit_mr(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    design = work_item.artifacts["design"]
    context = work_item.artifacts["context"]
    handle = _handle_from_context(context)
    delivery = ctx.delivery.submit(work_item.requirement, design, handle)
    decision = ctx.gate_policy.decide(work_item, GatePoint.MERGE_GATE)
    if decision.needs_human:
        return StageOutcome.suspend(GatePoint.MERGE_GATE, "delivery", delivery)
    return StageOutcome.ok("delivery", delivery)

def _handle_from_context(context):
    from autodev.domain.value_objects import WorkspaceHandle
    return WorkspaceHandle(context.worktree_path, context.branch)

HANDLERS: dict[WorkflowState, Callable] = {
    WorkflowState.INTAKE: handle_intake,
    WorkflowState.TRIAGE: handle_triage,
    WorkflowState.CONTEXT: handle_context,
    WorkflowState.DESIGN: handle_design,
    WorkflowState.REVIEW: handle_review,
    WorkflowState.IMPL: handle_impl,
    WorkflowState.ACCEPT: handle_accept,
    WorkflowState.VERIFY: handle_verify,
    WorkflowState.SUBMIT_MR: handle_submit_mr,
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/application/test_handlers_back.py -q`
Expected: `7 passed`。

- [ ] **Step 5: Commit**

```bash
git add src/autodev/application tests/application && git commit -m "feat(app): 后段处理器 REVIEW/IMPL/ACCEPT/VERIFY/SUBMIT_MR + 注册表"
```

---

### Task 10: 引擎 Engine

**Files:**
- Create: `src/autodev/application/engine.py`
- Test: `tests/application/test_engine.py`

**Interfaces:**
- Consumes: `HANDLERS`、`StageContext`、`domain` 策略与聚合、`StageError`、端口 `WorkItemRepository`/`EventPublisher`、事件类。
- Produces：
  - `Engine(repo: WorkItemRepository, publisher: EventPublisher, ctx: StageContext, clock: Callable[[], datetime], transition_rules=TransitionRules(), retry_policy=RetryPolicy())`。
  - `Engine.advance(work_item: WorkItem) -> None`：跑当前状态 handler，按 StageOutcome 处理成功/挂起/失败，更新聚合、发事件、`repo.save`。
    - 成功：有 artifact 则 `add_artifact`；`transition_to(next_state)`；若到 DONE → `workspace.cleanup` + 发 `WorkItemCompleted`。
    - 挂起：有 artifact 则 `add_artifact`；`suspend(gate)`；发 `HumanApprovalRequested`。
    - 失败：捕获自 handler 返回的 failure 或抛出的 `StageError`（非 `StageError` 异常按 TRANSIENT 处理）；`RetryPolicy` 决策 retry（记数，状态不变）/ rollback（记数 + 转移）/ fail（转 FAILED + 发 `WorkItemFailed`）。
  - `run_until_quiescent(repo, engine) -> None`：反复 `claim_runnable` 并 `advance`，直到无可运行任务。

- [ ] **Step 1: 写失败测试**

```python
# tests/application/test_engine.py
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState as S, TaskType, GatePoint
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial
from autodev.domain.work_item import WorkItem
from autodev.domain.policies import TriagePolicy, GatePolicy
from autodev.domain.events import HumanApprovalRequested, WorkItemFailed
from autodev.application.context import StageContext
from autodev.application.engine import Engine, run_until_quiescent
from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from tests.fakes import (FakeWorkspace, FakeContext, FakeDesign, FakeReview,
                         FakeExecution, FakeVerification, FakeDelivery, RecordingPublisher)

NOW = datetime(2026, 7, 15)

def _engine(repo, pub, review_ok=True, verify_ok=True):
    ctx = StageContext(
        workspace=FakeWorkspace(local=True), gatherer=FakeContext(), designer=FakeDesign(),
        reviewer=FakeReview(approved=review_ok), executor=FakeExecution(),
        verifier=FakeVerification(passed=verify_ok), delivery=FakeDelivery(),
        triage_policy=TriagePolicy(), gate_policy=GatePolicy(),
    )
    return Engine(repo, pub, ctx, clock=lambda: NOW)

def _wi(dial):
    return WorkItem.create(WorkItemId.new(), RepoRef("repo-a"),
                           Requirement("fix typo", "repo-a", (), "raw"), dial, NOW)

def test_runs_until_merge_gate_suspend():
    # REVIEW_GATE 自动、MERGE_GATE 人审
    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    wi = _wi(dial); repo.save(wi)
    run_until_quiescent(repo, _engine(repo, pub))
    got = repo.get(wi.id)
    assert got.state is S.WAIT_HUMAN and got.pending_gate is GatePoint.MERGE_GATE
    assert any(isinstance(e, HumanApprovalRequested) for e in pub.events)
    assert "delivery" in got.artifacts

def test_verify_failure_rolls_back_and_eventually_fails():
    dial = AutonomyDial(frozenset({
        (TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE),
        (TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE),
    }))
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    wi = _wi(dial); repo.save(wi)
    run_until_quiescent(repo, _engine(repo, pub, verify_ok=False))
    got = repo.get(wi.id)
    assert got.state is S.FAILED
    assert any(isinstance(e, WorkItemFailed) for e in pub.events)

def test_fully_auto_reaches_done_and_cleans_up():
    dial = AutonomyDial(frozenset({
        (TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE),
        (TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE),
    }))
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    eng = _engine(repo, pub)
    wi = _wi(dial); repo.save(wi)
    run_until_quiescent(repo, eng)
    got = repo.get(wi.id)
    assert got.state is S.DONE
    assert eng.ctx.workspace.cleaned  # cleanup 被调用
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/application/test_engine.py -q`
Expected: FAIL（`engine` / `memory_repository` 未实现）。

- [ ] **Step 3: 实现**

```python
# src/autodev/application/engine.py
from __future__ import annotations
from datetime import datetime
from typing import Callable
from autodev.domain.enums import WorkflowState as S, FailureKind
from autodev.domain.errors import StageError
from autodev.domain.policies import TransitionRules, RetryPolicy
from autodev.domain.value_objects import WorkspaceHandle
from autodev.domain.work_item import WorkItem
from autodev.domain.events import (
    HumanApprovalRequested, WorkItemCompleted, WorkItemFailed,
)
from autodev.application.context import StageContext
from autodev.application.handlers import HANDLERS

class Engine:
    def __init__(self, repo, publisher, ctx: StageContext,
                 clock: Callable[[], datetime],
                 transition_rules: TransitionRules | None = None,
                 retry_policy: RetryPolicy | None = None) -> None:
        self.repo = repo
        self.publisher = publisher
        self.ctx = ctx
        self.clock = clock
        self.transition_rules = transition_rules or TransitionRules()
        self.retry_policy = retry_policy or RetryPolicy()

    def advance(self, work_item: WorkItem) -> None:
        if not work_item.is_runnable():
            return
        now = self.clock()
        handler = HANDLERS[work_item.state]
        try:
            outcome = handler(work_item, self.ctx, now)
        except StageError as e:
            outcome = _to_failure(e.failure_kind, e.message)
        except Exception as e:  # noqa: BLE001 未预期异常 → 有界 TRANSIENT
            outcome = _to_failure(FailureKind.TRANSIENT, f"unexpected: {e}")

        if outcome.kind == "success":
            self._on_success(work_item, outcome, now)
        elif outcome.kind == "suspend":
            self._on_suspend(work_item, outcome, now)
        else:
            self._on_failure(work_item, outcome, now)
        self.repo.save(work_item)

    def _on_success(self, wi: WorkItem, outcome, now: datetime) -> None:
        if outcome.artifact_key:
            wi.add_artifact(outcome.artifact_key, outcome.artifact)
        nxt = self.transition_rules.next_state(wi.state)
        wi.transition_to(nxt, "stage ok", now)
        if nxt is S.DONE:
            self._finalize_done(wi)

    def _on_suspend(self, wi: WorkItem, outcome, now: datetime) -> None:
        if outcome.artifact_key:
            wi.add_artifact(outcome.artifact_key, outcome.artifact)
        wi.suspend(outcome.gate_point, f"awaiting human at {outcome.gate_point.name}", now)
        self.publisher.publish(HumanApprovalRequested(wi.id, outcome.gate_point))

    def _on_failure(self, wi: WorkItem, outcome, now: datetime) -> None:
        decision = self.retry_policy.decide(wi.state, outcome.failure_kind, wi.retry_ledger)
        if decision.action == "retry":
            wi.record_retry(decision.key)  # 状态不变, 下轮重试
        elif decision.action == "rollback":
            wi.record_retry(decision.key)
            wi.transition_to(decision.target, f"rollback: {outcome.message}", now)
        else:  # fail
            wi.transition_to(S.FAILED, f"failed: {outcome.message}", now)
            self.publisher.publish(WorkItemFailed(wi.id, wi.state.name, outcome.message))

    def _finalize_done(self, wi: WorkItem) -> None:
        delivery = wi.artifacts.get("delivery")
        context = wi.artifacts.get("context")
        if context is not None:
            self.ctx.workspace.cleanup(WorkspaceHandle(context.worktree_path, context.branch))
        mr_url = getattr(delivery, "mr_url", "")
        self.publisher.publish(WorkItemCompleted(wi.id, mr_url))


def _to_failure(kind: FailureKind, message: str):
    from autodev.domain.outcome import StageOutcome
    return StageOutcome.fail(kind, message)


def run_until_quiescent(repo, engine: Engine) -> None:
    while True:
        runnable = repo.claim_runnable()
        if not runnable:
            return
        for wi in runnable:
            engine.advance(wi)
```

> 注意：`WorkItemFailed(wi.id, wi.state.name, ...)` 在 `transition_to(FAILED)` 之后发布，故 `state.name == "FAILED"`；如需记录失败发生的原始阶段，可在转移前捕获 `origin = wi.state.name` 再传入。实现时按后者：转移前先存 `origin = wi.state.name`，发布 `WorkItemFailed(wi.id, origin, outcome.message)`。

- [ ] **Step 4: 调整失败事件记录原始阶段**

把 `_on_failure` 的 fail 分支改为：

```python
        else:  # fail
            origin = wi.state.name
            wi.transition_to(S.FAILED, f"failed: {outcome.message}", now)
            self.publisher.publish(WorkItemFailed(wi.id, origin, outcome.message))
```

- [ ] **Step 5: 跑测试（需 Task 11 的内存仓储）**

本任务测试依赖 `InMemoryWorkItemRepository`。先做 Task 11 的内存仓储再回来跑，或在本任务内联最小内存仓储。**决定：在 Task 11 建仓储，本步骤仅 commit 引擎实现，测试在 Task 11 结束时统一跑绿。**

```bash
git add src/autodev/application/engine.py tests/application/test_engine.py && git commit -m "feat(app): 状态机引擎 Engine（成功/挂起/失败/重试/回退/清理）"
```

---

### Task 11: 内存仓储 + 入口 + 引擎测试跑绿

**Files:**
- Create: `src/autodev/adapters/__init__.py`（空）
- Create: `src/autodev/adapters/memory_repository.py`
- Create: `src/autodev/adapters/event_bus.py`
- Create: `src/autodev/application/entrypoints.py`
- Test: `tests/adapters/__init__.py`（空）、`tests/application/test_entrypoints.py`

**Interfaces:**
- Consumes: `domain`、`Engine`、`StageContext`。
- Produces：
  - `InMemoryWorkItemRepository`：实现 `WorkItemRepository`；`save/get/claim_runnable`（返回所有 `is_runnable()` 的 WorkItem 列表）。
  - `InMemoryEventBus`：实现 `EventPublisher`；`subscribe(handler: Callable[[DomainEvent], None])`；`publish` 分发给所有订阅者。
  - `create_work_item(repo, publisher, *, work_item_id, repo_ref, requirement, autonomy_dial, now) -> WorkItem`：建 WorkItem（INTAKE）、`repo.save`、发 `WorkItemCreated`、返回。
  - `advance_work_item(work_item_id, repo, engine) -> None`：`engine.advance(repo.get(id))`。
  - `resume_work_item(work_item_id, approved, repo, engine, now) -> None`：仅当 `WAIT_HUMAN`；approved：按 `GATE_RESUME_TARGET[pending_gate]` `resume_to`，若目标 DONE 则 `engine._finalize_done`；未 approved：`transition_to(FAILED)` + 发 `WorkItemFailed`。常量 `GATE_RESUME_TARGET = {REVIEW_GATE: IMPL, MERGE_GATE: DONE}`。

- [ ] **Step 1: 写失败测试**

```python
# tests/application/test_entrypoints.py
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState as S, TaskType, GatePoint
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial
from autodev.domain.events import WorkItemCreated, WorkItemCompleted
from autodev.domain.policies import TriagePolicy, GatePolicy
from autodev.application.context import StageContext
from autodev.application.engine import Engine, run_until_quiescent
from autodev.application.entrypoints import create_work_item, resume_work_item
from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.adapters.event_bus import InMemoryEventBus
from tests.fakes import (FakeWorkspace, FakeContext, FakeDesign, FakeReview,
                         FakeExecution, FakeVerification, FakeDelivery)

NOW = datetime(2026, 7, 15)

def _engine(repo, pub):
    ctx = StageContext(FakeWorkspace(local=True), FakeContext(), FakeDesign(), FakeReview(),
                       FakeExecution(), FakeVerification(), FakeDelivery(),
                       TriagePolicy(), GatePolicy())
    return Engine(repo, pub, ctx, clock=lambda: NOW)

def test_create_emits_created_event():
    repo, bus = InMemoryWorkItemRepository(), InMemoryEventBus()
    seen = []; bus.subscribe(seen.append)
    wi = create_work_item(repo, bus, work_item_id=WorkItemId.new(), repo_ref=RepoRef("repo-a"),
                          requirement=Requirement("fix typo", "repo-a", (), "raw"),
                          autonomy_dial=AutonomyDial.all_human(), now=NOW)
    assert repo.get(wi.id).state is S.INTAKE
    assert any(isinstance(e, WorkItemCreated) for e in seen)

def test_resume_at_merge_gate_completes():
    repo, bus = InMemoryWorkItemRepository(), InMemoryEventBus()
    seen = []; bus.subscribe(seen.append)
    # REVIEW 自动, MERGE 人审 → 跑到 WAIT_HUMAN(MERGE)
    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    eng = _engine(repo, bus)
    wi = create_work_item(repo, bus, work_item_id=WorkItemId.new(), repo_ref=RepoRef("repo-a"),
                          requirement=Requirement("fix typo", "repo-a", (), "raw"),
                          autonomy_dial=dial, now=NOW)
    run_until_quiescent(repo, eng)
    assert repo.get(wi.id).state is S.WAIT_HUMAN
    resume_work_item(wi.id, True, repo, eng, NOW)
    assert repo.get(wi.id).state is S.DONE
    assert any(isinstance(e, WorkItemCompleted) for e in seen)

def test_resume_denied_fails():
    repo, bus = InMemoryWorkItemRepository(), InMemoryEventBus()
    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    eng = _engine(repo, bus)
    wi = create_work_item(repo, bus, work_item_id=WorkItemId.new(), repo_ref=RepoRef("repo-a"),
                          requirement=Requirement("fix typo", "repo-a", (), "raw"),
                          autonomy_dial=dial, now=NOW)
    run_until_quiescent(repo, eng)
    resume_work_item(wi.id, False, repo, eng, NOW)
    assert repo.get(wi.id).state is S.FAILED
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/application/test_entrypoints.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现仓储与事件总线**

```python
# src/autodev/adapters/memory_repository.py
from __future__ import annotations
from autodev.domain.ids import WorkItemId
from autodev.domain.work_item import WorkItem

class InMemoryWorkItemRepository:
    def __init__(self) -> None:
        self._store: dict[str, WorkItem] = {}

    def save(self, work_item: WorkItem) -> None:
        self._store[work_item.id.value] = work_item

    def get(self, work_item_id: WorkItemId) -> WorkItem:
        return self._store[work_item_id.value]

    def claim_runnable(self) -> list[WorkItem]:
        return [wi for wi in self._store.values() if wi.is_runnable()]
```

```python
# src/autodev/adapters/event_bus.py
from __future__ import annotations
from typing import Callable
from autodev.domain.events import DomainEvent

class InMemoryEventBus:
    def __init__(self) -> None:
        self._subs: list[Callable[[DomainEvent], None]] = []

    def subscribe(self, handler: Callable[[DomainEvent], None]) -> None:
        self._subs.append(handler)

    def publish(self, event: DomainEvent) -> None:
        for h in list(self._subs):
            h(event)
```

- [ ] **Step 4: 实现入口**

```python
# src/autodev/application/entrypoints.py
from __future__ import annotations
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState as S, GatePoint
from autodev.domain.errors import InvariantError
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial
from autodev.domain.work_item import WorkItem
from autodev.domain.events import WorkItemCreated, WorkItemFailed

GATE_RESUME_TARGET = {GatePoint.REVIEW_GATE: S.IMPL, GatePoint.MERGE_GATE: S.DONE}

def create_work_item(repo, publisher, *, work_item_id: WorkItemId, repo_ref: RepoRef,
                     requirement: Requirement, autonomy_dial: AutonomyDial,
                     now: datetime) -> WorkItem:
    wi = WorkItem.create(work_item_id, repo_ref, requirement, autonomy_dial, now)
    repo.save(wi)
    publisher.publish(WorkItemCreated(wi.id))
    return wi

def advance_work_item(work_item_id: WorkItemId, repo, engine) -> None:
    engine.advance(repo.get(work_item_id))

def resume_work_item(work_item_id: WorkItemId, approved: bool, repo, engine,
                     now: datetime) -> None:
    wi = repo.get(work_item_id)
    if wi.state is not S.WAIT_HUMAN:
        raise InvariantError("resume requires WAIT_HUMAN")
    gate = wi.pending_gate
    if approved:
        target = GATE_RESUME_TARGET[gate]
        wi.resume_to(target, f"approved at {gate.name}", now)
        if target is S.DONE:
            engine._finalize_done(wi)
    else:
        origin = wi.state.name
        wi.resume_to(S.FAILED, f"denied at {gate.name}", now)
        engine.publisher.publish(WorkItemFailed(wi.id, origin, "human denied"))
    repo.save(wi)
```

- [ ] **Step 5: 跑全部测试并 commit**

Run: `pytest -q`（应包含 Task 10 的 `test_engine.py` 现在跑绿）
Expected: 全绿。
```bash
git add src/autodev/adapters src/autodev/application/entrypoints.py tests/adapters tests/application/test_entrypoints.py && git commit -m "feat(app): 内存仓储/事件总线/入口, 引擎测试跑绿"
```

---

### Task 12: SQLite 仓储（持久化 ACL）

**Files:**
- Create: `src/autodev/adapters/sqlite_repository.py`
- Test: `tests/adapters/test_sqlite_repository.py`

**Interfaces:**
- Consumes: `WorkItem` 及其全部值对象/枚举/产物。
- Produces：`SqliteWorkItemRepository(db_path: str)`，实现 `WorkItemRepository`（`save/get/claim_runnable`）。用一张表存整个 WorkItem 的 JSON 快照 + 冗余 `state` 列以便 `claim_runnable` 查询。需 `to_row/from_row` 的领域↔行序列化（在本适配器内部完成，核心不感知 SQL）。
  - `save`：upsert（按 `id`）。
  - `get`：反序列化为 WorkItem。
  - `claim_runnable`：`WHERE state NOT IN ('DONE','FAILED','WAIT_HUMAN')`。

- [ ] **Step 1: 写失败测试（契约：与内存仓储行为一致的往返）**

```python
# tests/adapters/test_sqlite_repository.py
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState as S, TaskType, WorkspaceMode
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial
from autodev.domain.artifacts import TriageArtifact
from autodev.domain.work_item import WorkItem
from autodev.adapters.sqlite_repository import SqliteWorkItemRepository

NOW = datetime(2026, 7, 15, 10, 30)

def _wi():
    wi = WorkItem.create(WorkItemId.new(), RepoRef("repo-a"),
                         Requirement("fix typo", "repo-a", ("hint",), "raw"),
                         AutonomyDial.all_human(), NOW)
    wi.type = TaskType.SMALL_CHANGE
    wi.add_artifact("triage", TriageArtifact(TaskType.SMALL_CHANGE, 0.9, WorkspaceMode.WORKTREE))
    wi.transition_to(S.TRIAGE, "ok", NOW)
    return wi

def test_save_and_get_roundtrip(tmp_path):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    wi = _wi(); repo.save(wi)
    got = repo.get(wi.id)
    assert got.id == wi.id and got.state is S.TRIAGE and got.type is TaskType.SMALL_CHANGE
    assert got.requirement.goal == "fix typo"
    assert got.artifacts["triage"].workspace_mode is WorkspaceMode.WORKTREE

def test_claim_runnable_excludes_terminal(tmp_path):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    a = _wi(); repo.save(a)
    b = _wi(); b.transition_to(S.FAILED, "x", NOW); repo.save(b)
    ids = {wi.id.value for wi in repo.claim_runnable()}
    assert a.id.value in ids and b.id.value not in ids

def test_save_is_upsert(tmp_path):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    wi = _wi(); repo.save(wi)
    wi.transition_to(S.CONTEXT, "next", NOW); repo.save(wi)
    assert repo.get(wi.id).state is S.CONTEXT
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/adapters/test_sqlite_repository.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现**

```python
# src/autodev/adapters/sqlite_repository.py
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState, TaskType, WorkspaceMode, GatePoint
from autodev.domain.value_objects import (
    RepoRef, Requirement, AutonomyDial, RetryLedger, Cost, Verdict,
)
from autodev.domain.artifacts import (
    TriageArtifact, ContextArtifact, DesignArtifact, ReviewArtifact,
    ImplArtifact, AcceptanceArtifact, VerificationArtifact, DeliveryArtifact,
)
from autodev.domain.work_item import WorkItem, StateTransition

_TERMINAL_OR_WAIT = ("DONE", "FAILED", "WAIT_HUMAN")

class SqliteWorkItemRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS work_items ("
                      "id TEXT PRIMARY KEY, state TEXT NOT NULL, data TEXT NOT NULL)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def save(self, work_item: WorkItem) -> None:
        data = json.dumps(_to_dict(work_item))
        with self._conn() as c:
            c.execute("INSERT INTO work_items(id, state, data) VALUES(?,?,?) "
                      "ON CONFLICT(id) DO UPDATE SET state=excluded.state, data=excluded.data",
                      (work_item.id.value, work_item.state.name, data))

    def get(self, work_item_id: WorkItemId) -> WorkItem:
        with self._conn() as c:
            row = c.execute("SELECT data FROM work_items WHERE id=?",
                            (work_item_id.value,)).fetchone()
        if row is None:
            raise KeyError(work_item_id.value)
        return _from_dict(json.loads(row[0]))

    def claim_runnable(self) -> list[WorkItem]:
        q = ("SELECT data FROM work_items WHERE state NOT IN (?,?,?)")
        with self._conn() as c:
            rows = c.execute(q, _TERMINAL_OR_WAIT).fetchall()
        return [_from_dict(json.loads(r[0])) for r in rows]

# ---------- 序列化（领域 ↔ dict），核心不感知 ----------

def _to_dict(wi: WorkItem) -> dict:
    return {
        "id": wi.id.value,
        "repo_ref": wi.repo_ref.name,
        "requirement": {
            "goal": wi.requirement.goal, "target_repo": wi.requirement.target_repo,
            "acceptance_hints": list(wi.requirement.acceptance_hints),
            "raw_text": wi.requirement.raw_text,
        },
        "autonomy_dial": [[t.name, r, g.name] for (t, r, g) in wi.autonomy_dial.auto_gates],
        "type": wi.type.name if wi.type else None,
        "state": wi.state.name,
        "artifacts": {k: _artifact_to_dict(v) for k, v in wi.artifacts.items()},
        "history": [[h.from_state.name, h.to_state.name, h.reason, h.at.isoformat()]
                    for h in wi.history],
        "retry_ledger": list(wi.retry_ledger.counts),
        "cost": wi.cost.tokens,
        "pending_gate": wi.pending_gate.name if wi.pending_gate else None,
        "created_at": wi.created_at.isoformat() if wi.created_at else None,
        "updated_at": wi.updated_at.isoformat() if wi.updated_at else None,
    }

def _from_dict(d: dict) -> WorkItem:
    wi = WorkItem(
        id=WorkItemId(d["id"]),
        repo_ref=RepoRef(d["repo_ref"]),
        requirement=Requirement(d["requirement"]["goal"], d["requirement"]["target_repo"],
                                tuple(d["requirement"]["acceptance_hints"]),
                                d["requirement"]["raw_text"]),
        autonomy_dial=AutonomyDial(frozenset(
            (TaskType[t], r, GatePoint[g]) for (t, r, g) in d["autonomy_dial"])),
        type=TaskType[d["type"]] if d["type"] else None,
        state=WorkflowState[d["state"]],
        artifacts={k: _artifact_from_dict(v) for k, v in d["artifacts"].items()},
        history=[StateTransition(WorkflowState[a], WorkflowState[b], reason,
                                 datetime.fromisoformat(at)) for (a, b, reason, at) in d["history"]],
        retry_ledger=RetryLedger(frozenset(tuple(x) for x in d["retry_ledger"])),
        cost=Cost(d["cost"]),
        pending_gate=GatePoint[d["pending_gate"]] if d["pending_gate"] else None,
        created_at=datetime.fromisoformat(d["created_at"]) if d["created_at"] else None,
        updated_at=datetime.fromisoformat(d["updated_at"]) if d["updated_at"] else None,
    )
    return wi

def _artifact_to_dict(a: object) -> dict:
    t = type(a).__name__
    if isinstance(a, TriageArtifact):
        return {"__t": t, "level": a.level.name, "confidence": a.confidence,
                "workspace_mode": a.workspace_mode.name}
    if isinstance(a, ContextArtifact):
        return {"__t": t, "worktree_path": a.worktree_path, "branch": a.branch,
                "relevant_files": list(a.relevant_files), "summary": a.summary}
    if isinstance(a, DesignArtifact):
        return {"__t": t, "change_summary": a.change_summary, "target_files": list(a.target_files)}
    if isinstance(a, ReviewArtifact):
        return {"__t": t, "approved": a.approved, "comments": list(a.comments)}
    if isinstance(a, ImplArtifact):
        return {"__t": t, "diff": a.diff, "test_passed": a.test_passed, "summary": a.summary}
    if isinstance(a, AcceptanceArtifact):
        return {"__t": t, "criteria": list(a.criteria)}
    if isinstance(a, VerificationArtifact):
        return {"__t": t, "passed": a.verdict.passed, "reasons": list(a.verdict.reasons),
                "details": list(a.details)}
    if isinstance(a, DeliveryArtifact):
        return {"__t": t, "mr_url": a.mr_url, "branch": a.branch}
    raise TypeError(f"unknown artifact type {t}")

def _artifact_from_dict(d: dict) -> object:
    t = d["__t"]
    if t == "TriageArtifact":
        return TriageArtifact(TaskType[d["level"]], d["confidence"], WorkspaceMode[d["workspace_mode"]])
    if t == "ContextArtifact":
        return ContextArtifact(d["worktree_path"], d["branch"], tuple(d["relevant_files"]), d["summary"])
    if t == "DesignArtifact":
        return DesignArtifact(d["change_summary"], tuple(d["target_files"]))
    if t == "ReviewArtifact":
        return ReviewArtifact(d["approved"], tuple(d["comments"]))
    if t == "ImplArtifact":
        return ImplArtifact(d["diff"], d["test_passed"], d["summary"])
    if t == "AcceptanceArtifact":
        return AcceptanceArtifact(tuple(d["criteria"]))
    if t == "VerificationArtifact":
        return VerificationArtifact(Verdict(d["passed"], tuple(d["reasons"])), tuple(d["details"]))
    if t == "DeliveryArtifact":
        return DeliveryArtifact(d["mr_url"], d["branch"])
    raise TypeError(f"unknown artifact type {t}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/adapters/test_sqlite_repository.py -q`
Expected: `3 passed`。

- [ ] **Step 5: Commit**

```bash
git add src/autodev/adapters/sqlite_repository.py tests/adapters/test_sqlite_repository.py && git commit -m "feat(adapters): SQLite WorkItem 仓储 + 领域序列化"
```

---

### Task 13: 全流程集成测试（行走骨架验收）+ SQLite 驱动

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/e2e/__init__.py`（空）
- Create: `tests/e2e/test_walking_skeleton.py`

**Interfaces:**
- Consumes: 全部已建组件 + `SqliteWorkItemRepository` + `tests/fakes`。
- Produces：证明"用 SQLite 仓储 + 假适配器，一个 WorkItem 能走完整生命周期"的集成测试。这是本计划的验收标准。

- [ ] **Step 1: 写 conftest（组装 helper）**

```python
# tests/conftest.py
from datetime import datetime
import pytest
from autodev.domain.policies import TriagePolicy, GatePolicy
from autodev.application.context import StageContext
from autodev.application.engine import Engine
from autodev.adapters.event_bus import InMemoryEventBus
from tests.fakes import (FakeWorkspace, FakeContext, FakeDesign, FakeReview,
                         FakeExecution, FakeVerification, FakeDelivery)

FIXED_NOW = datetime(2026, 7, 15, 9, 0, 0)

@pytest.fixture
def make_engine():
    def _make(repo, bus, *, review_ok=True, verify_ok=True):
        ctx = StageContext(FakeWorkspace(local=True), FakeContext(), FakeDesign(),
                           FakeReview(approved=review_ok), FakeExecution(),
                           FakeVerification(passed=verify_ok), FakeDelivery(),
                           TriagePolicy(), GatePolicy())
        return Engine(repo, bus, ctx, clock=lambda: FIXED_NOW)
    return _make
```

- [ ] **Step 2: 写集成测试**

```python
# tests/e2e/test_walking_skeleton.py
from autodev.domain.ids import WorkItemId
from autodev.domain.enums import WorkflowState as S, TaskType, GatePoint
from autodev.domain.value_objects import RepoRef, Requirement, AutonomyDial
from autodev.domain.events import WorkItemCreated, HumanApprovalRequested, WorkItemCompleted
from autodev.application.engine import run_until_quiescent
from autodev.application.entrypoints import create_work_item, resume_work_item
from autodev.adapters.sqlite_repository import SqliteWorkItemRepository
from autodev.adapters.event_bus import InMemoryEventBus
from tests.conftest import FIXED_NOW

def _dial(*gates):
    return AutonomyDial(frozenset((TaskType.SMALL_CHANGE, "repo-a", g) for g in gates))

def test_end_to_end_with_merge_gate(tmp_path, make_engine):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    bus = InMemoryEventBus(); seen = []; bus.subscribe(seen.append)
    eng = make_engine(repo, bus)
    # 只自动 REVIEW_GATE, 保留 MERGE_GATE 人审（切片 1 默认形态）
    wi = create_work_item(repo, bus, work_item_id=WorkItemId.new(), repo_ref=RepoRef("repo-a"),
                          requirement=Requirement("fix passwrod typo", "repo-a",
                                                   ("error message spelled correctly",), "raw"),
                          autonomy_dial=_dial(GatePoint.REVIEW_GATE), now=FIXED_NOW)

    run_until_quiescent(repo, eng)
    mid = repo.get(wi.id)
    assert mid.state is S.WAIT_HUMAN and mid.pending_gate is GatePoint.MERGE_GATE
    assert {"triage", "context", "design", "review", "impl", "accept", "verify", "delivery"} <= set(mid.artifacts)
    assert any(isinstance(e, WorkItemCreated) for e in seen)
    assert any(isinstance(e, HumanApprovalRequested) for e in seen)

    resume_work_item(wi.id, True, repo, eng, FIXED_NOW)
    done = repo.get(wi.id)
    assert done.state is S.DONE
    assert done.artifacts["delivery"].mr_url
    assert any(isinstance(e, WorkItemCompleted) for e in seen)

def test_end_to_end_fully_autonomous(tmp_path, make_engine):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    bus = InMemoryEventBus()
    eng = make_engine(repo, bus)
    wi = create_work_item(repo, bus, work_item_id=WorkItemId.new(), repo_ref=RepoRef("repo-a"),
                          requirement=Requirement("fix typo", "repo-a", (), "raw"),
                          autonomy_dial=_dial(GatePoint.REVIEW_GATE, GatePoint.MERGE_GATE),
                          now=FIXED_NOW)
    run_until_quiescent(repo, eng)
    assert repo.get(wi.id).state is S.DONE
    assert eng.ctx.workspace.cleaned  # DONE 时清理 worktree

def test_end_to_end_verify_failure_fails_cleanly(tmp_path, make_engine):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    bus = InMemoryEventBus()
    eng = make_engine(repo, bus, verify_ok=False)
    wi = create_work_item(repo, bus, work_item_id=WorkItemId.new(), repo_ref=RepoRef("repo-a"),
                          requirement=Requirement("fix typo", "repo-a", (), "raw"),
                          autonomy_dial=_dial(GatePoint.REVIEW_GATE, GatePoint.MERGE_GATE),
                          now=FIXED_NOW)
    run_until_quiescent(repo, eng)
    assert repo.get(wi.id).state is S.FAILED  # VERIFY 反复回退 IMPL 至上限后干净失败
```

- [ ] **Step 3: 跑集成测试**

Run: `pytest tests/e2e/test_walking_skeleton.py -q`
Expected: `3 passed`。

- [ ] **Step 4: 跑全量测试**

Run: `pytest -q`
Expected: 全绿（domain + application + adapters + e2e）。

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/e2e && git commit -m "test(e2e): 行走骨架全流程集成测试（人审/全自动/失败三条路径）"
```

---

## Self-Review

**1. Spec coverage（对照领域模型基准 + 切片 1 spec）：**
- WorkItem 聚合/不变式/产物只进不改 → Task 5 ✅
- 统一语言/枚举 → Task 2 ✅
- 值对象/AutonomyDial/RetryLedger → Task 3 ✅
- 产物族/StageOutcome/领域事件 → Task 4 ✅
- 领域服务（Triage/Gate/Transition/Retry）→ Task 6 ✅
- 出站端口（Ports）→ Task 7 ✅
- 九阶段应用服务（handlers）→ Task 8、9 ✅
- 引擎（成功/挂起/失败/重试/回退/清理/事件）→ Task 10、11 ✅
- 人审=挂起态 + 唤醒 → Task 5（聚合）、Task 10（挂起）、Task 11（resume）✅
- 无人值守旋钮（REVIEW_GATE/MERGE_GATE）→ Task 6（GatePolicy）、e2e Task 13 ✅
- SQLite 仓储（WorkItemRepository ACL）→ Task 12 ✅
- 全流程验证（数据流实例：passwrod→password）→ Task 13 ✅
- 工作区三模式判定 → Task 6（TriagePolicy）✅（真实 git provision 属计划 2）
- 成本仅记录不拦截 → `WorkItem.add_cost` 存在、无上限逻辑 ✅
- **计划 2 覆盖**（真实 ACL：git worktree/Claude Code/GitLab/飞书 + E2E 冒烟）——本计划非目标，明确记录。

**2. Placeholder scan：** 无 TBD/TODO；每个 code step 均有完整可运行代码。Task 7 测试中 `FakeVerification` 那行有注释给出更清晰替代写法。

**3. Type consistency：** 处理器统一签名 `(work_item, ctx, now) -> StageOutcome`；artifact key 全程一致（triage/context/design/review/impl/accept/verify/delivery）；`Engine._finalize_done` 在 Task 10 定义、Task 11 resume 复用；`GATE_RESUME_TARGET` 与 `GatePoint` 一致；序列化字段与产物 dataclass 字段逐一对应。

**遗留说明：** Task 10 的引擎测试依赖 Task 11 的内存仓储，故 Task 10 Step 5 仅 commit 实现、测试在 Task 11 Step 5 统一跑绿——这是有意的任务边界安排，已在 Task 10 内注明。
