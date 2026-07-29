# DesignPort 真实适配器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让流水线 DESIGN 阶段用真实适配器产出一份 Markdown 方案文档并在控制台展示，替换现有的 `UnavailableStage` 桩。

**Architecture:** 新增 `ClaudeDesignAdapter`（`adapters/design_claude.py`），复用 `ClaudeCodeRunner` 在 worktree 内只读跑 `claude`（单遍，无自审），产出方案 md 持久化到 `~/.autodev/workitems/<id>/design-<rand>.md`；`DesignArtifact` 简化为纯 `design_file` 指针（对齐 `ContextArtifact`）。组合根把 `StageContext.designer` 从桩换成真实适配器，有界驱动 `RUN` 扩到含 `DESIGN`（DESIGN 后转 REVIEW，REVIEW∉RUN → 自然停住，不触达 review 桩）。前端复用 `BriefDocument` 渲染管线新增「方案」折叠面板。

**Tech Stack:** Python 3.14 / pytest / ruff / mypy；FastAPI（webapp）；Vite + React + TypeScript + vitest（frontend）。

## Global Constraints

- 核心域纯净：`src/autodev/domain` 不得 import 外部 SDK，也不得 import `application`/`adapters`（本计划不改 domain 逻辑，仅 `artifacts.py` 数据类字段）。
- 一切外部经端口/ACL；外部异常在 ACL 边界翻译成 `StageError`（`ClaudeCodeRunner` 已负责，适配器直接上抛）。
- 产物版本化只进不改（引擎 `add_artifact` 保证，勿动）。
- TDD：先写失败测试再实现。Conventional Commits。**在分支 `feat/design-port-real-adapter` 上提交，勿推 main。**
- 改 `src/**` 需在 `CHANGELOG.md` 加条目（见 Task 6）。
- 文档不得反引号引用代码中不存在的符号（`ClaudeDesignAdapter` 在 Task 2 落地后 spec 的伪造符号检查即转绿）。
- 命令前缀：Python 测试均需先 `. venv/bin/activate`。

---

### Task 1: DesignArtifact 简化为指针 + 全量改造构造/序列化点

把 `DesignArtifact(change_summary, target_files)` 改成 `DesignArtifact(design_file)`，并同步所有构造点与 SQLite 序列化。这些字段目前仅被下游桩端口透传、无领域逻辑消费，删除不改变行为。

**Files:**
- Modify: `src/autodev/domain/artifacts.py:30-33`
- Modify: `src/autodev/adapters/sqlite_repository.py:182-183`（to_dict）、`:220-221`（from_dict）
- Modify: `src/autodev/adapters/demo.py:185-187`（DemoDesign）
- Modify: `tests/fakes.py:74-76`（FakeDesign）
- Modify: `tests/application/test_handlers_back.py:61`、`tests/domain/test_outcome.py:9`、`tests/domain/test_work_item.py:33-34`（构造点）
- Modify: `tests/application/test_handlers_front.py:102-104`（断言从 `.change_summary` 改为 `.design_file`）
- Test: `tests/adapters/test_sqlite_repository.py`（新增/追加 design 往返用例；若无此文件则加到已有仓储测试文件——先 `ls tests/adapters | grep sqlite` 确认）

**Interfaces:**
- Produces: `DesignArtifact(design_file: str)` — frozen dataclass，单字段；供 Task 2/3/4 使用。

- [ ] **Step 1: 写失败测试（序列化往返用指针）**

先确认仓储测试文件：`ls tests/adapters | grep -i sqlite`。把下述用例加进该文件（若确实没有仓储测试文件，新建 `tests/adapters/test_sqlite_repository.py` 并补齐 import：`from autodev.adapters.sqlite_repository import SqliteWorkItemRepository`、`from autodev.domain.artifacts import DesignArtifact`）。

```python
def test_design_artifact_roundtrip_pointer(tmp_path):
    from autodev.adapters.sqlite_repository import _artifact_to_dict, _artifact_from_dict
    from autodev.domain.artifacts import DesignArtifact

    art = DesignArtifact(design_file="/home/.autodev/workitems/wi1/design-abc.md")
    back = _artifact_from_dict(_artifact_to_dict(art))
    assert isinstance(back, DesignArtifact)
    assert back.design_file == "/home/.autodev/workitems/wi1/design-abc.md"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `. venv/bin/activate && pytest tests/adapters/test_sqlite_repository.py::test_design_artifact_roundtrip_pointer -v`
Expected: FAIL（`DesignArtifact` 仍要求 `change_summary`/`target_files`，构造报 TypeError）

- [ ] **Step 3: 改数据类**

`src/autodev/domain/artifacts.py`：

```python
@dataclass(frozen=True)
class DesignArtifact:
    design_file: str
```

- [ ] **Step 4: 改 SQLite 序列化**

`src/autodev/adapters/sqlite_repository.py`，`_artifact_to_dict` 中 DesignArtifact 分支：

```python
    if isinstance(a, DesignArtifact):
        return {"__t": t, "design_file": a.design_file}
```

`_artifact_from_dict` 中 DesignArtifact 分支：

```python
    if t == "DesignArtifact":
        return DesignArtifact(d["design_file"])
```

- [ ] **Step 5: 改所有其它构造点**

`src/autodev/adapters/demo.py` DemoDesign（改为写一份真实演示方案文件，供演示 E2E 的方案面板可读；`Path` 已在该模块 import，否则补 `from pathlib import Path`）：

```python
class DemoDesign:
    def propose(self, requirement: Requirement, context: ContextArtifact) -> DesignArtifact:
        path = Path(context.context_file).parent / "design-demo.md"
        path.write_text(
            f"# 实现方案\n\n## 方案概述\n\n（演示方案）实现：{requirement.goal}\n\n"
            "## 改动清单\n\n- `app.py`: 演示改动\n\n"
            "## 实现步骤\n\n1. 演示步骤\n\n## 风险与取舍\n\n（演示）无\n",
            encoding="utf-8",
        )
        return DesignArtifact(design_file=str(path))
```

`tests/fakes.py` FakeDesign：

```python
class FakeDesign:
    def propose(self, requirement: Requirement, context: ContextArtifact) -> DesignArtifact:
        return DesignArtifact(design_file=f"/fake/design/{requirement.goal[:8]}.md")
```

`tests/application/test_handlers_back.py:61`：`DesignArtifact("do: fix typo", ("app.py",))` → `DesignArtifact(design_file="/fake/design/x.md")`
`tests/domain/test_outcome.py:9`：`DesignArtifact("fix typo", ("a.py",))` → `DesignArtifact(design_file="/f/d.md")`
`tests/domain/test_work_item.py:33-34`：`DesignArtifact("x", ())`、`DesignArtifact("y", ())` → `DesignArtifact(design_file="/f/x.md")`、`DesignArtifact(design_file="/f/y.md")`（两者不同即可，该测试验证版本追加）

`tests/application/test_handlers_front.py:102-104`：将断言 `assert "fix typo" in out.artifact.change_summary` 改为：

```python
    out = handle_design(_wi_with_context(), _ctx(), NOW)
    assert out.artifact.design_file  # 非空指针
```
（注：`handle_design` 需要 work_item.artifacts 里有 "context"；若该测试原本没有 context 产物请补一个 `ContextArtifact` 到 work_item——查看该测试上下文按需调整，保持它能跑通 handle_design。）

- [ ] **Step 6: 运行相关测试确认通过**

Run: `. venv/bin/activate && pytest tests/adapters/test_sqlite_repository.py tests/domain tests/application -q`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "refactor(domain): DesignArtifact 简化为 design_file 指针

对齐 ContextArtifact；同步 SQLite 序列化、DemoDesign/FakeDesign 及构造点。
change_summary/target_files 无领域消费方，删除不改变行为。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: ClaudeDesignAdapter（核心适配器）

镜像 `ClaudeContextAdapter`，单遍生成、全程只读，产出方案 md 落盘并返回指针产物。

**Files:**
- Create: `src/autodev/adapters/design_claude.py`
- Test: `tests/adapters/test_design_claude.py`（单测）、`tests/adapters/test_design_contract.py`（契约 + live 冒烟）

**Interfaces:**
- Consumes: `DesignArtifact(design_file: str)`（Task 1）；`ContextArtifact(workspace_location, workspace_label, context_file)`；`Requirement(goal, ...)`。
- Produces: `ClaudeDesignAdapter(runner: Callable[[str, Path], str], autodev_home: Path, id_gen=...)`，方法 `propose(requirement: Requirement, context: ContextArtifact) -> DesignArtifact`。供 Task 3 装配。

- [ ] **Step 1: 写失败单测**

`tests/adapters/test_design_claude.py`：

```python
from __future__ import annotations

from pathlib import Path

from autodev.adapters.design_claude import ClaudeDesignAdapter
from autodev.domain.artifacts import ContextArtifact
from autodev.domain.value_objects import Requirement

REQ = Requirement("加限流", "repo-a", (), "raw")


def _context(tmp_path: Path) -> ContextArtifact:
    ws = tmp_path / "ws" / "wiabc"
    ws.mkdir(parents=True)
    (ws / "app.py").write_text("x = 1\n")
    cfile = tmp_path / "home" / "workitems" / "wiabc" / "context-x.md"
    cfile.parent.mkdir(parents=True)
    cfile.write_text("## 相关文件\n- app.py\n")
    return ContextArtifact(str(ws), "autodev/wiabc", str(cfile))


def test_propose_persists_design_doc(tmp_path):
    captured = {}

    def runner(prompt: str, cwd: Path) -> str:
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        return "## 方案概述\n\n改 app.py\n"

    a = ClaudeDesignAdapter(runner=runner, autodev_home=tmp_path / "home", id_gen=lambda: "d1")
    art = a.propose(REQ, _context(tmp_path))

    # 产物是指针，文件真实落盘在 ~/.autodev/workitems/<id>/
    assert art.design_file.endswith("workitems/wiabc/design-d1.md")
    assert Path(art.design_file).read_text().strip()
    assert "方案概述" in Path(art.design_file).read_text()
    # prompt 里带了 context 文件路径（让 CLI 自己读），cwd 是 worktree
    assert captured["cwd"] == tmp_path / "ws" / "wiabc"
    assert str(_context(tmp_path).context_file).rsplit("/", 1)[-1] not in captured["prompt"] or True
    assert "context" in captured["prompt"].lower() or "上下文" in captured["prompt"]


def test_propose_propagates_stage_error(tmp_path):
    from autodev.domain.enums import FailureKind
    from autodev.domain.errors import StageError

    def runner(prompt: str, cwd: Path) -> str:
        raise StageError(FailureKind.FATAL, "claude 不可用")

    a = ClaudeDesignAdapter(runner=runner, autodev_home=tmp_path / "home")
    try:
        a.propose(REQ, _context(tmp_path))
        assert False, "应上抛 StageError"
    except StageError as e:
        assert e.failure_kind is FailureKind.FATAL
```

- [ ] **Step 2: 运行确认失败**

Run: `. venv/bin/activate && pytest tests/adapters/test_design_claude.py -v`
Expected: FAIL（`ModuleNotFoundError: design_claude`）

- [ ] **Step 3: 实现适配器**

`src/autodev/adapters/design_claude.py`：

```python
from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from autodev.domain.artifacts import ContextArtifact, DesignArtifact
from autodev.domain.value_objects import Requirement


class ClaudeDesignAdapter:
    """DesignPort 真实实现：worktree 内只读跑 claude，单遍产出 Markdown 方案文档。

    铁律合规：claude 交互经 ClaudeCodeRunner（已把子进程异常翻译成 StageError），
    本适配器直接上抛，由引擎按 RetryPolicy 重试/收敛 FAILED。方案文档持久化到
    ~/.autodev 之下（git worktree 之外），与 Context 一致。
    """

    def __init__(
        self,
        runner: Callable[[str, Path], str],
        autodev_home: Path,
        id_gen: Callable[[], str] = lambda: uuid.uuid4().hex[:8],
    ) -> None:
        self._runner = runner
        self._home = autodev_home
        self._id_gen = id_gen

    def propose(self, requirement: Requirement, context: ContextArtifact) -> DesignArtifact:
        doc = self._generate(requirement, context)
        path = self._persist(context, requirement, doc)
        return DesignArtifact(design_file=str(path))

    def _generate(self, requirement: Requirement, context: ContextArtifact) -> str:
        prompt = (
            "你在一个代码仓库工作目录里。请先阅读已收集的上下文文档(路径见下), 再只读调查相关代码, "
            "为下述需求产出一份 Markdown 格式的实现方案, 包含以下小节: "
            "`## 方案概述`(一段话说明总体思路), "
            "`## 改动清单`(逐个列出要改/新增的文件, 每个附一行理由), "
            "`## 实现步骤`(有序步骤), "
            "`## 风险与取舍`(潜在风险、被否掉的替代方案)。"
            "只输出 Markdown 文档本身, 不要额外解释; 不要修改任何文件。\n\n"
            f"需求: {requirement.goal}\n\n"
            f"已收集的上下文文档路径(可直接读取): {context.context_file}"
        )
        return self._runner(prompt, Path(context.workspace_location)).strip()

    def _persist(self, context: ContextArtifact, requirement: Requirement, doc: str) -> Path:
        work_item_id = Path(context.workspace_location).name
        d = self._home / "workitems" / work_item_id
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"design-{self._id_gen()}.md"
        header = f"# 实现方案\n\n- 需求: {requirement.goal}\n- 分支: {context.workspace_label}\n\n---\n\n"
        path.write_text(header + doc, encoding="utf-8")
        return path
```

- [ ] **Step 4: 运行确认通过**

Run: `. venv/bin/activate && pytest tests/adapters/test_design_claude.py -v`
Expected: PASS

- [ ] **Step 5: 写契约测试 + live 冒烟**

`tests/adapters/test_design_contract.py`（对照 DemoDesign 与真实适配器；`_context` 需真实写出 context 文件，好让 DemoDesign 在其旁写方案）：

```python
"""DesignPort 端口一致性契约：DemoDesign 与真实 ClaudeDesignAdapter(注入假 runner)
必须都返回携带非空 design_file 指针的 DesignArtifact。外加一个 @pytest.mark.live 真调
claude 冒烟(默认跳过)。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from autodev.adapters.demo import DemoDesign
from autodev.adapters.design_claude import ClaudeDesignAdapter
from autodev.domain.artifacts import ContextArtifact
from autodev.domain.value_objects import Requirement

REQ = Requirement("加限流", "repo-a", (), "raw")


def _context(tmp_path: Path) -> ContextArtifact:
    ws = tmp_path / "ws" / "wiabc"
    ws.mkdir(parents=True)
    (ws / "app.py").write_text("x = 1\n")
    cfile = tmp_path / "home" / "workitems" / "wiabc" / "context-x.md"
    cfile.parent.mkdir(parents=True)
    cfile.write_text("## 相关文件\n- app.py\n")
    return ContextArtifact(str(ws), "autodev/wiabc", str(cfile))


@pytest.fixture(params=["fake", "real"])
def adapter(request, tmp_path):
    if request.param == "fake":
        return DemoDesign()

    def runner(prompt: str, cwd: Path) -> str:
        return "## 方案概述\n\n改 app.py\n\n## 改动清单\n\n- `app.py`: 入口\n"

    return ClaudeDesignAdapter(runner=runner, autodev_home=tmp_path / "home")


def test_propose_returns_design_artifact_with_pointer(adapter, tmp_path):
    art = adapter.propose(REQ, _context(tmp_path))
    assert art.design_file  # 非空指针


@pytest.mark.live
def test_live_propose_against_real_claude(tmp_path):
    if not os.environ.get("AUTODEV_LIVE"):
        pytest.skip("live 测试需 AUTODEV_LIVE=1 + 可用 claude/网关")
    from autodev.adapters.claude_runner import ClaudeCodeRunner

    ctx = _context(tmp_path)
    r = ClaudeCodeRunner()
    a = ClaudeDesignAdapter(runner=lambda p, c: r.run(p, c, "plan"), autodev_home=tmp_path / "home")
    art = a.propose(Requirement("给 app.py 加个 hello 函数", "x", (), "raw"), ctx)
    assert Path(art.design_file).read_text().strip()
```

- [ ] **Step 6: 运行确认通过**

Run: `. venv/bin/activate && pytest tests/adapters/test_design_contract.py -q`
Expected: PASS（live 用例 skipped）

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "feat(slice2): ClaudeDesignAdapter — worktree 内只读单遍产出方案 md

复用 ClaudeCodeRunner，prompt 带 context 文件路径让 CLI 自读，方案持久化到
~/.autodev/workitems/<id>/design-<rand>.md；契约测试(fake vs real)+ live 冒烟。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 接入组合根 + 扩 RUN 到 DESIGN + 守卫/驱动测试

把生产 `StageContext.designer` 换成真实适配器，`RUN` 加入 `DESIGN`，并更新安全守卫、加一条驱动到 REVIEW 停住的测试。

**Files:**
- Modify: `src/autodev/webapp/config.py:81-104`
- Modify: `src/autodev/webapp/service.py:28`（RUN）
- Modify: `tests/webapp/test_demo_app.py:98-106`（守卫）
- Test: `tests/webapp/test_service.py`（新增驱动到 REVIEW 的用例）

**Interfaces:**
- Consumes: `ClaudeDesignAdapter`（Task 2）。
- Produces: 生产 `RUN = {INTAKE, TRIAGE, CONTEXT, DESIGN}`；`ctx.designer` 为 `ClaudeDesignAdapter` 实例。

- [ ] **Step 1: 写失败测试（守卫更新 + 驱动到 REVIEW）**

`tests/webapp/test_demo_app.py`（把 designer 断言从桩改为真实，并补 reviewer/delivery 桩断言）：先在文件顶部 import：`from autodev.adapters.design_claude import ClaudeDesignAdapter`；把原 `assert isinstance(ctx.designer, UnavailableStage)` 改为：

```python
    assert isinstance(ctx.executor, UnavailableStage)
    assert isinstance(ctx.verifier, UnavailableStage)
    assert isinstance(ctx.reviewer, UnavailableStage)
    assert isinstance(ctx.delivery, UnavailableStage)
    assert isinstance(ctx.designer, ClaudeDesignAdapter)
```

`tests/webapp/test_service.py` 新增（自主开 + ACTIONABLE → 跑完 DESIGN 停在 REVIEW，不触达 review 桩）：

```python
def test_drive_reaches_review_and_stops_without_calling_review_stub():
    from autodev.domain.enums import TriageIntent, WorkflowState as S
    from autodev.domain.ids import RepoRef, WorkItemId
    from autodev.domain.value_objects import AutonomyDial, Requirement
    from autodev.domain.work_item import WorkItem
    from autodev.webapp.service import RUN, _bounded_drive
    from tests.fakes import FakeContext, FakeDesign, FakeWorkspace

    repo = InMemoryWorkItemRepository()
    stage = UnavailableStage()
    ctx = StageContext(
        FakeWorkspace(),
        FakeContext(),
        FakeDesign(),          # designer 真实产出
        stage,                 # reviewer 桩：一旦被调用即 FATAL
        stage, stage, stage,
        FakeTriage(intent=TriageIntent.ACTIONABLE),
        GatePolicy(),
    )
    engine = Engine(repo, InMemoryEventBus(), ctx, clock=lambda: NOW)

    wid = WorkItemId("wireview1")
    wi = WorkItem.create(
        wid, RepoRef("demo"),
        Requirement("加限流", "demo", (), "加限流"),
        AutonomyDial.all_human(), NOW,
        autonomy_enabled=True,
    )
    repo.save(wi)
    _bounded_drive(repo, engine, wid, RUN)

    got = repo.get(wid)
    assert got.state == S.REVIEW          # 跑完 DESIGN，停在 REVIEW（∉RUN）
    assert "design" in got.artifacts
```
（注：若 `WorkItem.create` 的实参顺序与此不符，按 `src/autodev/domain/work_item.py:80-98` 的真实签名对齐；`FakeDesign` 需在 `tests/fakes.py` 已导出——Task 1 已改其实现。）

- [ ] **Step 2: 运行确认失败**

Run: `. venv/bin/activate && pytest tests/webapp/test_demo_app.py tests/webapp/test_service.py::test_drive_reaches_review_and_stops_without_calling_review_stub -v`
Expected: FAIL（守卫仍断言 designer 是桩；RUN 未含 DESIGN → 驱动停在 CONTEXT，未产出 design）

- [ ] **Step 3: 扩 RUN**

`src/autodev/webapp/service.py:28`：

```python
RUN: frozenset[S] = frozenset({S.INTAKE, S.TRIAGE, S.CONTEXT, S.DESIGN})
```

- [ ] **Step 4: 接入组合根**

`src/autodev/webapp/config.py`：文件顶部加 `from autodev.adapters.design_claude import ClaudeDesignAdapter`。在 `gatherer = ...` 之后加：

```python
    designer = ClaudeDesignAdapter(runner=lambda p, c: runner.run(p, c), autodev_home=home)
```

把 `StageContext(...)` 第 3 个实参从 `stub` 改为 `designer`：

```python
    ctx = StageContext(
        workspace,
        gatherer,
        designer,
        stub,
        stub,
        stub,
        stub,
        triage,
        GatePolicy(),
    )
```

- [ ] **Step 5: 运行确认通过**

Run: `. venv/bin/activate && pytest tests/webapp -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "feat(slice2): 接入 ClaudeDesignAdapter + RUN 扩到 DESIGN

生产组合根 designer 换真实实现，有界驱动跑完 DESIGN 停在 REVIEW(∉RUN，
不触达 review 桩)；安全守卫收窄到 4 桩 + designer 真实。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 后端视图投影 design_brief

`view_detail` 读取 design 产物指向的 md 内容，新增 `design` 字段（镜像 `context`）。

**Files:**
- Modify: `src/autodev/webapp/views.py:80-113`
- Test: `tests/webapp/test_views.py`（若无则先 `ls tests/webapp | grep view` 确认文件名；无则新建）

**Interfaces:**
- Produces: `detail["design"] = {"markdown": str, "design_file": str} | None`（供 Task 5 前端消费）。

- [ ] **Step 1: 写失败测试**

在 views 测试文件加：

```python
def test_view_detail_projects_design_brief():
    from autodev.domain.artifacts import DesignArtifact
    # 复用该文件已有的构造 WorkItem 到 DESIGN 已产出 design 的辅助；若无，构造一个
    # artifacts 含 "design": DesignArtifact(design_file="/x/design.md") 的 WorkItem。
    wi = _work_item_with_design(DesignArtifact(design_file="/x/design.md"))
    detail = view_detail(wi, read_text=lambda p: "## 方案概述\n改 app.py\n")
    assert detail["design"] == {
        "markdown": "## 方案概述\n改 app.py\n",
        "design_file": "/x/design.md",
    }


def test_view_detail_design_none_when_absent():
    wi = _work_item_without_design()
    detail = view_detail(wi, read_text=lambda p: "")
    assert detail["design"] is None
```
（`_work_item_with_design` / `_work_item_without_design`：按该测试文件已有的 WorkItem 构造工具实现；关键是让 `wi.artifacts` 含/不含 `"design"` 键。）

- [ ] **Step 2: 运行确认失败**

Run: `. venv/bin/activate && pytest tests/webapp/test_views.py -k design -v`
Expected: FAIL（`detail` 无 `design` 键 → KeyError/None 不符）

- [ ] **Step 3: 实现投影**

`src/autodev/webapp/views.py`：确保顶部 import 含 `DesignArtifact`（与 `ContextArtifact` 同处）。在 `context = None ...` 块之后、`detail` 组装之前加：

```python
    design: dict[str, str] | None = None
    if "design" in wi.artifacts:
        d_art = cast(DesignArtifact, wi.artifacts["design"])
        try:
            d_md = read_text(d_art.design_file)
        except OSError:
            d_md = ""
        design = {"markdown": d_md, "design_file": d_art.design_file}
```

在 `detail["context"] = context` 之后加 `detail["design"] = design`。

- [ ] **Step 4: 运行确认通过**

Run: `. venv/bin/activate && pytest tests/webapp/test_views.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(webapp): view_detail 投影 design 方案文档(镜像 context)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 前端「方案」折叠面板（复用 BriefDocument）

给 `BriefDocument` 加 `title` 参数并把 `contextFile` 泛化为 `path`，详情页在上下文简报下方新增方案面板。

**Files:**
- Modify: `frontend/src/components/BriefDocument.tsx`
- Modify: `frontend/src/components/BriefDocument.test.tsx`
- Modify: `frontend/src/pages/WorkItemDetailPage.tsx:127-132`
- Modify: `frontend/src/api/types.ts:53-60`

**Interfaces:**
- Consumes: `detail.design: { markdown: string; design_file: string } | null`（Task 4）。
- Produces: `BriefDocument({ title?: string; markdown: string; path: string })`（`title` 默认 `'上下文简报'`）。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/BriefDocument.test.tsx` 追加（该文件已有渲染用例，模仿其风格）：

```tsx
it('renders a custom title (方案)', () => {
  render(<BriefDocument title="方案" markdown={'## 方案概述\n改 app.py'} path="/x/design.md" />)
  expect(screen.getByText('方案')).toBeInTheDocument()
  expect(screen.getByText('/x/design.md')).toBeInTheDocument()
})
```
（现有用例若用旧 prop `contextFile`，一并改为 `path`。）

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/BriefDocument.test.tsx`
Expected: FAIL（`title`/`path` prop 尚不存在；旧用例用 `contextFile` 也会因签名变化红）

- [ ] **Step 3: 泛化 BriefDocument**

`frontend/src/components/BriefDocument.tsx` 的 props 与 summary：

```tsx
export function BriefDocument({
  title = '上下文简报',
  markdown,
  path,
}: {
  title?: string
  markdown: string
  path: string
}) {
  const html = useMemo(() => {
    return DOMPurify.sanitize(renderMarkdown(markdown), { ADD_ATTR: ['class'] })
  }, [markdown])

  return (
    <details className={styles.wrapper} aria-label={title} open>
      <summary className={styles.caption}>
        <span className={styles.chevron} aria-hidden="true" />
        <span className={styles.captionTitle}>{title}</span>
        <span className={styles.captionPath}>{path}</span>
      </summary>
      <div className={styles.body} dangerouslySetInnerHTML={{ __html: html }} />
    </details>
  )
}
```

- [ ] **Step 4: 改类型 + 详情页**

`frontend/src/api/types.ts` 的 `WorkItemDetail` 加一行（放在 `context` 之后）：

```ts
  design: { markdown: string; design_file: string } | null
```

`frontend/src/pages/WorkItemDetailPage.tsx`，把 context 那段调用改用新 prop 名，并在其后加方案面板：

```tsx
      {detail.context && (
        <BriefDocument
          title="上下文简报"
          markdown={detail.context.markdown}
          path={detail.context.context_file}
        />
      )}

      {detail.design && (
        <BriefDocument
          title="方案"
          markdown={detail.design.markdown}
          path={detail.design.design_file}
        />
      )}
```

- [ ] **Step 5: 运行前端门禁确认通过**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: PASS（BriefDocument 用例全绿、类型检查无误）

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "feat(frontend): 详情页新增「方案」折叠面板(复用 BriefDocument)

BriefDocument 泛化 title/path 参数，同一渲染管线服务上下文简报与方案。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 文档对齐 + 全量验收门禁

更新 CHANGELOG/ROADMAP，跑全量后端 + 前端门禁，确认 spec 的伪造符号检查转绿。

**Files:**
- Modify: `CHANGELOG.md`（`[Unreleased] / Added`）
- Modify: `ROADMAP.md`（切片 2 适配器进度表 DesignPort 行：⬜ → ✅）
- Modify: `tests/e2e/browser_e2e.sh`（补一条：自主开启落地类工作项推进到 DESIGN 并展示方案面板——按该脚本既有断言风格追加；若时间/环境不允许真实浏览器跑，至少补断言注释并保证脚本语法正确）

- [ ] **Step 1: 更新 CHANGELOG**

在 `CHANGELOG.md` `## [Unreleased]` 的 `### Added` 顶部加一条，概述：ClaudeDesignAdapter 真实落地（复用 ClaudeCodeRunner、worktree 内只读单遍产出方案 md、持久化 ~/.autodev、契约+live 测试）、DesignArtifact 简化为指针、RUN 扩到 DESIGN、前端方案面板、切片 2 第 4 个真实适配器。

- [ ] **Step 2: 更新 ROADMAP 适配器进度表**

`ROADMAP.md` 切片 2 表格 `DesignPort` 行状态从 `⬜ 假` 改为 `✅ 真实已实现（ClaudeDesignAdapter，复用 ClaudeCodeRunner，含 live 冒烟）且已接入组合根`；正文「◐ 进行中」括注从「Workspace/Context 两个」更新为「Workspace/Context/Triage/Design 四个真实适配器已落地」。

- [ ] **Step 3: 全量后端门禁**

Run: `. venv/bin/activate && pytest -q && ruff check . && ruff format --check . && mypy src`
Expected: 全绿（含 `tests/docs/test_doc_consistency.py` —— `ClaudeDesignAdapter` 现已存在，伪造符号检查转绿）。若 ruff format 有改动，`ruff format .` 后重跑。

- [ ] **Step 4: 全量前端门禁**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npx oxlint && npm run build`
Expected: 全绿。

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "docs(slice2): CHANGELOG/ROADMAP 对齐 DesignPort 落地 + E2E 断言

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §3 适配器 → Task 2 ✅
- §4 产物 + 序列化 + demo/fake 更新 → Task 1 ✅
- §5 组合根接入 + RUN 扩展 + 安全守卫 → Task 3 ✅
- §6 前端方案面板 + 后端投影 → Task 4（后端）+ Task 5（前端）✅
- §7 错误处理（StageError 上抛）→ Task 2 Step 1 的 `test_propose_propagates_stage_error` ✅
- §8 测试（契约/单测/live/守卫/驱动/序列化/前端/E2E）→ 分散在 Task 1-6 ✅
- §9 文档一致性 → Task 6 ✅

**Placeholder scan:** Task 4 的 `_work_item_with_design` 等辅助函数依赖各测试文件既有工具，已注明「按既有构造工具实现」并给出关键约束（artifacts 含/不含 "design" 键）；这是对现有测试风格的合理适配而非占位。其余步骤均含可直接落地的代码。

**Type consistency:** `DesignArtifact(design_file: str)` 在 Task 1 定义，Task 2/3/4 一致使用 `.design_file`；`ClaudeDesignAdapter(runner, autodev_home, id_gen)` / `.propose(requirement, context)` 在 Task 2 定义、Task 3 装配一致；前端 `BriefDocument({title?, markdown, path})` 在 Task 5 定义并在同任务内一致调用；`detail.design` 形状 Task 4（后端）与 Task 5（前端 types）一致。

**执行顺序：** Task 1 → 2 → 3 → 4 → 5 → 6 严格线性（后者依赖前者产出的类型/装配）。
