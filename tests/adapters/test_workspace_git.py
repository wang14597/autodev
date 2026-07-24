import subprocess
from pathlib import Path

import pytest

from autodev.adapters.workspace_git import (
    GitWorkspaceAdapter,
    GitWorkspaceConfig,
    _classify,
)
from autodev.domain.enums import FailureKind, WorkspaceMode
from autodev.domain.errors import StageError
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import RepoRef, WorkspaceHandle


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


def _make_remote(path: Path) -> str:
    """建一个带一个提交的本地 git 仓, 返回其路径(可作 file:// 远程)。"""
    path.mkdir(parents=True)

    def g(*args: str) -> None:
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    g("init", "--initial-branch=main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (path / "app.py").write_text("x = 1\n")
    g("add", ".")
    g("commit", "-m", "init")
    return str(path)


def _worktree_list(repo_path: str) -> str:
    return subprocess.run(
        ["git", "-C", repo_path, "worktree", "list"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_provision_local_repo_uses_worktree_off_source_no_mirror(tmp_path):
    # 本地 git 仓库路径(file:// 登记)→ 直接在源仓上开 worktree, 不整仓克隆。
    src = _make_remote(tmp_path / "voice-agent")
    cfg = _cfg(tmp_path, repo_map={"voice-agent": f"worktree:{src}"})
    a = GitWorkspaceAdapter(cfg)

    h = a.provision(WorkItemId("wid1"), RepoRef("voice-agent"), WorkspaceMode.FETCH, "autodev/wid1")

    # worktree 落在 workspaces_dir, 含源仓真实文件, 在指定分支
    assert Path(h.location).exists()
    assert (Path(h.location) / "app.py").read_text() == "x = 1\n"
    assert h.label == "autodev/wid1"
    # 关键: 没有建镜像(证明未整仓克隆)
    assert not (cfg.mirror_dir / "voice-agent.git").exists()
    # worktree 挂在源仓上(源仓 worktree list 含该路径)
    assert str(Path(h.location)) in _worktree_list(src)


def test_provision_local_repo_plain_path(tmp_path):
    # 裸本地路径(非 file://)也识别为本地仓库
    src = _make_remote(tmp_path / "proj")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"proj": f"worktree:{src}"}))
    h = a.provision(WorkItemId("w2"), RepoRef("proj"), WorkspaceMode.FETCH, "autodev/w2")
    assert (Path(h.location) / "app.py").exists()


def test_cleanup_local_worktree_removes_from_source(tmp_path):
    src = _make_remote(tmp_path / "proj")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"proj": f"worktree:{src}"}))
    h = a.provision(WorkItemId("w3"), RepoRef("proj"), WorkspaceMode.FETCH, "autodev/w3")
    assert str(Path(h.location)) in _worktree_list(src)

    a.cleanup(h)

    assert not Path(h.location).exists()  # worktree 目录已删
    assert str(Path(h.location)) not in _worktree_list(src)  # 源仓注册已清
    # 分支已删
    branches = subprocess.run(
        ["git", "-C", src, "branch", "--list", "autodev/w3"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert branches.strip() == ""


def test_provision_two_local_workitems_parallel(tmp_path):
    # 同一本地仓的两个工作项并行, 各自独立 worktree/分支, 互不影响。
    src = _make_remote(tmp_path / "proj")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"proj": f"worktree:{src}"}))
    h1 = a.provision(WorkItemId("a"), RepoRef("proj"), WorkspaceMode.FETCH, "autodev/a")
    h2 = a.provision(WorkItemId("b"), RepoRef("proj"), WorkspaceMode.FETCH, "autodev/b")
    assert Path(h1.location).exists() and Path(h2.location).exists()
    assert h1.location != h2.location
    lst = _worktree_list(src)
    assert str(Path(h1.location)) in lst and str(Path(h2.location)) in lst


def test_repo_status_local_worktree_repo_is_local_available(tmp_path):
    # worktree: 本地仓库 → exists_local=True(triage 选 REUSE, 语义干净)。
    src = _make_remote(tmp_path / "proj")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"proj": f"worktree:{src}"}))
    st = a.repo_status(RepoRef("proj"))
    assert st.exists_local is True and st.exists_remote is False


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
    cur = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ws, capture_output=True, text=True
    ).stdout.strip()
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
    _mirror_from_remote(a, "r", remote)  # 预置 mirror
    h = a.provision(WorkItemId("w2"), RepoRef("r"), WorkspaceMode.REUSE, "autodev/w2")
    assert Path(h.location, "app.py").exists()


def test_provision_second_work_item_does_not_corrupt_first(tmp_path):
    # 回归测试: 两个工作项共享同一仓库 mirror 时, 第二次 FETCH+prune 不应删掉
    # 第一个工作项本地创建的特性分支 (旧版用 `git clone --mirror` +
    # `remote update --prune` 会把 refs/heads/autodev/wi1 当成远端已删的分支裁掉)。
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))

    h1 = a.provision(WorkItemId("wi1"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/wi1")
    ws1 = Path(h1.location)
    assert ws1.exists()

    h2 = a.provision(WorkItemId("wi2"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/wi2")
    ws2 = Path(h2.location)
    assert ws2.exists()

    # wi1 的 worktree 必须仍然有效: 分支未被裁剪, 内容仍在。
    cur1 = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ws1, capture_output=True, text=True
    )
    assert cur1.returncode == 0
    assert cur1.stdout.strip() == "autodev/wi1"
    assert (ws1 / "app.py").read_text() == "x = 1\n"


def test_provision_same_work_item_twice_is_idempotent(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))

    h1 = a.provision(WorkItemId("wi1"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/wi1")
    h2 = a.provision(WorkItemId("wi1"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/wi1")

    assert h1 == h2


def test_provision_is_idempotent(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    h1 = a.provision(WorkItemId("dup"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/dup")
    h2 = a.provision(WorkItemId("dup"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/dup")
    assert h1 == h2  # 复用同一 worktree, 不报错


def test_provision_recreates_worktree_when_branch_differs(tmp_path):
    # 回归: _discard_worktree 与 cleanup 统一后, "同一 work_item 换分支名" 的幂等
    # 重建路径必须依然可用(旧分支删除、worktree 重建到新分支)。
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    a.provision(WorkItemId("wiX"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/old")
    h2 = a.provision(WorkItemId("wiX"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/new")
    assert h2.label == "autodev/new"
    cur = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=Path(h2.location),
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert cur == "autodev/new"
    branches = subprocess.run(
        ["git", "-C", str(a._mirror_path("r")), "branch", "--list", "autodev/old"],
        capture_output=True,
        text=True,
    ).stdout
    assert "autodev/old" not in branches


def test_cleanup_removes_worktree_and_branch_keeps_mirror(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    h = a.provision(WorkItemId("c1"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/c1")
    a.cleanup(h)
    assert not Path(h.location).exists()  # worktree 删除
    assert a._mirror_path("r").exists()  # mirror 保留
    branches = subprocess.run(
        ["git", "-C", str(a._mirror_path("r")), "branch", "--list", "autodev/c1"],
        capture_output=True,
        text=True,
    ).stdout
    assert "autodev/c1" not in branches  # 分支删除


def test_cleanup_is_idempotent(tmp_path):
    a = GitWorkspaceAdapter(_cfg(tmp_path))
    a.cleanup(WorkspaceHandle(location=str(tmp_path / "gone"), label="b"))  # 不报错


def test_provision_create_inits_local_repo_with_worktree(tmp_path):
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={}))  # 无远程
    h = a.provision(WorkItemId("new1"), RepoRef("brand-new"), WorkspaceMode.CREATE, "autodev/new1")
    ws = Path(h.location)
    assert ws.exists()
    cur = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ws, capture_output=True, text=True
    ).stdout.strip()
    assert cur == "autodev/new1"
    # 有一个初始提交可据以工作
    log = subprocess.run(["git", "log", "--oneline"], cwd=ws, capture_output=True, text=True).stdout
    assert log.strip()  # 非空
    assert a._mirror_path("brand-new").exists()
