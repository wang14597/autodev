# F1 工作区 ACL Implementation Plan

> **For agentic workers:** 用 subagent-driven-development 逐任务执行 + 评审。全程 TDD。所有测试用本地临时 git 仓（file:// / 本地路径），无需任何外部凭证。

**Goal:** 实现 GitWorkspaceAdapter（`src/autodev/adapters/workspace_git.py`），真实实现 `WorkspacePort`（repo_status / provision / cleanup，模式 REUSE/FETCH/CREATE），用本地 git 仓完整测试。

**Architecture:** 设计见 `docs/superpowers/specs/2026-07-20-f1-workspace-acl-design.md`。适配器把 `WorkspaceMode`/`RepoRef`/`WorkspaceHandle` 翻译成真实 git 命令（mirror 缓存 + worktree），git 失败在边界翻译成领域 `StageError`+`FailureKind`。

**Tech Stack:** Python(subprocess/pathlib/dataclasses)、pytest、系统 `git`。

## Global Constraints
- 只跟 git 打交道；不碰 GitLab API / Claude / 飞书。
- git 子进程失败翻译成 `StageError(FailureKind, msg)`：网络/超时→TRANSIENT，未映射仓库/鉴权→FATAL，其他非零→LOGIC，git 缺失→FATAL。每个 git 调用带超时。
- `provision`/`cleanup` 幂等（可重跑）。
- 不改领域/应用层运行时逻辑或其他适配器。接入真实运行（替换 `FakeWorkspace`）属 F8，不在此。
- 现有全套测试保持绿；`ruff check . && ruff format --check . && mypy src`（新适配器在 src 内，须过 mypy）通过。
- 需要 git ≥ 2.28（用 `--initial-branch`）。
- Conventional Commits；提交人 `AutoDev <autodev@local>`，body 末附 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。

## File Structure
```
src/autodev/adapters/workspace_git.py   # GitWorkspaceConfig + GitWorkspaceAdapter
tests/adapters/test_workspace_git.py     # 行为测试(本地 git 仓)
tests/adapters/test_workspace_contract.py# 端口一致性: 真适配器 vs FakeWorkspace
```

---

### Task 1: 骨架 — 配置 + `_git`/`_classify` 失败翻译

**Files:** Create `src/autodev/adapters/workspace_git.py`; Test `tests/adapters/test_workspace_git.py`

**Interfaces:**
- `GitWorkspaceConfig(repo_map: dict[str,str], mirror_dir: Path, workspaces_dir: Path)` frozen。
- `GitWorkspaceAdapter(config, run=subprocess.run, timeout=60)`；内部 `_git(args, cwd=None) -> str`、`_classify(stderr) -> FailureKind`、`_mirror_path(name)`、`_resolve_url(name)`。
- 失败翻译：超时→TRANSIENT，git 缺失(FileNotFoundError)→FATAL，非零按 stderr 关键词分类（网络→TRANSIENT，鉴权→FATAL，其余→LOGIC）。

- [ ] **Step 1: 写失败测试**

```python
# tests/adapters/test_workspace_git.py
import subprocess
from pathlib import Path

import pytest

from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError
from autodev.adapters.workspace_git import GitWorkspaceConfig, GitWorkspaceAdapter, _classify


def _cfg(tmp_path: Path, repo_map=None) -> GitWorkspaceConfig:
    return GitWorkspaceConfig(
        repo_map=repo_map or {},
        mirror_dir=tmp_path / "mirrors",
        workspaces_dir=tmp_path / "ws",
    )


def test_classify_maps_stderr_to_failure_kind():
    assert _classify("fatal: Could not resolve host: gitlab") is FailureKind.TRANSIENT
    assert _classify("git@x: Permission denied (publickey).") is FailureKind.FATAL
    assert _classify("error: pathspec 'x' did not match") is FailureKind.LOGIC


def test_git_nonzero_raises_stageerror_classified(tmp_path):
    def fake_run(*a, **k):
        return subprocess.CompletedProcess(a, 1, stdout="", stderr="Could not resolve host: gitlab")
    adapter = GitWorkspaceAdapter(_cfg(tmp_path), run=fake_run)
    with pytest.raises(StageError) as ei:
        adapter._git(["ls-remote", "x"])
    assert ei.value.failure_kind is FailureKind.TRANSIENT


def test_git_missing_binary_is_fatal(tmp_path):
    def fake_run(*a, **k):
        raise FileNotFoundError("git")
    adapter = GitWorkspaceAdapter(_cfg(tmp_path), run=fake_run)
    with pytest.raises(StageError) as ei:
        adapter._git(["status"])
    assert ei.value.failure_kind is FailureKind.FATAL


def test_git_timeout_is_transient(tmp_path):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)
    adapter = GitWorkspaceAdapter(_cfg(tmp_path), run=fake_run)
    with pytest.raises(StageError) as ei:
        adapter._git(["clone", "x"])
    assert ei.value.failure_kind is FailureKind.TRANSIENT
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/adapters/test_workspace_git.py -q` → FAIL（模块不存在）。

- [ ] **Step 3: 实现**

```python
# src/autodev/adapters/workspace_git.py
from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from autodev.domain.enums import FailureKind, WorkspaceMode
from autodev.domain.errors import StageError
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import RepoRef, RepoStatus, WorkspaceHandle

_NETWORK_HINTS = (
    "could not resolve host", "connection", "timed out",
    "unable to access", "network is unreachable", "failed to connect",
)
_AUTH_HINTS = (
    "authentication failed", "permission denied", "access denied",
    "could not read from remote", "publickey",
)


def _classify(stderr: str) -> FailureKind:
    s = stderr.lower()
    if any(h in s for h in _NETWORK_HINTS):
        return FailureKind.TRANSIENT
    if any(h in s for h in _AUTH_HINTS):
        return FailureKind.FATAL
    return FailureKind.LOGIC


@dataclass(frozen=True)
class GitWorkspaceConfig:
    repo_map: dict[str, str]
    mirror_dir: Path
    workspaces_dir: Path


class GitWorkspaceAdapter:
    def __init__(
        self,
        config: GitWorkspaceConfig,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout: int = 60,
    ) -> None:
        self._config = config
        self._run = run
        self._timeout = timeout

    def _git(self, args: list[str], cwd: Path | None = None) -> str:
        try:
            proc = self._run(
                ["git", *args],
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise StageError(FailureKind.TRANSIENT, f"git 超时: {' '.join(args)}") from e
        except FileNotFoundError as e:
            raise StageError(FailureKind.FATAL, "git 不可用") from e
        if proc.returncode != 0:
            raise StageError(
                _classify(proc.stderr),
                f"git {' '.join(args)} 失败: {proc.stderr.strip()[:200]}",
            )
        return proc.stdout.strip()

    def _mirror_path(self, name: str) -> Path:
        return self._config.mirror_dir / f"{name}.git"

    def _resolve_url(self, name: str) -> str:
        url = self._config.repo_map.get(name)
        if not url:
            raise StageError(FailureKind.FATAL, f"仓库未在 repo_map 登记: {name}")
        return url
```

- [ ] **Step 4: 跑测试确认通过** — `pytest tests/adapters/test_workspace_git.py -q` → 4 passed。`ruff check src/autodev/adapters/workspace_git.py && mypy src` 通过。

- [ ] **Step 5: Commit**
```bash
git add src/autodev/adapters/workspace_git.py tests/adapters/test_workspace_git.py
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "feat(adapters): GitWorkspaceAdapter 骨架 + git 失败翻译"
```

---

### Task 2: `repo_status`

**Files:** Modify `src/autodev/adapters/workspace_git.py`; `tests/adapters/test_workspace_git.py`

**Interfaces:** `repo_status(repo: RepoRef) -> RepoStatus`：exists_local=mirror 目录在否；exists_remote=name 在 repo_map 且 `git ls-remote` 成功（探测失败→False，不抛）。

- [ ] **Step 1: 写失败测试**（用本地 git 仓当 file:// 远程）

```python
# 追加到 tests/adapters/test_workspace_git.py
from autodev.domain.value_objects import RepoRef


def _make_remote(path: Path) -> str:
    """建一个带一个提交的本地 git 仓, 返回其路径(可作 file:// 远程)。"""
    path.mkdir(parents=True)
    def g(*args): subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
    g("init", "--initial-branch=main")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (path / "app.py").write_text("x = 1\n")
    g("add", "."); g("commit", "-m", "init")
    return str(path)


def test_repo_status_unmapped_is_all_false(tmp_path):
    a = GitWorkspaceAdapter(_cfg(tmp_path))
    st = a.repo_status(RepoRef("nope"))
    assert st.exists_local is False and st.exists_remote is False


def test_repo_status_mapped_remote_true(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    st = a.repo_status(RepoRef("r"))
    assert st.exists_remote is True and st.exists_local is False


def test_repo_status_local_true_when_mirror_present(tmp_path):
    cfg = _cfg(tmp_path, repo_map={})
    (cfg.mirror_dir / "r.git").mkdir(parents=True)
    a = GitWorkspaceAdapter(cfg)
    assert a.repo_status(RepoRef("r")).exists_local is True
```

- [ ] **Step 2: 跑测试确认失败** — repo_status 未实现 → FAIL。

- [ ] **Step 3: 实现**（追加方法）
```python
    def repo_status(self, repo: RepoRef) -> RepoStatus:
        exists_local = self._mirror_path(repo.name).exists()
        exists_remote = False
        url = self._config.repo_map.get(repo.name)
        if url:
            try:
                self._git(["ls-remote", url])
                exists_remote = True
            except StageError:
                exists_remote = False
        return RepoStatus(exists_local=exists_local, exists_remote=exists_remote)
```

- [ ] **Step 4: 跑测试确认通过** — 3 passed（本节）。全套 `pytest -q` 绿。

- [ ] **Step 5: Commit**
```bash
git add src/autodev/adapters/workspace_git.py tests/adapters/test_workspace_git.py
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "feat(adapters): repo_status(local/remote 探测)"
```

---

### Task 3: `provision` REUSE / FETCH

**Files:** Modify adapter + tests

**Interfaces:** `provision(work_item_id, repo, mode, branch) -> WorkspaceHandle`（本任务实现 REUSE/FETCH 路径）；辅助 `_ensure_mirror`、`_base_ref`。REUSE：mirror 须已在(否则 FATAL)。FETCH：无 mirror→`git clone --mirror`，有→`remote update --prune`。worktree 从 mirror 默认分支拉。

- [ ] **Step 1: 写失败测试**
```python
# 追加
from autodev.domain.enums import WorkspaceMode
from autodev.domain.ids import WorkItemId


def _mirror_from_remote(adapter, name, remote_url):
    # 借 FETCH 建 mirror
    adapter._git(["clone", "--mirror", remote_url, str(adapter._mirror_path(name))])


def test_provision_fetch_creates_worktree_on_branch(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    h = a.provision(WorkItemId("wi123456"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/wi123456")
    ws = Path(h.location)
    assert ws.exists() and (ws / "app.py").read_text() == "x = 1\n"
    assert h.label == "autodev/wi123456"
    # 分支正确
    cur = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ws,
                         capture_output=True, text=True).stdout.strip()
    assert cur == "autodev/wi123456"
    assert a._mirror_path("r").exists()  # mirror 落地


def test_provision_reuse_requires_existing_mirror(tmp_path):
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={}))
    with pytest.raises(StageError) as ei:
        a.provision(WorkItemId("w"), RepoRef("r"), WorkspaceMode.REUSE, "b")
    assert ei.value.failure_kind is FailureKind.FATAL


def test_provision_reuse_uses_cached_mirror(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    _mirror_from_remote(a, "r", remote)          # 预置 mirror
    h = a.provision(WorkItemId("w2"), RepoRef("r"), WorkspaceMode.REUSE, "autodev/w2")
    assert Path(h.location, "app.py").exists()
```

- [ ] **Step 2: 跑测试确认失败**。

- [ ] **Step 3: 实现**（追加）
```python
    def provision(
        self, work_item_id: WorkItemId, repo: RepoRef, mode: WorkspaceMode, branch: str
    ) -> WorkspaceHandle:
        mirror = self._mirror_path(repo.name)
        ws = self._config.workspaces_dir / work_item_id.value
        if ws.exists():  # 幂等: 已有 worktree
            current = self._git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=ws)
            if current == branch:
                return WorkspaceHandle(location=str(ws), label=branch)
            self.cleanup(WorkspaceHandle(location=str(ws), label=current))
        self._ensure_mirror(mirror, repo.name, mode)
        base = self._base_ref(mirror)
        self._config.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self._git(["-C", str(mirror), "worktree", "add", "-b", branch, str(ws), base])
        return WorkspaceHandle(location=str(ws), label=branch)

    def _ensure_mirror(self, mirror: Path, name: str, mode: WorkspaceMode) -> None:
        if mode is WorkspaceMode.REUSE:
            if not mirror.exists():
                raise StageError(FailureKind.FATAL, f"REUSE 模式但本地无 mirror: {name}")
            return
        if mode is WorkspaceMode.FETCH:
            if mirror.exists():
                self._git(["-C", str(mirror), "remote", "update", "--prune"])
            else:
                url = self._resolve_url(name)
                mirror.parent.mkdir(parents=True, exist_ok=True)
                self._git(["clone", "--mirror", url, str(mirror)])
            return
        self._create_seed_mirror(mirror)  # CREATE (Task 4)

    def _base_ref(self, mirror: Path) -> str:
        return self._git(["-C", str(mirror), "symbolic-ref", "--short", "HEAD"])
```
> 注：`_create_seed_mirror` 在 Task 4 实现；本任务不测 CREATE 路径。若 lint 报未定义, 先加一个 `raise NotImplementedError` 占位方法, Task 4 替换。

- [ ] **Step 4: 跑测试确认通过** — 3 passed；全套绿；mypy 过。

- [ ] **Step 5: Commit**
```bash
git add src/autodev/adapters/workspace_git.py tests/adapters/test_workspace_git.py
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "feat(adapters): provision REUSE/FETCH + worktree"
```

---

### Task 4: `provision` CREATE（本地 init 种子 mirror）

**Files:** Modify adapter + tests

**Interfaces:** `_create_seed_mirror(mirror)`：`git init --bare --initial-branch=main`，再经临时工作仓造一个空初始提交 push 进 bare mirror，使 `main` 存在可据以拉 worktree。CREATE 不碰远程（F6 再建）。

- [ ] **Step 1: 写失败测试**
```python
def test_provision_create_inits_local_repo_with_worktree(tmp_path):
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={}))  # 无远程
    h = a.provision(WorkItemId("new1"), RepoRef("brand-new"), WorkspaceMode.CREATE, "autodev/new1")
    ws = Path(h.location)
    assert ws.exists()
    cur = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ws,
                         capture_output=True, text=True).stdout.strip()
    assert cur == "autodev/new1"
    # 有一个初始提交可据以工作
    log = subprocess.run(["git", "log", "--oneline"], cwd=ws, capture_output=True, text=True).stdout
    assert log.strip()  # 非空
    assert a._mirror_path("brand-new").exists()
```

- [ ] **Step 2: 跑测试确认失败**（`_create_seed_mirror` 未实现/占位）。

- [ ] **Step 3: 实现**
```python
    def _create_seed_mirror(self, mirror: Path) -> None:
        mirror.parent.mkdir(parents=True, exist_ok=True)
        self._git(["init", "--bare", "--initial-branch=main", str(mirror)])
        with tempfile.TemporaryDirectory() as tmp:
            self._git(["init", "--initial-branch=main", tmp])
            self._git([
                "-C", tmp,
                "-c", "user.name=AutoDev", "-c", "user.email=autodev@local",
                "commit", "--allow-empty", "-m", "chore: init",
            ])
            self._git(["-C", tmp, "push", str(mirror), "main"])
```

- [ ] **Step 4: 跑测试确认通过** — 1 passed；全套绿。

- [ ] **Step 5: Commit**
```bash
git add src/autodev/adapters/workspace_git.py tests/adapters/test_workspace_git.py
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "feat(adapters): provision CREATE(本地种子 mirror)"
```

---

### Task 5: 幂等 + `cleanup`

**Files:** Modify adapter + tests

**Interfaces:** `cleanup(handle)`：从 worktree 经 `rev-parse --git-common-dir` 找到 mirror，`worktree remove --force` + `branch -D <label>`（分支不存在忽略）+ `worktree prune`；location 不存在→no-op。provision 幂等（已在 Task 3 代码含 ws.exists 复用逻辑，本任务补测 + cleanup）。

- [ ] **Step 1: 写失败测试**
```python
def test_provision_is_idempotent(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    h1 = a.provision(WorkItemId("dup"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/dup")
    h2 = a.provision(WorkItemId("dup"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/dup")
    assert h1 == h2  # 复用同一 worktree, 不报错


def test_cleanup_removes_worktree_and_branch_keeps_mirror(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    h = a.provision(WorkItemId("c1"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/c1")
    a.cleanup(h)
    assert not Path(h.location).exists()          # worktree 删除
    assert a._mirror_path("r").exists()           # mirror 保留
    branches = subprocess.run(["git", "-C", str(a._mirror_path("r")), "branch", "--list", "autodev/c1"],
                              capture_output=True, text=True).stdout
    assert "autodev/c1" not in branches           # 分支删除


def test_cleanup_is_idempotent(tmp_path):
    a = GitWorkspaceAdapter(_cfg(tmp_path))
    a.cleanup(WorkspaceHandle(location=str(tmp_path / "gone"), label="b"))  # 不报错
```

- [ ] **Step 2: 跑测试确认失败**。

- [ ] **Step 3: 实现**
```python
    def cleanup(self, handle: WorkspaceHandle) -> None:
        loc = Path(handle.location)
        if not loc.exists():
            return
        common = self._git(["-C", str(loc), "rev-parse", "--git-common-dir"])
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = (loc / common_path).resolve()
        self._git(["-C", str(common_path), "worktree", "remove", "--force", str(loc)])
        try:
            self._git(["-C", str(common_path), "branch", "-D", handle.label])
        except StageError:
            pass
        self._git(["-C", str(common_path), "worktree", "prune"])
```

- [ ] **Step 4: 跑测试确认通过** — 3 passed；全套绿；mypy 过。

- [ ] **Step 5: Commit**
```bash
git add src/autodev/adapters/workspace_git.py tests/adapters/test_workspace_git.py
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "feat(adapters): cleanup(经 git-common-dir 回收) + provision 幂等测试"
```

---

### Task 6: 端口一致性契约测试 + 收尾

**Files:** Create `tests/adapters/test_workspace_contract.py`

**Interfaces:** 一组对 `WorkspacePort` 的行为断言，分别对 `FakeWorkspace` 与真实 GitWorkspaceAdapter 跑，证明二者契约一致（假实现不跑偏）。

- [ ] **Step 1: 写契约测试**
```python
# tests/adapters/test_workspace_contract.py
import subprocess
from pathlib import Path

import pytest

from autodev.domain.enums import WorkspaceMode
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import RepoRef
from autodev.adapters.workspace_git import GitWorkspaceConfig, GitWorkspaceAdapter
from tests.fakes import FakeWorkspace


def _make_remote(path: Path) -> str:
    path.mkdir(parents=True)
    def g(*a): subprocess.run(["git", *a], cwd=path, check=True, capture_output=True)
    g("init", "--initial-branch=main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (path / "app.py").write_text("x = 1\n"); g("add", "."); g("commit", "-m", "init")
    return str(path)


def _real(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    return GitWorkspaceAdapter(GitWorkspaceConfig(
        repo_map={"r": remote}, mirror_dir=tmp_path / "m", workspaces_dir=tmp_path / "w"))


@pytest.fixture(params=["fake", "real"])
def workspace(request, tmp_path):
    return FakeWorkspace(local=True) if request.param == "fake" else _real(tmp_path)


def test_provision_returns_handle_with_requested_label(workspace):
    h = workspace.provision(WorkItemId("k1"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/k1")
    assert h.label == "autodev/k1"
    assert h.location  # 非空路径


def test_cleanup_accepts_provisioned_handle(workspace):
    h = workspace.provision(WorkItemId("k2"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/k2")
    workspace.cleanup(h)  # 两种实现都不应抛
```
> 注：契约取二者共同保证的行为（返回带 label 的 handle、cleanup 可接受该 handle 不抛）。FakeWorkspace 的 provision/cleanup 签名须与端口一致——若不一致则是 fake 跑偏, 属真问题, 修 fake。

- [ ] **Step 2: 跑测试** — `pytest tests/adapters/test_workspace_contract.py -q` → 4 passed（2 用例 × 2 参数）。

- [ ] **Step 3: 全量门禁**
Run: `. venv/bin/activate && pytest -q && ruff check . && ruff format --check . && mypy src`
Expected: 全绿。

- [ ] **Step 4: Commit**
```bash
git add tests/adapters/test_workspace_contract.py
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "test(adapters): WorkspacePort 端口一致性契约(fake vs 真实)"
```

---

## Self-Review
- 覆盖 spec：repo_status(§4)、provision REUSE/FETCH/CREATE(§4)、cleanup(§4)、幂等(§5)、失败翻译(§5)、契约测试(§6)——全覆盖。
- 占位扫描：Task 3 注明 `_create_seed_mirror` 先占位、Task 4 替换（唯一有意的跨任务顺序）。其余 code step 均完整。
- 类型一致：`WorkspaceHandle{location,label}`、`RepoStatus{exists_local,exists_remote}`、`StageError(FailureKind,msg)`、`WorkspaceMode.REUSE/FETCH/CREATE` 全程与领域一致。
- 无外部凭证：所有测试用本地 git 仓 / 本地路径。
- 边界：不接入真实运行(F8)、不建远程仓(F6)、并发留后续——与 spec §7 一致。
