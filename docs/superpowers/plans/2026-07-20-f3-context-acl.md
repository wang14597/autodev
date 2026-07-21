# F3 上下文 ACL Implementation Plan

> **For agentic workers:** subagent-driven-development 逐任务 + 评审。全程 TDD。Claude 调用一律经注入的 runner，单测用假 runner（零外部依赖）；live 冒烟标记跳过。

**Goal:** 实现 CONTEXT 阶段的真实 `ContextPort`：共享 ClaudeCodeRunner（headless Claude 底座）+ ClaudeContextAdapter（两遍质检：收集→复核改进，Markdown 结果落盘 `~/.autodev`，`ContextArtifact` 只存指针）。含 `ContextArtifact` 领域改动及涟漪。

**Architecture:** 设计见 `docs/superpowers/specs/2026-07-20-f3-context-acl-design.md`。Claude 只读（plan 模式）调查，adapter（Python）把结果写盘、DB 存路径。

**Tech Stack:** Python(subprocess/json/re/pathlib/uuid)、pytest、`claude` CLI（经内网网关，测试不实调）。

## Global Constraints
- Claude 调用经注入 runner；单测零外部依赖；`claude` 只读 plan 模式。
- 结果文件写 worktree 之外的 `~/.autodev`（可配置，测试用 tmp）。
- Claude 调用失败翻译成 `StageError`+`FailureKind`（超时/网关网络→TRANSIENT，鉴权→FATAL，其余→LOGIC）；runner 内置对 TRANSIENT 的有界重试。
- 收集遍失败（重试耗尽）→ StageError 上浮；复核遍失败（重试耗尽）→ 降级回第一遍。
- 不接入真实运行（F8）；不改领域/应用层运行时逻辑，除本计划明列的 `ContextArtifact` 改动。
- 现有全套测试保持绿；`ruff check . && ruff format --check . && mypy src` 通过。
- Conventional Commits；提交人 `AutoDev <autodev@local>`，body 末附 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。

## File Structure
```
src/autodev/domain/artifacts.py          # ContextArtifact 改为指针(改动)
src/autodev/adapters/sqlite_repository.py # ContextArtifact 序列化(改动)
src/autodev/adapters/claude_runner.py     # ClaudeCodeRunner(新)
src/autodev/adapters/context_claude.py    # ClaudeContextAdapter(新)
docs/architecture/diagrams.md             # ContextArtifact 类图改字段(改动, 为保持准确; 注意 CI 不会自动拦此处漂移)
CHANGELOG.md                              # F3 变更条目(改动, doc-impact 门禁会卡)
tests/fakes.py                            # FakeContext 改新字段(改动)
tests/adapters/test_claude_runner.py      # runner 单测
tests/adapters/test_context_claude.py     # adapter 单测(假 runner)
tests/adapters/test_context_contract.py   # 端口一致性 + live 冒烟
+ 更新 slice-1 中构造 ContextArtifact 的测试
```

---

### Task 1: 领域改动 — ContextArtifact 改为指针

**Files:** Modify `src/autodev/domain/artifacts.py`, `src/autodev/adapters/sqlite_repository.py`, `tests/fakes.py`, `docs/architecture/diagrams.md`, 以及所有构造/断言旧 ContextArtifact 的测试。

**Interfaces:** `ContextArtifact` 新字段：`workspace_location: str`、`workspace_label: str`、`context_file: str`（删除 `relevant_files`、`summary`）。

- [ ] **Step 1: 改 dataclass**

`src/autodev/domain/artifacts.py` 的 ContextArtifact：
```python
@dataclass(frozen=True)
class ContextArtifact:
    workspace_location: str
    workspace_label: str
    context_file: str
```

- [ ] **Step 2: 改 SQLite 序列化**

`sqlite_repository.py` 中 ContextArtifact 的两处：
```python
# _artifact_to_dict
if isinstance(a, ContextArtifact):
    return {"__t": t, "workspace_location": a.workspace_location,
            "workspace_label": a.workspace_label, "context_file": a.context_file}
# _artifact_from_dict
if t == "ContextArtifact":
    return ContextArtifact(d["workspace_location"], d["workspace_label"], d["context_file"])
```

- [ ] **Step 3: 改 FakeContext**

`tests/fakes.py` 的 FakeContext.gather：
```python
class FakeContext:
    def gather(self, requirement, handle):
        return ContextArtifact(handle.location, handle.label,
                               f"{handle.location}/../.autodev-fake/context.md")
```

- [ ] **Step 4: 修所有旧构造点**

Run: `grep -rn 'ContextArtifact(' src tests` — 逐个把 4 参数旧构造改为 `ContextArtifact(location, label, context_file)`；断言 `.summary`/`.relevant_files` 的改为断言 `.context_file`（或删除该断言，改断言 workspace_label 等仍存在字段）。真实构造点：`tests/application/test_handlers_front.py`、`test_handlers_back.py`、`tests/application/test_engine.py`（`sqlite_repository.py`/`tests/fakes.py` 已在 Step 2/3 处理）。

- [ ] **Step 5: 更新架构文档（保持类图准确）**

`docs/architecture/diagrams.md` 的 `class ContextArtifact { ... }` Mermaid 类图删掉 `+tuple relevant_files`、`+str summary`，改为 `+str context_file`。顺带核查 `docs/architecture/2026-07-15-strategic-direction-and-domain-model.md` 若有 ContextArtifact 字段描述一并更新。
> 注意：这处**不是 CI 阻塞项**——类图在 mermaid 围栏代码块内，第 1 层符号检查会 strip 掉、抓不到；doc-ownership 里 `artifacts.py` 也只映射 CHANGELOG 不映射 diagrams.md。即漂移会**静默**，故必须手动改准。（可选后续改进：给 doc-ownership 加 `artifacts.py → diagrams.md` 规则，至少强制"改 artifact 就得动一下类图"。）

- [ ] **Step 6: 跑全套 + 门禁**

Run: `. venv/bin/activate && pytest -q && ruff check . && ruff format --check . && mypy src`
Expected: 全绿（这是重构，行为不变，测试数可能不变）。

- [ ] **Step 7: Commit**
```bash
git add -A src/autodev/domain/artifacts.py src/autodev/adapters/sqlite_repository.py docs/architecture/diagrams.md tests/
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "refactor(domain): ContextArtifact 改为指针(context_file), 大内容落盘"
```

---

### Task 2: ClaudeCodeRunner（共享底座）

**Files:** Create `src/autodev/adapters/claude_runner.py`, `tests/adapters/test_claude_runner.py`

**Interfaces:** `ClaudeCodeRunner(run=subprocess.run, timeout=600, max_retries=3, sleep=time.sleep)`；`run(prompt: str, cwd: Path, permission_mode: str = "plan") -> str`（跑 `claude -p <prompt> --permission-mode <mode> --bare`；失败翻译；对 TRANSIENT 有界重试）。

- [ ] **Step 1: 写失败测试**
```python
# tests/adapters/test_claude_runner.py
import subprocess
from pathlib import Path
import pytest
from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError
from autodev.adapters.claude_runner import ClaudeCodeRunner, _classify


def test_classify():
    assert _classify("Error: overloaded_error 503") is FailureKind.TRANSIENT
    assert _classify("invalid api key / 401 unauthorized") is FailureKind.FATAL
    assert _classify("some other error") is FailureKind.LOGIC


def test_run_success_returns_stdout(tmp_path):
    def fake(*a, **k):
        return subprocess.CompletedProcess(a, 0, stdout="RESULT\n", stderr="")
    assert ClaudeCodeRunner(run=fake).run("p", tmp_path) == "RESULT"


def test_run_timeout_transient(tmp_path):
    def fake(*a, **k):
        raise subprocess.TimeoutExpired("claude", 1)
    with pytest.raises(StageError) as ei:
        ClaudeCodeRunner(run=fake, max_retries=0).run("p", tmp_path)
    assert ei.value.failure_kind is FailureKind.TRANSIENT


def test_run_missing_binary_fatal(tmp_path):
    def fake(*a, **k):
        raise FileNotFoundError("claude")
    with pytest.raises(StageError) as ei:
        ClaudeCodeRunner(run=fake).run("p", tmp_path)
    assert ei.value.failure_kind is FailureKind.FATAL


def test_run_retries_transient_then_succeeds(tmp_path):
    calls = {"n": 0}
    def fake(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            return subprocess.CompletedProcess(a, 1, stdout="", stderr="connection timed out")
        return subprocess.CompletedProcess(a, 0, stdout="OK", stderr="")
    out = ClaudeCodeRunner(run=fake, max_retries=3, sleep=lambda s: None).run("p", tmp_path)
    assert out == "OK" and calls["n"] == 3


def test_run_invokes_expected_args(tmp_path):
    seen = {}
    def fake(cmd, **k):
        seen["cmd"] = cmd; seen["cwd"] = k.get("cwd"); seen["timeout"] = k.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, stdout="x", stderr="")
    ClaudeCodeRunner(run=fake, timeout=600).run("PROMPT", tmp_path, permission_mode="plan")
    assert seen["cmd"] == ["claude", "-p", "PROMPT", "--permission-mode", "plan", "--bare"]
    assert seen["cwd"] == str(tmp_path) and seen["timeout"] == 600
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**
```python
# src/autodev/adapters/claude_runner.py
from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError

_NETWORK_HINTS = (
    "connection", "timed out", "could not resolve", "network", "gateway",
    "502", "503", "econnrefused", "rate limit", "overloaded",
)
_AUTH_HINTS = ("unauthorized", "authentication", "invalid api key", "forbidden", "401", "403")


def _classify(stderr: str) -> FailureKind:
    s = stderr.lower()
    if any(h in s for h in _NETWORK_HINTS):
        return FailureKind.TRANSIENT
    if any(h in s for h in _AUTH_HINTS):
        return FailureKind.FATAL
    return FailureKind.LOGIC


class ClaudeCodeRunner:
    def __init__(
        self,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout: int = 600,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._run = run
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep = sleep

    def run(self, prompt: str, cwd: Path, permission_mode: str = "plan") -> str:
        attempt = 0
        while True:
            try:
                return self._invoke(prompt, cwd, permission_mode)
            except StageError as e:
                if e.failure_kind is FailureKind.TRANSIENT and attempt < self._max_retries:
                    attempt += 1
                    self._sleep(min(2**attempt, 30))
                    continue
                raise

    def _invoke(self, prompt: str, cwd: Path, permission_mode: str) -> str:
        try:
            proc = self._run(
                ["claude", "-p", prompt, "--permission-mode", permission_mode, "--bare"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise StageError(FailureKind.TRANSIENT, "claude 超时") from e
        except FileNotFoundError as e:
            raise StageError(FailureKind.FATAL, "claude 不可用") from e
        if proc.returncode != 0:
            raise StageError(_classify(proc.stderr), f"claude 失败: {proc.stderr.strip()[:200]}")
        return proc.stdout.strip()
```

- [ ] **Step 4: 跑测试确认通过** — 6 passed；全套绿；ruff/mypy 过。

- [ ] **Step 5: Commit**
```bash
git add src/autodev/adapters/claude_runner.py tests/adapters/test_claude_runner.py
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "feat(adapters): ClaudeCodeRunner 共享底座(失败翻译+有界重试)"
```

---

### Task 3: ClaudeContextAdapter — 收集遍 + 落盘

**Files:** Create `src/autodev/adapters/context_claude.py`, `tests/adapters/test_context_claude.py`

**Interfaces:** `ClaudeContextAdapter(runner: Callable[[str, Path], str], autodev_home: Path, id_gen: Callable[[], str] = lambda: uuid.uuid4().hex[:8])`；`gather(requirement, handle) -> ContextArtifact`。本任务 `gather` = 收集遍 + `_review` 占位(直接返回输入) + 落盘；复核遍在 T4 实现。work_item_id 取 `Path(handle.location).name`（F1 布局：worktree 位于 workspaces_dir/<work_item_id>）。

- [ ] **Step 1: 写失败测试**
```python
# tests/adapters/test_context_claude.py
import json
from pathlib import Path
import pytest
from autodev.domain.errors import StageError
from autodev.domain.enums import FailureKind
from autodev.domain.value_objects import Requirement, WorkspaceHandle
from autodev.adapters.context_claude import ClaudeContextAdapter

REQ = Requirement("fix login", "repo-a", (), "raw")


def _handle(tmp_path):
    ws = tmp_path / "ws" / "wi12345678"
    ws.mkdir(parents=True)
    return WorkspaceHandle(location=str(ws), label="autodev/wi12345678")


def test_gather_parses_json_and_writes_markdown(tmp_path):
    def runner(prompt, cwd):
        return json.dumps({"relevant_files": ["src/login.py"], "summary": "登录逻辑在 login.py"})
    home = tmp_path / "home"
    a = ClaudeContextAdapter(runner=runner, autodev_home=home, id_gen=lambda: "aaa")
    art = a.gather(REQ, _handle(tmp_path))
    p = Path(art.context_file)
    assert p.exists() and p.suffix == ".md"
    assert "登录逻辑在 login.py" in p.read_text() and "src/login.py" in p.read_text()
    assert str(home) in art.context_file          # 写在 autodev_home 下
    assert "/ws/wi12345678" not in art.context_file  # 不在 worktree 内
    assert art.workspace_label == "autodev/wi12345678"


def test_gather_degrades_on_non_json(tmp_path):
    def runner(prompt, cwd):
        return "这是一段自由文本, 不是 JSON"
    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: "b")
    art = a.gather(REQ, _handle(tmp_path))
    txt = Path(art.context_file).read_text()
    assert "这是一段自由文本" in txt  # summary 降级为原文


def test_gather_propagates_collect_failure(tmp_path):
    def runner(prompt, cwd):
        raise StageError(FailureKind.TRANSIENT, "claude 挂了")
    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h")
    with pytest.raises(StageError):
        a.gather(REQ, _handle(tmp_path))


def test_gather_multiple_writes_distinct_files(tmp_path):
    def runner(prompt, cwd):
        return json.dumps({"relevant_files": [], "summary": "s"})
    ids = iter(["x1", "x2"])
    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: next(ids))
    h = _handle(tmp_path)
    a1 = a.gather(REQ, h)
    a2 = a.gather(REQ, h)
    assert a1.context_file != a2.context_file  # 不覆盖
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**
```python
# src/autodev/adapters/context_claude.py
from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from pathlib import Path

from autodev.domain.artifacts import ContextArtifact
from autodev.domain.value_objects import Requirement, WorkspaceHandle

_JSON = re.compile(r"\{.*\}", re.S)


class ClaudeContextAdapter:
    def __init__(
        self,
        runner: Callable[[str, Path], str],
        autodev_home: Path,
        id_gen: Callable[[], str] = lambda: uuid.uuid4().hex[:8],
    ) -> None:
        self._runner = runner
        self._home = autodev_home
        self._id_gen = id_gen

    def gather(self, requirement: Requirement, handle: WorkspaceHandle) -> ContextArtifact:
        files, summary = self._collect(requirement, handle)
        files, summary = self._review(files, summary, requirement, handle)
        path = self._persist(handle, files, summary, requirement)
        return ContextArtifact(
            workspace_location=handle.location,
            workspace_label=handle.label,
            context_file=str(path),
        )

    def _collect(self, requirement: Requirement, handle: WorkspaceHandle) -> tuple[tuple[str, ...], str]:
        prompt = (
            "你在一个代码仓库工作目录里。只读调查与下述需求相关的代码, "
            "输出 JSON: {\"relevant_files\":[相对路径...], \"summary\":\"对相关代码的理解摘要\"}。"
            "不要修改任何文件。\n\n需求: " + requirement.goal
        )
        return self._parse(self._runner(prompt, Path(handle.location)))

    def _review(
        self, files: tuple[str, ...], summary: str, requirement: Requirement, handle: WorkspaceHandle
    ) -> tuple[tuple[str, ...], str]:
        return files, summary  # T4 实现真实复核

    def _parse(self, out: str) -> tuple[tuple[str, ...], str]:
        m = _JSON.search(out)
        if m:
            try:
                data = json.loads(m.group(0))
                files = tuple(str(f) for f in data.get("relevant_files", []))
                return files, str(data.get("summary", ""))
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
        return (), out  # 降级

    def _persist(
        self, handle: WorkspaceHandle, files: tuple[str, ...], summary: str, requirement: Requirement
    ) -> Path:
        work_item_id = Path(handle.location).name
        d = self._home / "workitems" / work_item_id
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"context-{self._id_gen()}.md"
        path.write_text(self._render(files, summary, requirement, handle), encoding="utf-8")
        return path

    def _render(
        self, files: tuple[str, ...], summary: str, requirement: Requirement, handle: WorkspaceHandle
    ) -> str:
        lines = [
            "# 上下文收集结果",
            "",
            f"- 需求: {requirement.goal}",
            f"- 分支: {handle.label}",
            "",
            "## 相关文件",
            "",
        ]
        lines += [f"- `{f}`" for f in files] or ["(无)"]
        lines += ["", "## 摘要", "", summary, ""]
        return "\n".join(lines)
```

- [ ] **Step 4: 跑测试确认通过** — 4 passed；全套绿；ruff/mypy 过。

- [ ] **Step 5: Commit**
```bash
git add src/autodev/adapters/context_claude.py tests/adapters/test_context_claude.py
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "feat(adapters): ClaudeContextAdapter 收集遍 + Markdown 落盘 + 指针 artifact"
```

---

### Task 4: 复核遍 `_review`

**Files:** Modify `src/autodev/adapters/context_claude.py`, `tests/adapters/test_context_claude.py`

**Interfaces:** 实现 `_review`：第二个 runner 调用，拿第一遍结果 + worktree 核对并输出改进 `{relevant_files, summary}`；runner 抛 `StageError`（重试耗尽）→ 降级回第一遍。保持独立可组合（未来套 loop）。

- [ ] **Step 1: 写失败测试**
```python
# 追加到 tests/adapters/test_context_claude.py
def test_review_improves_result(tmp_path):
    outs = iter([
        json.dumps({"relevant_files": ["a.py"], "summary": "初版"}),
        json.dumps({"relevant_files": ["a.py", "b.py"], "summary": "改进版: 更完整"}),
    ])
    def runner(prompt, cwd):
        return next(outs)
    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: "r1")
    art = a.gather(REQ, _handle(tmp_path))
    txt = Path(art.context_file).read_text()
    assert "改进版" in txt and "b.py" in txt   # 反映复核改进


def test_review_failure_degrades_to_first_pass(tmp_path):
    calls = {"n": 0}
    def runner(prompt, cwd):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps({"relevant_files": ["a.py"], "summary": "第一遍"})
        raise StageError(FailureKind.TRANSIENT, "复核挂了")  # runner 已重试耗尽后抛
    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: "r2")
    art = a.gather(REQ, _handle(tmp_path))
    txt = Path(art.context_file).read_text()
    assert "第一遍" in txt   # 降级回第一遍, 不抛
```

- [ ] **Step 2: 跑测试确认失败**（当前 _review 是占位, 不会改进/不会二次调用）

- [ ] **Step 3: 实现**
```python
    def _review(
        self, files: tuple[str, ...], summary: str, requirement: Requirement, handle: WorkspaceHandle
    ) -> tuple[tuple[str, ...], str]:
        prompt = (
            "下面是对本仓库的第一遍上下文收集结果。请对照真实代码核对其相关性/完整性/摘要准确性, "
            "补漏、去无关、修正摘要, 输出改进后的 JSON: "
            "{\"relevant_files\":[...], \"summary\":\"...\"}。只读, 不要改文件。\n\n"
            f"需求: {requirement.goal}\n第一遍 relevant_files: {list(files)}\n第一遍 summary:\n{summary}"
        )
        try:
            return self._parse(self._runner(prompt, Path(handle.location)))
        except StageError:
            return files, summary  # 复核失败(重试耗尽) → 降级回第一遍
```
> 注：runner（ClaudeCodeRunner）已对 TRANSIENT 内置有界重试；此处 `except StageError` 捕获的是"重试仍失败"。

- [ ] **Step 4: 跑测试确认通过** — 6 passed（本文件）；全套绿。

- [ ] **Step 5: Commit**
```bash
git add src/autodev/adapters/context_claude.py tests/adapters/test_context_claude.py
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "feat(adapters): 上下文复核遍(_review)改进结果 + 失败降级"
```

---

### Task 5: 端口一致性契约 + live 冒烟 + 收尾

**Files:** Create `tests/adapters/test_context_contract.py`

**Interfaces:** 对 `ContextPort` 的共同行为断言，跑 `FakeContext` 与真实 ClaudeContextAdapter（注入假 runner）；外加一个 `@pytest.mark.live` 的真调 claude 冒烟（默认跳过）。

- [ ] **Step 1: 写测试**
```python
# tests/adapters/test_context_contract.py
import json
import os
from pathlib import Path
import pytest
from autodev.domain.value_objects import Requirement, WorkspaceHandle
from autodev.adapters.context_claude import ClaudeContextAdapter
from tests.fakes import FakeContext

REQ = Requirement("fix login", "repo-a", (), "raw")


def _handle(tmp_path):
    ws = tmp_path / "ws" / "wiabc"
    ws.mkdir(parents=True)
    (ws / "app.py").write_text("x = 1\n")
    return WorkspaceHandle(location=str(ws), label="autodev/wiabc")


@pytest.fixture(params=["fake", "real"])
def adapter(request, tmp_path):
    if request.param == "fake":
        return FakeContext()
    def runner(prompt, cwd):
        return json.dumps({"relevant_files": ["app.py"], "summary": "s"})
    return ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "home")


def test_gather_returns_context_artifact_with_pointer(adapter, tmp_path):
    art = adapter.gather(REQ, _handle(tmp_path))
    assert art.workspace_label == "autodev/wiabc"
    assert art.context_file  # 非空指针
    assert art.workspace_location


@pytest.mark.live
def test_live_gather_against_real_claude(tmp_path):
    if not os.environ.get("AUTODEV_LIVE"):
        pytest.skip("live 测试需 AUTODEV_LIVE=1 + 可用 claude/网关")
    from autodev.adapters.claude_runner import ClaudeCodeRunner
    ws = tmp_path / "ws" / "wilive"; ws.mkdir(parents=True)
    (ws / "app.py").write_text("def login(): ...\n")
    r = ClaudeCodeRunner()
    a = ClaudeContextAdapter(runner=lambda p, c: r.run(p, c, "plan"), autodev_home=tmp_path / "home")
    art = a.gather(Requirement("检查 login", "x", (), "raw"),
                   WorkspaceHandle(location=str(ws), label="autodev/wilive"))
    assert Path(art.context_file).read_text().strip()  # 非空
```
`pyproject.toml`：`[tool.pytest.ini_options]` 加 `markers = ["live: 需真实 claude/网关, 默认不跑"]`（避免 unknown-marker 警告）。默认 `pytest` 不加 `-m live` 就会因 skip 跳过 live 用例。

- [ ] **Step 2: 跑测试** — 契约 2 passed（1 用例 × 2 参数），live 用例 skipped。

- [ ] **Step 3: 更新 CHANGELOG（否则 doc-impact 门禁会卡）**

本 feature 改了 `src/**`，`CHANGELOG.md` 的 `## [Unreleased] > ### Added` 追加一条 F3 条目，概述：CONTEXT 阶段真实 `ContextPort`（ClaudeCodeRunner 共享底座 + ClaudeContextAdapter 两遍质检、Markdown 结果落盘 `~/.autodev`），及 `ContextArtifact` 改为指针（`context_file`）。`### Changed` 视需要补 ContextArtifact 字段变更一句。

- [ ] **Step 4: 全量门禁**
Run: `. venv/bin/activate && pytest -q && ruff check . && ruff format --check . && mypy src`
Expected: 全绿。

- [ ] **Step 5: Commit**
```bash
git add tests/adapters/test_context_contract.py pyproject.toml CHANGELOG.md
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "test(adapters): ContextPort 端口一致性契约 + live 冒烟(默认跳过)"
```

---

## Self-Review
- 覆盖 spec：ContextArtifact 改指针(§2/T1)、ClaudeCodeRunner(§4/T2)、收集+落盘(§5/T3)、复核降级(§5/T4)、契约+live(§6/T5)。
- 文档涟漪与门禁：T5 Step 3 补 `CHANGELOG.md` 是**真·CI 阻塞项**（doc-impact `src/**`→CHANGELOG）；T1 Step 5 更新 `diagrams.md` 是**准确性配套、非 CI 阻塞**（类图在 mermaid 代码块内，符号检查抓不到；漂移会静默，故手动改准）。
- 占位：T3 的 `_review` 占位在 T4 替换（唯一有意跨任务顺序）。其余 code step 完整。
- 类型一致：`ContextArtifact{workspace_location,workspace_label,context_file}`、`WorkspaceHandle{location,label}`、`Requirement.goal`、`StageError(FailureKind,msg)` 全程一致。
- runner 注入使单测零外部依赖；live 冒烟标记默认跳过；结果文件在 `~/.autodev`(可配置)、worktree 之外。
- work_item_id 取 `Path(handle.location).name`（F1 布局），spec/plan 一致注明。
