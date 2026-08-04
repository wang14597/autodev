# ReviewPort 真实适配器（评审产出最终方案）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 REVIEW 阶段真实运行——读上下文与方案两份文档、只读核对真实代码，产出一份最终方案文档作为下游权威输入；同时修掉"回退重设计拿不到评审意见"的死结。

**Architecture:** 新增评审适配器复用 `ClaudeCodeRunner`（子进程 `claude`，`permission-mode plan` 只读，cwd 为工作项 worktree），单遍调用，输出用**首行哨兵**格式携带判决，解析成 `approved` / `comments` / 最终方案正文三部分；正文落盘 `~/.autodev/workitems/<id>/final-plan-<rand>.md`，产物只存指针。领域状态机、`GatePoint`、`GatePolicy` 零改动。

**Tech Stack:** Python 3.14 + FastAPI + SQLite（后端）；Vite + React + TypeScript + TanStack Query（前端）；pytest / ruff / mypy / vitest。

**设计依据：** [ReviewPort 真实适配器设计](../specs/2026-08-03-review-port-real-adapter-design.md)

## Global Constraints

- **铁律 1 核心域纯净**：`src/autodev/domain` 不得 import 任何外部系统 SDK，也不得 import `application` / `adapters`。本计划对 domain 的改动仅限加字段与改 Protocol 签名。
- **铁律 2 一切外部经端口/ACL**：`claude` 子进程只经 `ClaudeCodeRunner` 调用，实现放 `src/autodev/adapters/`。
- **铁律 3 失败翻译前置**：适配器不吞异常、不自行重试；`ClaudeCodeRunner` 已把子进程异常翻译成 `StageError`，直接上抛给引擎。
- **铁律 4 产物版本化只进不改**：只用 `add_artifact` 追加，绝不覆盖既有版本。
- **铁律 5 人审是一等状态**：`WAIT_HUMAN` / `GatePoint` / `GatePolicy` / `resume_target` 一律零改动。
- **铁律 7 一切失败收敛到 FAILED**：不新增任何重试；沿用 `RetryPolicy` 的 `CAP = 3`。
- **TDD**：每个任务先写失败测试，跑一次确认它失败，再写实现。
- **Conventional Commits**，提交在当前分支 `feat/review-port-real-adapter` 上，**不要切回或推 main**。
- **改 `src/**` 必须在 `CHANGELOG.md` 加条目**（Task 6 统一做），否则 CI 的 doc-impact job 会红。
- **文档一致性**：正文行内反引号里不得出现代码中不存在的 CamelCase 符号（围栏代码块内不受此限）。
- 全量验收命令：`pytest -q && ruff check . && ruff format --check . && mypy src`，前端 `cd frontend && npm run typecheck && npm run lint && npm run test && npm run build`。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `src/autodev/adapters/review_claude.py`（新） | 评审适配器 + 输出解析纯函数 |
| `src/autodev/domain/artifacts.py` | `ReviewArtifact` 加最终方案指针字段 |
| `src/autodev/domain/ports.py` | `DesignPort` 加上一轮评审入参 |
| `src/autodev/adapters/sqlite_repository.py` | 新字段的序列化/反序列化 |
| `src/autodev/application/handlers.py` | `handle_design` 透传上一轮评审；`handle_impl` 取权威方案 |
| `src/autodev/adapters/design_claude.py` | 接受并使用上一轮评审意见 |
| `src/autodev/adapters/demo.py` | 演示评审端口产出演示最终方案；演示设计端口签名同步 |
| `tests/fakes.py` / `src/autodev/webapp/stubs.py` | 签名同步 |
| `src/autodev/webapp/config.py` | 装配真实评审端口 |
| `src/autodev/webapp/drive.py` | 能力集合加 REVIEW |
| `src/autodev/webapp/views.py` | `review` 投影 |
| `frontend/src/components/ReviewComments.tsx`（新） | 评审意见列表（blocking / suggestion 区分） |
| `frontend/src/pages/WorkItemDetailPage.tsx` | 「最终方案」面板 + 意见列表 |
| `frontend/src/api/types.ts` | `review` DTO |

---

### Task 1: `ReviewArtifact` 携带最终方案指针（含持久化）

**Files:**
- Modify: `src/autodev/domain/artifacts.py:35-38`
- Modify: `src/autodev/adapters/sqlite_repository.py:184-185`（序列化）、`:223-224`（反序列化）
- Test: `tests/adapters/test_sqlite_repository.py`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: `ReviewArtifact(approved: bool, comments: tuple[str, ...], final_plan_file: str = "")`。后续任务全部依赖这个字段名与默认值。

- [ ] **Step 1: 写失败测试**

追加到 `tests/adapters/test_sqlite_repository.py` 末尾（文件顶部若缺 `ReviewArtifact` 导入则补上）：

```python
def test_review_artifact_round_trips_final_plan_pointer(tmp_path):
    """评审产物的最终方案指针必须能存能取——否则重启后下游拿不到权威方案。"""
    from autodev.domain.artifacts import ReviewArtifact

    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite3"))
    wi = _wi()
    wi.add_artifact(
        "review",
        ReviewArtifact(True, ("- suggestion: 补个测试",), final_plan_file="/x/final-plan-a1.md"),
    )
    repo.save(wi)

    loaded = repo.get(wi.id)
    art = loaded.artifacts["review"]
    assert art.approved is True
    assert art.comments == ("- suggestion: 补个测试",)
    assert art.final_plan_file == "/x/final-plan-a1.md"


def test_review_artifact_from_old_row_without_pointer_defaults_empty(tmp_path):
    """旧行没有该键时兜底空串（照 TriageArtifact 的 risk/signals 先例）。"""
    from autodev.adapters.sqlite_repository import _artifact_from_dict

    art = _artifact_from_dict({"__t": "ReviewArtifact", "approved": False, "comments": ["x"]})
    assert art.final_plan_file == ""
```

`_wi()` 是该测试文件第 17 行已有的工作项构造 helper。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest -q tests/adapters/test_sqlite_repository.py -k review_artifact`
Expected: FAIL —— `TypeError: ReviewArtifact.__init__() got an unexpected keyword argument 'final_plan_file'`

- [ ] **Step 3: 加字段**

`src/autodev/domain/artifacts.py`：

```python
@dataclass(frozen=True)
class ReviewArtifact:
    approved: bool
    comments: tuple[str, ...]
    # 评审产出的最终方案文档路径（下游 IMPL 的权威输入）。加默认值向后兼容：
    # 旧持久化产物与演示/假适配器无需同步改造。判定"无法自救"而回退重设计时为空串。
    final_plan_file: str = ""
```

- [ ] **Step 4: 同步 SQLite 序列化**

`src/autodev/adapters/sqlite_repository.py` 的 `_artifact_to_dict`：

```python
    if isinstance(a, ReviewArtifact):
        return {
            "__t": t,
            "approved": a.approved,
            "comments": list(a.comments),
            "final_plan_file": a.final_plan_file,
        }
```

`_artifact_from_dict`：

```python
    if t == "ReviewArtifact":
        # 旧行无 final_plan_file 键 → 兜底空串（向后兼容）
        return ReviewArtifact(
            d["approved"], tuple(d["comments"]), d.get("final_plan_file", "")
        )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest -q tests/adapters/test_sqlite_repository.py && mypy src`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src/autodev/domain/artifacts.py src/autodev/adapters/sqlite_repository.py tests/adapters/test_sqlite_repository.py
git commit -m "feat(domain): ReviewArtifact 携带最终方案指针 + 持久化兼容旧行"
```

---

### Task 2: 回退重设计带上上一轮评审意见

**Files:**
- Modify: `src/autodev/domain/ports.py:52-53`
- Modify: `src/autodev/application/handlers.py:82-85`
- Modify: `src/autodev/adapters/design_claude.py:29-46`
- Modify: `src/autodev/adapters/demo.py:185-194`、`tests/fakes.py:74-76`、`src/autodev/webapp/stubs.py`
- Test: `tests/application/test_handlers_front.py`、`tests/adapters/test_design_claude.py`

**Interfaces:**
- Consumes: Task 1 的 `ReviewArtifact`
- Produces: `DesignPort.propose(requirement, context, prior_review: ReviewArtifact | None = None) -> DesignArtifact`。所有实现（真实 / 演示 / 假件 / 桩）都接这三个参数。

**为什么非做不可：** `approved=False` → `RetryPolicy` 回退 DESIGN → 引擎重跑 `handle_design`。若端口方法只收需求与上下文，设计员看不见被否理由，同样输入产同样方案，招来同样打回，烧完 `CAP` 收敛 FAILED。在演示评审端口永远通过的年代这条路不可达；本次把拒绝变成真的，不能交付一条已知走不通的路。

- [ ] **Step 1: 写失败测试（判别性）**

追加到 `tests/application/test_handlers_front.py`（顶部补 `from autodev.domain.artifacts import DesignArtifact, ReviewArtifact` 与 `from autodev.domain.artifacts import ContextArtifact`，按文件现有导入风格合并）：

```python
def test_design_receives_prior_review_on_rollback():
    """回退重设计必须把上一轮评审意见带给设计端口。

    判别性：旧实现只传 (requirement, context)，本用例断言端口确实收到了那份评审产物；
    回退旧实现时 seen == [None]，用例失败。
    """
    seen: list[object] = []

    class RecordingDesign:
        def propose(self, requirement, context, prior_review=None):
            seen.append(prior_review)
            return DesignArtifact(design_file="/x/design.md")

    wi = _wi()
    wi.add_artifact("context", ContextArtifact("/tmp/ws/wi1", "autodev/wi1", "/tmp/ctx.md"))
    rejected = ReviewArtifact(False, ("- blocking: 方案方向不对",))
    wi.add_artifact("review", rejected)

    ctx = _ctx()
    ctx.designer = RecordingDesign()
    handle_design(wi, ctx, NOW)

    assert seen == [rejected]


def test_design_receives_none_on_first_pass():
    """首轮设计（无评审产物）必须传 None，不能凭空造一个空评审。"""
    seen: list[object] = []

    class RecordingDesign:
        def propose(self, requirement, context, prior_review=None):
            seen.append(prior_review)
            return DesignArtifact(design_file="/x/design.md")

    wi = _wi()
    wi.add_artifact("context", ContextArtifact("/tmp/ws/wi1", "autodev/wi1", "/tmp/ctx.md"))
    ctx = _ctx()
    ctx.designer = RecordingDesign()
    handle_design(wi, ctx, NOW)

    assert seen == [None]
```

（`StageContext` 是普通 `@dataclass`、非 frozen，`ctx.designer = ...` 直接赋值即可。）

再追加到 `tests/adapters/test_design_claude.py`：

```python
def test_propose_puts_prior_review_comments_into_prompt(tmp_path):
    """回退重设计时，被否理由必须出现在提示词里——否则模型无从改进。"""
    from autodev.domain.artifacts import ReviewArtifact

    captured = {}

    def runner(prompt: str, cwd: Path) -> str:
        captured["prompt"] = prompt
        return "## 方案概述\n\n改 app.py\n"

    a = ClaudeDesignAdapter(runner=runner, autodev_home=tmp_path / "home", id_gen=lambda: "d2")
    a.propose(
        REQ,
        _context(tmp_path),
        ReviewArtifact(False, ("- blocking: 漏了鉴权中间件",)),
    )
    assert "漏了鉴权中间件" in captured["prompt"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest -q tests/application/test_handlers_front.py -k prior_review tests/adapters/test_design_claude.py -k prior_review`
Expected: FAIL —— `TypeError: propose() takes 3 positional arguments but 4 were given`（或断言 `seen == [None]` 时收到 `[]`）

- [ ] **Step 3: 改端口协议**

`src/autodev/domain/ports.py`：

```python
class DesignPort(Protocol):
    def propose(
        self,
        requirement: Requirement,
        context: ContextArtifact,
        prior_review: ReviewArtifact | None = None,
    ) -> DesignArtifact: ...
```

（`ReviewArtifact` 在该文件已因 `ReviewPort` 而导入，无需新增 import。若未导入则补。）

- [ ] **Step 4: `handle_design` 透传**

`src/autodev/application/handlers.py`（顶部 `from autodev.domain.artifacts import (...)` 里加 `ReviewArtifact`）：

```python
def handle_design(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    context = cast(ContextArtifact, work_item.artifacts["context"])
    # 回退重设计时把上一轮评审意见带回设计员：否则同样输入产同样方案、招来同样打回，
    # 烧完 RetryPolicy 的 CAP 后收敛 FAILED（这条回退路径此前不可达，故从未暴露）。
    prior = work_item.artifacts.get("review")
    prior_review = prior if isinstance(prior, ReviewArtifact) else None
    artifact = ctx.designer.propose(work_item.requirement, context, prior_review)
    return StageOutcome.ok("design", artifact)
```

- [ ] **Step 5: 真实设计适配器用上它**

`src/autodev/adapters/design_claude.py`：

```python
    def propose(
        self,
        requirement: Requirement,
        context: ContextArtifact,
        prior_review: ReviewArtifact | None = None,
    ) -> DesignArtifact:
        doc = self._generate(requirement, context, prior_review)
        path = self._persist(context, requirement, doc)
        return DesignArtifact(design_file=str(path))

    def _generate(
        self,
        requirement: Requirement,
        context: ContextArtifact,
        prior_review: ReviewArtifact | None = None,
    ) -> str:
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
        if prior_review is not None and prior_review.comments:
            prompt += (
                "\n\n注意: 上一轮方案已被评审否决, 理由如下。"
                "请针对性重做, 不要重复同样的选择:\n"
                + "\n".join(f"- {c}" for c in prior_review.comments)
            )
        return self._runner(prompt, Path(context.workspace_location)).strip()
```

顶部导入加 `ReviewArtifact`：`from autodev.domain.artifacts import ContextArtifact, DesignArtifact, ReviewArtifact`

- [ ] **Step 6: 其余三处实现同步签名**

`src/autodev/adapters/demo.py` 的演示设计端口：

```python
class DemoDesign:
    def propose(
        self,
        requirement: Requirement,
        context: ContextArtifact,
        prior_review: ReviewArtifact | None = None,
    ) -> DesignArtifact:
```
（方法体不变；顶部 `from autodev.domain.artifacts import (...)` 已含 `ReviewArtifact`。）

`tests/fakes.py`：

```python
class FakeDesign:
    def propose(
        self,
        requirement: Requirement,
        context: ContextArtifact,
        prior_review: ReviewArtifact | None = None,
    ) -> DesignArtifact:
        return DesignArtifact(design_file=f"/fake/design/{requirement.goal[:8]}.md")
```
（顶部导入已含 `ReviewArtifact`。）

`src/autodev/webapp/stubs.py`：

```python
    def propose(
        self,
        requirement: Requirement,
        context: ContextArtifact,
        prior_review: ReviewArtifact | None = None,
    ) -> DesignArtifact:
        raise StageError(FailureKind.FATAL, _MESSAGE)
```

- [ ] **Step 7: 跑测试确认通过**

Run: `pytest -q && mypy src`
Expected: 全部 PASS（`mypy` 尤其重要——Protocol 结构化匹配漏改任何一处实现都会在这里报错）

- [ ] **Step 8: 提交**

```bash
git add src/autodev/domain/ports.py src/autodev/application/handlers.py src/autodev/adapters/design_claude.py src/autodev/adapters/demo.py src/autodev/webapp/stubs.py tests/fakes.py tests/application/test_handlers_front.py tests/adapters/test_design_claude.py
git commit -m "fix(design): 回退重设计带上上一轮评审意见, 修掉必然撞 CAP 的死结"
```

---

### Task 3: 评审适配器（解析 + 落盘）

**Files:**
- Create: `src/autodev/adapters/review_claude.py`
- Modify: `src/autodev/adapters/demo.py`（演示评审端口产出演示最终方案）
- Test: `tests/adapters/test_review_claude.py`（新）、`tests/adapters/test_review_contract.py`（新）

**Interfaces:**
- Consumes: Task 1 的 `ReviewArtifact(..., final_plan_file)`；`ClaudeCodeRunner` 的 `run(prompt, cwd, permission_mode) -> str`
- Produces（后续任务按这两个名字引用）：

```python
def parse_review_output(raw: str) -> tuple[bool, tuple[str, ...], str]: ...   # (approved, comments, body)

class ClaudeReviewAdapter:
    def __init__(
        self,
        runner: Callable[[str, Path], str],
        autodev_home: Path,
        id_gen: Callable[[], str] = ...,
    ) -> None: ...
    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact: ...
```

- [ ] **Step 1: 写失败测试（解析）**

创建 `tests/adapters/test_review_claude.py`：

```python
from __future__ import annotations

from pathlib import Path

import pytest

from autodev.adapters.review_claude import ClaudeReviewAdapter, parse_review_output
from autodev.domain.artifacts import ContextArtifact, DesignArtifact
from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError


def _context(tmp_path: Path) -> ContextArtifact:
    ws = tmp_path / "ws" / "wiabc"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "app.py").write_text("x = 1\n")
    cfile = tmp_path / "home" / "workitems" / "wiabc" / "context-x.md"
    cfile.parent.mkdir(parents=True, exist_ok=True)
    cfile.write_text("## 相关文件\n- app.py\n")
    return ContextArtifact(str(ws), "autodev/wiabc", str(cfile))


DESIGN = DesignArtifact(design_file="/x/design-d1.md")


def test_parse_approved_with_separator():
    approved, comments, body = parse_review_output(
        "REVIEW: APPROVED\n"
        "- suggestion: 补个测试\n"
        "---\n"
        "## 方案概述\n\n改 app.py\n"
    )
    assert approved is True
    assert comments == ("- suggestion: 补个测试",)
    assert body.startswith("## 方案概述")


def test_parse_blocked_collects_blocking_comments():
    approved, comments, body = parse_review_output(
        "REVIEW: BLOCKED\n- blocking: 需求自相矛盾\n---\n"
    )
    assert approved is False
    assert comments == ("- blocking: 需求自相矛盾",)
    assert body == ""


def test_parse_sentinel_without_separator_treats_rest_as_body():
    """缺 --- 分隔符不算格式错误：意见行之后的剩余全部是正文。"""
    approved, comments, body = parse_review_output(
        "REVIEW: APPROVED\n- suggestion: 小改\n## 方案概述\n\n正文\n"
    )
    assert approved is True
    assert comments == ("- suggestion: 小改",)
    assert body.startswith("## 方案概述")


def test_parse_without_sentinel_degrades_to_approved():
    """首行不是哨兵 → 降级为通过、整份当正文。

    降级方向是有意选的：误判通过只多走一次人审，误判回退要烧一次 CAP 配额并重跑数分钟。
    """
    approved, comments, body = parse_review_output("## 方案概述\n\n直接给了方案\n")
    assert approved is True
    assert comments == ()
    assert body.startswith("## 方案概述")


def test_review_persists_final_plan_and_returns_pointer(tmp_path):
    captured = {}

    def runner(prompt: str, cwd: Path) -> str:
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        return "REVIEW: APPROVED\n---\n## 方案概述\n\n最终方案正文\n\n## 评审说明\n\n补了鉴权\n"

    a = ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home", id_gen=lambda: "r1")
    art = a.review(DESIGN, _context(tmp_path))

    assert art.approved is True
    assert art.final_plan_file.endswith("workitems/wiabc/final-plan-r1.md")
    text = Path(art.final_plan_file).read_text()
    assert "最终方案正文" in text
    # 头部只记分支与初稿路径（端口签名拿不到 Requirement，不能写需求）
    assert "autodev/wiabc" in text
    assert "/x/design-d1.md" in text
    # 提示词把两份文档的绝对路径都给了 CLI，cwd 是 worktree
    assert str(_context(tmp_path).context_file) in captured["prompt"]
    assert "/x/design-d1.md" in captured["prompt"]
    assert captured["cwd"] == tmp_path / "ws" / "wiabc"


def test_review_approved_but_empty_body_is_logic_error(tmp_path):
    """通过却没给方案 → LOGIC 失败。空方案绝不能交下游。"""

    def runner(prompt: str, cwd: Path) -> str:
        return "REVIEW: APPROVED\n---\n   \n"

    a = ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home")
    with pytest.raises(StageError) as e:
        a.review(DESIGN, _context(tmp_path))
    assert e.value.failure_kind is FailureKind.LOGIC


def test_review_blocked_with_empty_body_does_not_persist(tmp_path):
    """判回退时没有终稿可言：不落盘、指针为空，下游按 Task 4 的兜底退回初稿。"""

    def runner(prompt: str, cwd: Path) -> str:
        return "REVIEW: BLOCKED\n- blocking: 上下文缺关键信息\n"

    a = ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home")
    art = a.review(DESIGN, _context(tmp_path))
    assert art.approved is False
    assert art.final_plan_file == ""
    assert art.comments == ("- blocking: 上下文缺关键信息",)


def test_review_propagates_stage_error(tmp_path):
    """铁律 3：runner 已翻译好的失败直接上抛，适配器不吞不重试。"""

    def runner(prompt: str, cwd: Path) -> str:
        raise StageError(FailureKind.TRANSIENT, "claude 超时")

    a = ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home")
    with pytest.raises(StageError) as e:
        a.review(DESIGN, _context(tmp_path))
    assert e.value.failure_kind is FailureKind.TRANSIENT
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest -q tests/adapters/test_review_claude.py`
Expected: FAIL —— `ModuleNotFoundError: No module named 'autodev.adapters.review_claude'`

- [ ] **Step 3: 写实现**

创建 `src/autodev/adapters/review_claude.py`：

```python
# src/autodev/adapters/review_claude.py
"""ReviewPort 真实实现：方案评审产出**最终方案**文档。

REVIEW 在本平台是"精炼"而非"判决"：读上下文与方案两份文档、只读核对真实代码，
产出一份可直接交给下游的最终方案。判回退（approved=False）收窄到"问题不在方案层面
而在上游"——需求自相矛盾、上下文缺关键信息、方案方向根本错需重新调研。

铁律合规：claude 交互经 ClaudeCodeRunner（已把子进程异常翻译成 StageError），本适配器
直接上抛，由引擎按 RetryPolicy 重试/回退/收敛 FAILED；文档落盘在 ~/.autodev 之下
（git worktree 之外），与 Context/Design 一致。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from autodev.domain.artifacts import ContextArtifact, DesignArtifact, ReviewArtifact
from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError

_APPROVED = "REVIEW: APPROVED"
_BLOCKED = "REVIEW: BLOCKED"
_SEPARATOR = "---"
_COMMENT_PREFIXES = ("- blocking:", "- suggestion:")


def parse_review_output(raw: str) -> tuple[bool, tuple[str, ...], str]:
    """把评审输出解析成 (approved, comments, 最终方案正文)。

    约定格式：首行哨兵 → 若干意见行 → `---` → 正文。ClaudeCodeRunner 只回 stdout 文本，
    没有 tool_use 那种强制 schema 可用，故用哨兵。

    首行不是哨兵时**降级**为通过、整份当正文：误判通过的代价是多走一次 REVIEW_GATE
    人审，误判回退的代价是烧掉一次 RetryPolicy 的 CAP 配额并重跑一次数分钟的 DESIGN。
    前者明显更轻，所以降级往通过那边倒。

    comments 的采集与 approved 无关，且**保留 `- blocking:` / `- suggestion:` 前缀原样**，
    让 UI 与人一眼看出哪条是拦路的、哪条只是建议。
    """
    text = raw.strip()
    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    if first not in (_APPROVED, _BLOCKED):
        return True, (), text

    approved = first == _APPROVED
    comments: list[str] = []
    i = 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == _SEPARATOR:
            i += 1
            break
        if stripped.startswith(_COMMENT_PREFIXES):
            comments.append(stripped)
            i += 1
            continue
        if not stripped:
            i += 1
            continue
        # 非空、非意见行、非分隔符 → 正文从这一行开始（缺 --- 不算格式错误）
        break
    body = "\n".join(lines[i:]).strip()
    return approved, tuple(comments), body


class ClaudeReviewAdapter:
    """在 worktree 内只读单遍跑 claude，产出最终方案文档。"""

    def __init__(
        self,
        runner: Callable[[str, Path], str],
        autodev_home: Path,
        id_gen: Callable[[], str] = lambda: uuid.uuid4().hex[:8],
    ) -> None:
        self._runner = runner
        self._home = autodev_home
        self._id_gen = id_gen

    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact:
        raw = self._runner(self._prompt(design, context), Path(context.workspace_location))
        approved, comments, body = parse_review_output(raw)
        if approved and not body:
            # 通过却没给方案：空方案绝不交下游。LOGIC → 回退重设计。
            raise StageError(FailureKind.LOGIC, "评审判定通过但未产出最终方案正文")
        if not body:
            # 判回退时没有终稿可言，不落空文件；下游兜底退回 DESIGN 初稿。
            return ReviewArtifact(approved, comments, final_plan_file="")
        path = self._persist(design, context, body)
        return ReviewArtifact(approved, comments, final_plan_file=str(path))

    def _prompt(self, design: DesignArtifact, context: ContextArtifact) -> str:
        return (
            "你在一个代码仓库工作目录里, 担任方案评审员。请依次:\n"
            f"1. 读已收集的上下文文档: {context.context_file}\n"
            f"2. 读待评审的实现方案初稿: {design.design_file}\n"
            "3. 只读调查真实代码核对方案: 提到的文件是否存在, 接口签名是否如其所述, "
            "是否与现有架构冲突, 是否违反项目约定(如仓库根目录 CLAUDE.md 所载)。\n"
            "4. 产出一份**最终方案**。能自己补全/纠正的问题直接改进到最终稿里, "
            "不要动辄打回。\n\n"
            "输出格式(严格遵守):\n"
            "首行必须是 `REVIEW: APPROVED` 或 `REVIEW: BLOCKED`。"
            "仅当问题不在方案层面而在上游(需求自相矛盾 / 上下文缺关键信息 / "
            "方案方向根本错需重新调研)才用 BLOCKED。\n"
            "首行之后可跟若干意见行, 每行以 `- blocking: ` 或 `- suggestion: ` 开头。\n"
            f"然后单独一行 `{_SEPARATOR}`, 其后是最终方案的 Markdown 正文, 含小节 "
            "`## 方案概述` / `## 改动清单` / `## 实现步骤` / `## 风险与取舍` / `## 评审说明`"
            "(最后一节说明相对初稿改了什么、为什么)。\n"
            "不要修改任何文件; 除上述内容外不要输出别的解释。"
        )

    def _persist(self, design: DesignArtifact, context: ContextArtifact, body: str) -> Path:
        work_item_id = Path(context.workspace_location).name
        d = self._home / "workitems" / work_item_id
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"final-plan-{self._id_gen()}.md"
        # 头部只记分支与初稿路径（供溯源"这份终稿评审的是哪一版初稿"）。
        # 端口签名拿不到 Requirement，故不记需求——需求已在初稿与上下文文档里。
        header = (
            f"# 最终方案\n\n- 分支: {context.workspace_label}\n"
            f"- 初稿: {design.design_file}\n\n---\n\n"
        )
        path.write_text(header + body, encoding="utf-8")
        return path
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest -q tests/adapters/test_review_claude.py -v`
Expected: 9 项全 PASS

- [ ] **Step 5: 演示评审端口也产出最终方案**

`src/autodev/adapters/demo.py`，把演示评审端口改成落一份演示终稿（照演示设计端口的写法）：

```python
class DemoReview:
    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact:
        path = Path(context.context_file).parent / "final-plan-demo.md"
        path.write_text(
            "# 最终方案（演示）\n\n"
            f"- 初稿: {design.design_file}\n\n"
            "## 方案概述\n\n（演示）沿用初稿思路\n\n"
            "## 评审说明\n\n（演示）核对无误，未作改动\n",
            encoding="utf-8",
        )
        return ReviewArtifact(
            approved=True,
            comments=("- suggestion: （演示）评审通过",),
            final_plan_file=str(path),
        )
```

- [ ] **Step 6: 写契约测试**

创建 `tests/adapters/test_review_contract.py`：

```python
"""ReviewPort 端口一致性契约：演示评审端口与真实适配器(注入假 runner)必须都返回
approved 为真、且携带非空最终方案指针的 ReviewArtifact。外加一个 @pytest.mark.live
真调 claude 冒烟(默认跳过)。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from autodev.adapters.demo import DemoReview
from autodev.adapters.review_claude import ClaudeReviewAdapter
from autodev.domain.artifacts import ContextArtifact, DesignArtifact


def _context(tmp_path: Path) -> ContextArtifact:
    ws = tmp_path / "ws" / "wiabc"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "app.py").write_text("x = 1\n")
    cfile = tmp_path / "home" / "workitems" / "wiabc" / "context-x.md"
    cfile.parent.mkdir(parents=True, exist_ok=True)
    cfile.write_text("## 相关文件\n- app.py\n")
    return ContextArtifact(str(ws), "autodev/wiabc", str(cfile))


def _design(tmp_path: Path) -> DesignArtifact:
    dfile = tmp_path / "home" / "workitems" / "wiabc" / "design-d1.md"
    dfile.parent.mkdir(parents=True, exist_ok=True)
    dfile.write_text("## 方案概述\n\n改 app.py\n")
    return DesignArtifact(design_file=str(dfile))


@pytest.fixture(params=["fake", "real"])
def adapter(request, tmp_path):
    if request.param == "fake":
        return DemoReview()

    def runner(prompt: str, cwd: Path) -> str:
        return "REVIEW: APPROVED\n---\n## 方案概述\n\n最终方案\n"

    return ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home")


def test_review_returns_artifact_with_final_plan_pointer(adapter, tmp_path):
    art = adapter.review(_design(tmp_path), _context(tmp_path))
    assert art.approved is True
    assert art.final_plan_file  # 非空指针
    assert Path(art.final_plan_file).read_text().strip()


@pytest.mark.live
def test_live_review_against_real_claude(tmp_path):
    if not os.environ.get("AUTODEV_LIVE"):
        pytest.skip("live 测试需 AUTODEV_LIVE=1 + 可用 claude/网关")
    from autodev.adapters.claude_runner import ClaudeCodeRunner

    r = ClaudeCodeRunner()
    a = ClaudeReviewAdapter(
        runner=lambda p, c: r.run(p, c, "plan"), autodev_home=tmp_path / "home"
    )
    art = a.review(_design(tmp_path), _context(tmp_path))
    assert art.final_plan_file
    assert Path(art.final_plan_file).read_text().strip()
```

- [ ] **Step 7: 跑测试确认通过**

Run: `pytest -q tests/adapters/ && mypy src`
Expected: 全部 PASS（live 那项 skip）

- [ ] **Step 8: 提交**

```bash
git add src/autodev/adapters/review_claude.py src/autodev/adapters/demo.py tests/adapters/test_review_claude.py tests/adapters/test_review_contract.py
git commit -m "feat(adapters): ReviewPort 真实适配器 — 评审产出最终方案文档"
```

---

### Task 4: 接线 —— 下游取权威方案 + 驱动边界扩到 REVIEW

**Files:**
- Modify: `src/autodev/application/handlers.py:100-105`（`handle_impl`）
- Modify: `src/autodev/webapp/config.py:84-106`
- Modify: `src/autodev/webapp/drive.py:26`
- Test: `tests/application/test_handlers_back.py`、`tests/webapp/test_demo_app.py`

**Interfaces:**
- Consumes: Task 1 的 `final_plan_file`；Task 3 产出的评审适配器（类名见 Task 3 的 Produces 代码块）
- Produces: `IMPLEMENTED_STAGES` 含 `S.REVIEW`；生产组合根的 `reviewer` 为真实适配器

- [ ] **Step 1: 写失败测试**

追加到 `tests/application/test_handlers_back.py`：

```python
def test_impl_uses_final_plan_from_review():
    """IMPL 的权威输入是评审终稿，不是 DESIGN 初稿。"""
    from autodev.domain.artifacts import ReviewArtifact

    seen: list[str] = []

    class RecordingExecution:
        def implement(self, design, handle):
            seen.append(design.design_file)
            return ImplArtifact("--- diff ---", True, "recorded")

    ctx, dial = _ctx()
    wi = _wi(dial)
    wi.add_artifact("review", ReviewArtifact(True, (), final_plan_file="/x/final-plan-r1.md"))
    ctx.executor = RecordingExecution()
    handle_impl(wi, ctx, NOW)
    assert seen == ["/x/final-plan-r1.md"]


def test_impl_falls_back_to_design_when_no_final_plan():
    """无评审终稿（历史数据 / 判回退）时退回 DESIGN 初稿，不能崩。"""
    seen: list[str] = []

    class RecordingExecution:
        def implement(self, design, handle):
            seen.append(design.design_file)
            return ImplArtifact("--- diff ---", True, "recorded")

    ctx, dial = _ctx()
    wi = _wi(dial)
    ctx.executor = RecordingExecution()
    handle_impl(wi, ctx, NOW)
    assert seen == ["/fake/design/x.md"]
```

顶部导入补 `ImplArtifact`：`from autodev.domain.artifacts import (AcceptanceArtifact, ContextArtifact, DesignArtifact, ImplArtifact)`。`ctx.executor = ...` 直接赋值即可（`StageContext` 非 frozen）。

再改 `tests/webapp/test_demo_app.py` 的两个守卫（把评审端口从"仍为桩"改成"已真实"）：

```python
    # 分诊/方案设计/方案评审已是真实适配器；Execution/Verification/Delivery 在沙箱
    # 就绪前仍须为桩。
    assert isinstance(ctx.triage, LlmTriageAdapter)
    assert isinstance(ctx.executor, UnavailableStage)
    assert isinstance(ctx.verifier, UnavailableStage)
    assert isinstance(ctx.delivery, UnavailableStage)
    assert isinstance(ctx.designer, ClaudeDesignAdapter)
    assert isinstance(ctx.reviewer, ClaudeReviewAdapter)
```
（顶部导入 `from autodev.adapters.review_claude import ClaudeReviewAdapter`；把原先 `assert isinstance(ctx.reviewer, UnavailableStage)` 那行删掉，并把该测试的函数级 docstring 里"Review"从桩清单中去掉。）

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest -q tests/application/test_handlers_back.py -k final_plan tests/webapp/test_demo_app.py`
Expected: FAIL —— `seen == ['/fake/design/x.md']`（还没读评审终稿）；守卫测试报 `ctx.reviewer` 是桩、且 `test_implemented_stages_matches_real_ports` 报 REVIEW 不一致

- [ ] **Step 3: `handle_impl` 取权威方案**

`src/autodev/application/handlers.py`：

```python
def _plan_for_impl(work_item: WorkItem) -> DesignArtifact:
    """IMPL 的权威方案：评审产出的最终方案优先，缺失则退回 DESIGN 初稿。

    评审判"无法自救"时不产终稿（指针为空），但那种情况会回退重设计、走不到 IMPL；
    这里的兜底是给历史数据与不产终稿的假件留的。
    """
    review = work_item.artifacts.get("review")
    if isinstance(review, ReviewArtifact) and review.final_plan_file:
        return DesignArtifact(design_file=review.final_plan_file)
    return cast(DesignArtifact, work_item.artifacts["design"])


def handle_impl(work_item: WorkItem, ctx: StageContext, now: datetime) -> StageOutcome:
    design = _plan_for_impl(work_item)
    context = work_item.artifacts["context"]
    handle = _handle_from_context(context)
    impl = ctx.executor.implement(design, handle)
    return StageOutcome.ok("impl", impl)
```

- [ ] **Step 4: 组合根接线 + 扩驱动边界**

`src/autodev/webapp/config.py`：顶部加 `from autodev.adapters.review_claude import ClaudeReviewAdapter`，然后

```python
    designer = ClaudeDesignAdapter(runner=lambda p, c: runner.run(p, c), autodev_home=home)
    reviewer = ClaudeReviewAdapter(runner=lambda p, c: runner.run(p, c), autodev_home=home)
    stub = UnavailableStage()
```

并把 `StageContext(...)` 的第四个位置参数由 `stub` 改为 `reviewer`：

```python
    ctx = StageContext(
        workspace,
        gatherer,
        designer,
        reviewer,
        stub,
        stub,
        stub,
        triage,
        GatePolicy(),
    )
```

同时把该文件的模块 docstring 里"(F1 workspace/F3 context/F4 design)+ 桩(REVIEW 及之后)"改为"+ 评审"、桩范围改为 IMPL 及之后。

`src/autodev/webapp/drive.py`：

```python
IMPLEMENTED_STAGES: frozenset[S] = frozenset(
    {S.INTAKE, S.TRIAGE, S.CONTEXT, S.DESIGN, S.REVIEW}
)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest -q && mypy src && ruff check . && ruff format --check .`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src/autodev/application/handlers.py src/autodev/webapp/config.py src/autodev/webapp/drive.py tests/application/test_handlers_back.py tests/webapp/test_demo_app.py
git commit -m "feat(webapp): 接入真实评审端口, 驱动边界扩到 REVIEW"
```

---

### Task 5: 投影与前端「最终方案」面板

**Files:**
- Modify: `src/autodev/webapp/views.py:103-143`
- Create: `frontend/src/components/ReviewComments.tsx`、`frontend/src/components/ReviewComments.module.css`、`frontend/src/components/ReviewComments.test.tsx`
- Modify: `frontend/src/api/types.ts:55-65`、`frontend/src/pages/WorkItemDetailPage.tsx`
- Test: `tests/webapp/test_views.py`

**Interfaces:**
- Consumes: Task 1 的 `final_plan_file`
- Produces: `view_detail` 的 `review` 键 —— `{markdown: str, final_plan_file: str, approved: bool, comments: list[str]} | None`

- [ ] **Step 1: 写失败测试（后端投影）**

追加到 `tests/webapp/test_views.py`：

```python
def test_view_detail_projects_review_final_plan():
    from autodev.domain.artifacts import ReviewArtifact

    wi = _work_item(S.REVIEW)
    wi.add_artifact(
        "review",
        ReviewArtifact(
            True, ("- suggestion: 补个测试",), final_plan_file="/x/final-plan-r1.md"
        ),
    )
    detail = view_detail(wi, lambda p: "## 方案概述\n\n最终方案")
    review = detail["review"]
    assert review["final_plan_file"] == "/x/final-plan-r1.md"
    assert review["approved"] is True
    assert review["comments"] == ["- suggestion: 补个测试"]
    assert "最终方案" in review["markdown"]


def test_view_detail_review_markdown_empty_when_file_unreadable():
    from autodev.domain.artifacts import ReviewArtifact

    def boom(path: str) -> str:
        raise OSError("EPERM")

    wi = _work_item(S.REVIEW)
    wi.add_artifact("review", ReviewArtifact(True, (), final_plan_file="/x/f.md"))
    assert view_detail(wi, boom)["review"]["markdown"] == ""


def test_view_detail_review_is_none_without_artifact():
    assert view_detail(_work_item(S.CONTEXT), lambda p: "")["review"] is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest -q tests/webapp/test_views.py -k review`
Expected: FAIL —— `KeyError: 'review'`

- [ ] **Step 3: 加投影**

`src/autodev/webapp/views.py`：顶部导入加 `ReviewArtifact`，在 `design` 块之后插入

```python
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
```

并在装配处加一行（紧跟 `detail["design"] = design`）：

```python
    detail["review"] = review
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest -q tests/webapp/ && mypy src`
Expected: 全部 PASS

- [ ] **Step 5: 写前端失败测试**

创建 `frontend/src/components/ReviewComments.test.tsx`：

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ReviewComments } from './ReviewComments'

describe('ReviewComments', () => {
  it('renders nothing when there are no comments', () => {
    const { container } = render(<ReviewComments comments={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders each comment as a list item', () => {
    render(<ReviewComments comments={['- blocking: 方向不对', '- suggestion: 补测试']} />)
    expect(screen.getByText(/方向不对/)).toBeInTheDocument()
    expect(screen.getByText(/补测试/)).toBeInTheDocument()
  })

  it('marks blocking and suggestion items differently so 拦路的一眼可辨', () => {
    const { container } = render(
      <ReviewComments comments={['- blocking: 方向不对', '- suggestion: 补测试']} />,
    )
    const kinds = [...container.querySelectorAll('li')].map((li) => li.dataset.kind)
    expect(kinds).toEqual(['blocking', 'suggestion'])
  })
})
```

- [ ] **Step 6: 跑测试确认失败**

Run: `cd frontend && npm run test -- ReviewComments`
Expected: FAIL —— 找不到模块 `./ReviewComments`

- [ ] **Step 7: 写前端实现**

创建 `frontend/src/components/ReviewComments.tsx`：

```tsx
import styles from './ReviewComments.module.css'

/** 评审意见列表。前缀（`- blocking:` / `- suggestion:`）由后端原样保留，此处据其分类着色。 */
export function ReviewComments({ comments }: { comments: string[] }) {
  if (comments.length === 0) return null
  return (
    <ul className={styles.list} data-testid="review-comments">
      {comments.map((c) => (
        <li key={c} data-kind={c.startsWith('- blocking:') ? 'blocking' : 'suggestion'}>
          {c.replace(/^- (blocking|suggestion):\s*/, '')}
        </li>
      ))}
    </ul>
  )
}
```

创建 `frontend/src/components/ReviewComments.module.css`：

```css
.list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.list li {
  font-size: 0.88rem;
  line-height: 1.5;
  color: var(--ink-soft);
  padding-left: var(--space-3);
  border-left: 2px solid var(--line);
}

.list li[data-kind='blocking'] {
  color: var(--ink);
  font-weight: 500;
  border-left-color: currentColor;
}
```

`frontend/src/api/types.ts` 的 `WorkItemDetail` 里，`design` 之后加：

```ts
  review: {
    markdown: string
    final_plan_file: string
    approved: boolean
    comments: string[]
  } | null
```

`frontend/src/pages/WorkItemDetailPage.tsx`：导入 `import { ReviewComments } from '../components/ReviewComments'`，在「方案」面板之后插入

```tsx
      {detail.review && (
        <>
          {detail.review.final_plan_file && (
            <BriefDocument
              title="最终方案"
              markdown={detail.review.markdown}
              path={detail.review.final_plan_file}
            />
          )}
          <ReviewComments comments={detail.review.comments} />
        </>
      )}
```

- [ ] **Step 8: 跑前端全套**

Run: `cd frontend && npm run test && npm run typecheck && npm run lint && npm run build`
Expected: 全部 PASS

- [ ] **Step 9: 提交**

```bash
git add src/autodev/webapp/views.py tests/webapp/test_views.py frontend/src/components/ReviewComments.tsx frontend/src/components/ReviewComments.module.css frontend/src/components/ReviewComments.test.tsx frontend/src/api/types.ts frontend/src/pages/WorkItemDetailPage.tsx
git commit -m "feat(frontend): 「最终方案」面板 + 评审意见列表"
```

---

### Task 6: 文档对齐与全量验收

**Files:**
- Modify: `CHANGELOG.md`（`[Unreleased]` / `### Added`）
- Modify: `ROADMAP.md`（适配器表、切片 2 状态、驱动边界描述）
- Test: `pytest -q tests/docs`

**Interfaces:**
- Consumes: Task 1-5 全部落地后的真实符号名（此时评审适配器类已存在于 `src/autodev`，可在文档正文行内反引号里引用而不触发伪造符号检查）
- Produces: 无

- [ ] **Step 1: 写 CHANGELOG 条目**

在 `CHANGELOG.md` 的 `## [Unreleased]` → `### Added` 段**首位**插入（与既有条目同风格，一条一段）：

```markdown
- **ReviewPort 真实落地(切片 2 第 5 个真实适配器)**：`src/autodev/adapters/review_claude.py:ClaudeReviewAdapter` —— 复用 `ClaudeCodeRunner`,在 worktree 内**只读单遍**跑 `claude`,读上下文与方案两份文档并核对真实代码,产出一份**最终方案**文档(`~/.autodev/workitems/<id>/final-plan-<rand>.md`),作为下游 IMPL 的权威输入。REVIEW 由此从"判决"变为"精炼"：`ReviewArtifact` 增 `final_plan_file` 指针(默认空串,向后兼容),`handle_impl` 改取评审终稿、缺失才退回 DESIGN 初稿。判决经**首行哨兵**(`REVIEW: APPROVED` / `REVIEW: BLOCKED`)取出——`ClaudeCodeRunner` 只回 stdout,没有 `LlmTriageAdapter` 那种强制 schema 可用;首行不是哨兵即**降级为通过**并把整份输出当正文(误判通过只多走一次人审,误判回退要烧一次 `RetryPolicy` 的重试配额),通过但正文为空则报 LOGIC 失败(空方案绝不交下游)。生产组合根接入真实 `reviewer`,`IMPLEMENTED_STAGES` 扩到 REVIEW(仍止于 IMPL,该端口尚为桩);`view_detail` 增 `review` 投影,前端详情页新增「最终方案」面板与评审意见列表(blocking/suggestion 分色)。契约测试(演示评审端口 vs 真实适配器,注入假 runner)+ 解析单测 + `@pytest.mark.live` 冒烟覆盖;防漂移与安全守卫更新为 reviewer 真实、executor/verifier/delivery 仍为桩。规划见 `docs/superpowers/specs/2026-08-03-review-port-real-adapter-design.md`。
- **回退重设计不再是死路**：`DesignPort.propose` 增可选入参传入上一轮 `ReviewArtifact`,`handle_design` 在回退重设计时透传,真实设计适配器把被否理由写进提示词。此前 `RetryPolicy` 把 REVIEW 的 LOGIC 失败回退到 DESIGN,但设计端口收不到任何评审反馈——同样输入产同样方案、招来同样打回,必然烧完重试上限收敛 FAILED。该路径在演示评审端口永远通过的年代不可达,本次评审能真判回退,故一并修好。
```

- [ ] **Step 2: 改 ROADMAP**

`ROADMAP.md` 三处：

1. 切片 2 适配器表里评审端口那一行，状态与落点改成：

```markdown
| **ReviewPort** | 对 DesignProposal 做方案评审并产出最终方案 | ✅ 真实已实现（`ClaudeReviewAdapter`）**且已接入组合根** | 已产出最终方案 Markdown 文档，持久化到 `~/.autodev` |
```

2. 「核心工作」列表里 `◐ Review / Execution 两个真实适配器待实现` 改为 `✅ Review 真实适配器已实现；◐ Execution 待实现`；`⬜ REVIEW 及之后阶段仍待接入` 改为 `⬜ IMPL 及之后阶段仍待接入`。
3. 全文搜 `止于 REVIEW`，改为 `止于 IMPL`；搜 `REVIEW 起为抛错桩` 改为 `IMPL 起为抛错桩`。第 16 行的切片 2 状态括注 `（Workspace/Context/Triage/Design 已落地）` 补上 `/Review`。

同样检查 `README.md` 是否有驱动边界描述（`grep -n "REVIEW\|止于" README.md`），有则同步。

- [ ] **Step 3: 跑文档一致性检查**

Run: `pytest -q tests/docs`
Expected: 11 项 PASS。若报伪造符号，检查是否在正文行内反引号里写了 `src/**` 中不存在的名字（`ReviewComments` 是前端组件、不在 `src/autodev` 里，若在正文引用它需加进 `docs/.doc-allowlist.txt` 的前端组件段）。

- [ ] **Step 4: 全量验收**

Run: `pytest -q && ruff check . && ruff format --check . && mypy src && cd frontend && npm run typecheck && npm run lint && npm run test && npm run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add CHANGELOG.md ROADMAP.md README.md
git commit -m "docs: CHANGELOG/ROADMAP 对齐 ReviewPort 真实适配器"
```

---

## 手工验收（实现完成后）

需要真实 `claude` CLI 与网关可用。

1. 起控制台服务，新建一个**自动挡**低风险工作项。
2. 确认连续跑过 INTAKE→TRIAGE→CONTEXT→DESIGN→REVIEW，详情页「方案」与「最终方案」两个面板都能展开，内容不同（终稿含「评审说明」小节）。
3. 确认「开发」行显示「待建设」、「推进」按钮为灰且给出该阶段尚未建设的提示。
4. 新建一个**高风险**工作项（需求里写危险关键词），确认在 REVIEW_GATE 挂起 `WAIT_HUMAN`，点「批准继续」后落到「开发」的待建设态。
5. 新建一个**手动挡**工作项，确认建完自动跑到上下文并挂 CONTEXT_GATE；点「继续后续流程」只跑一个阶段（方案）就停住；再点一次才跑评审。
